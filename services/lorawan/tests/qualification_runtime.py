"""Closed, run-specific system guardian adapters; no effects at import."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import time
from urllib.parse import quote
from services.lorawan.tests.qualification_guard import (require, SERVICES, validate_ids, WORKLOAD_PHASES, PHASE_REQUESTS,
    PhaseDeadline, PhaseExpired, check_deadline, phase_scope)
from services.lorawan.tests.stack_ownership import CAPS, RUNTIME_IMAGE, BINDS, VOLUMES, PORTS, PROJECT, _sources, rendered_memory_bytes


def fingerprint(container):
    result={key:deepcopy(container[key]) for key in ('Id','Name','Image','Config','HostConfig','Mounts')}
    host=result['HostConfig']
    if 'OomKillDisable' in host:
        # Docker materializes its disabled default as null after first start.
        # Preserve field presence and every other identity value.
        require(host['OomKillDisable'] is False or host['OomKillDisable'] is None,'unexpected Docker OOM-kill flag')
        host['OomKillDisable']=False
    return result


class DockerBackend:
    """Only lifecycle requests for the immutable seven-ID manifest are writable.

    The request adapter returns None for a confirmed missing inspected ID. Every
    other daemon/protocol failure raises and leaves the admission FD pinned.
    """
    def __init__(self,manifest,*,request,cgroup_empty,mode='qualification'):
        require(mode in ('qualification','lifecycle-proof'));self.mode=mode
        self.manifest=deepcopy(manifest);self.request=request;self.cgroup_empty=cgroup_empty
        require(set(manifest)=={'schema','nonce','root','compose_sha256','rendered','containers','images','networks','volumes'})
        require(manifest['schema']=='earthship-sensor-qualification/v1' and re.fullmatch('[a-f0-9]{32}',manifest['nonce']))
        self.root=Path(manifest['root']);require(self.root.is_absolute() and self.root.resolve()==self.root)
        self.ids={service:c['Id'] for service,c in manifest['containers'].items()};validate_ids(self.ids)
        self.configuration()
        rendered=manifest['rendered'];require(set(rendered['services'])==set(SERVICES))
        require(set(manifest['networks'])=={PROJECT+'_sensors',PROJECT+'_management'})
        require(all(re.fullmatch('[a-f0-9]{64}',value) for value in manifest['networks'].values()))
        require(set(manifest['volumes'])=={name for values in VOLUMES.values() for name in values.values()})
        for service,container in manifest['containers'].items():
            require(container['State']['Running'] is False and container['State']['Pid']==0,'precreation must be stopped')
            self.container(container,service)
        self.fingerprints={c['Id']:fingerprint(c) for c in manifest['containers'].values()}

    def configuration(self):
        compose=self.root/'deploy/lorawan/compose.test.yaml'
        require(compose.resolve()==compose and compose.is_file())
        raw=compose.read_bytes();require(len(raw)<=131072 and sha256(raw).hexdigest()==self.manifest['compose_sha256'],'Compose source changed')

    def container(self,container,service):
        spec=self.manifest['rendered']['services'][service];labels=container['Config']['Labels'];host=container['HostConfig']
        memory,cpu,tasks=CAPS[service]
        require(container['Id']==self.ids[service] and container['Name']=='/'+PROJECT+'-'+service+'-1')
        require(labels.get('com.docker.compose.project')==PROJECT and labels.get('com.docker.compose.service')==service
                and labels.get('com.docker.compose.project.working_dir')==str(self.root/'deploy/lorawan')
                and labels.get('com.docker.compose.project.config_files')==str(self.root/'deploy/lorawan/compose.test.yaml')
                and labels.get('org.earthship.sensor.qualification')==self.manifest['nonce'])
        require(rendered_memory_bytes(spec.get('mem_limit'))==memory*1024**2 and rendered_memory_bytes(spec.get('memswap_limit'))==memory*1024**2
                and float(spec.get('cpus',0))==cpu and spec.get('pids_limit')==tasks and spec.get('restart')=='no' and 'build' not in spec)
        require(host['Memory']==memory*1024**2 and host['MemorySwap']==memory*1024**2 and host['NanoCpus']==int(cpu*10**9)
                and host['PidsLimit']==tasks and host['RestartPolicy']=={'Name':'no','MaximumRetryCount':0}
                and host.get('Privileged') is False and host.get('AutoRemove') is False)
        require(container['Config']['Image']==spec['image'] and container['Image']==self.manifest['images'][spec['image']])
        require(re.fullmatch('sha256:[a-f0-9]{64}',container['Image']))
        if service in ('ingest','simulator'):require(spec['image']==RUNTIME_IMAGE and container['Image']==RUNTIME_IMAGE)
        binds={m['Destination']:m['Source'] for m in container['Mounts'] if m['Type']=='bind'}
        volumes={m['Destination']:m['Name'] for m in container['Mounts'] if m['Type']=='volume'}
        require(binds==_sources(self.root,service) and volumes==VOLUMES.get(service,{}))
        expected={m['target']:not m.get('read_only',False) for m in spec.get('volumes',[])}
        require({m['Destination']:m['RW'] for m in container['Mounts'] if m['Type'] in ('bind','volume')}==expected)
        networks={PROJECT+'_'+name for name in spec['networks']}
        expected_names={PROJECT+'_sensors',PROJECT+'_management'} if service in PORTS else {PROJECT+'_sensors'}
        require(networks==expected_names and set(container['NetworkSettings']['Networks'])==networks)
        for name,value in container['NetworkSettings']['Networks'].items():
            require(value.get('NetworkID') in ('',self.manifest['networks'][name]))
            if container['State']['Running']:require(value.get('NetworkID')==self.manifest['networks'][name])
        ports={str(p['target'])+'/tcp':[{'HostIp':p['host_ip'],'HostPort':str(p['published'])}] for p in spec.get('ports',[])}
        require(host.get('PortBindings',{})==ports)
        if service in PORTS:
            internal,published=PORTS[service];require(ports=={internal:[{'HostIp':'127.0.0.1','HostPort':published}]})
        else:require(not ports)
        if container['State']['Running']:
            require({p:b for p,b in container['NetworkSettings']['Ports'].items() if b}==ports)

    def _request(self,method,path,*,deadline=None):
        check_deadline(deadline)
        result=self.request(method,path,deadline=deadline) if deadline is not None else self.request(method,path)
        check_deadline(deadline)
        return result

    def validate(self,ids,*,running=False,cleanup=False,deadline=None):
        check_deadline(deadline)
        require(ids==self.ids);self.configuration();check_deadline(deadline)
        for service,identity in self.ids.items():
            container=self._request('GET','/containers/'+identity+'/json',deadline=deadline)
            if container is None:
                require(cleanup,'missing owned fixture');continue
            if self.mode=='lifecycle-proof' and service!='mqtt' and not cleanup:
                require(container['State']['Running'] is False,'proof mode permits only MQTT to run')
            self.container(container,service)
            require(fingerprint(container)==self.fingerprints[identity],'original container configuration changed')
            if running:require(container['State']['Running'] is True)
        for name,identity in self.manifest['networks'].items():
            network=self._request('GET','/networks/'+name,deadline=deadline)
            require(network['Id']==identity and network['Name']==name and network['Driver']=='bridge'
                    and network['Internal']==name.endswith('_sensors') and network['Labels'].get('com.docker.compose.project')==PROJECT)
        for name,expected in self.manifest['volumes'].items():
            volume=self._request('GET','/volumes/'+name,deadline=deadline)
            require(volume==expected,'retained volume identity changed')
            require(volume['Name']==name and volume['Driver']=='local' and volume.get('Options') in (None,{})
                    and volume['Labels'].get('com.docker.compose.project')==PROJECT
                    and volume['Labels'].get('com.docker.compose.volume')==name.removeprefix(PROJECT+'_'))
        inventory=self._request('GET','/containers/json?all=1',deadline=deadline);require(len(inventory)<=256)
        for summary in inventory:
            identity=summary['Id'];require(re.fullmatch('[a-f0-9]{64}',identity))
            container=self._request('GET','/containers/'+identity+'/json',deadline=deadline)
            require(container is not None,'container inventory changed')
            if (container['Config']['Labels'].get('com.docker.compose.project')==PROJECT
                    or container['Name'] in {'/'+PROJECT+'-'+service+'-1' for service in SERVICES}):
                require(identity in self.ids.values(),'unrecognized replacement fixture identity')
            if any(m['Type']=='volume' and m.get('Name') in self.manifest['volumes'] for m in container['Mounts']):
                require(identity in self.ids.values(),'foreign retained-volume consumer')
        check_deadline(deadline)

    def action(self,action,identity,*,deadline=None):
        check_deadline(deadline)
        require(identity in self.ids.values() and action in ('start','stop','restart','remove'))
        self.validate(self.ids,cleanup=action=='remove',deadline=deadline)
        check_deadline(deadline)  # Nested validation cannot renew submission authority.
        if action=='remove':return self._request('DELETE','/containers/'+identity+'?force=1&v=0',deadline=deadline)
        return self._request('POST','/containers/'+identity+'/'+action+('' if action=='start' else '?t=10'),deadline=deadline)

    def absent(self,ids):
        require(ids==self.ids)
        return all(self.request('GET','/containers/'+identity+'/json') is None and self.cgroup_empty(identity) for identity in ids.values())

    def retired(self,services,*,deadline=None):
        check_deadline(deadline)
        require(self.mode=='qualification' and services in (('chirpstack',),('chirpstack','redis'),('chirpstack','redis','simulator')))
        self.validate(self.ids,deadline=deadline);check_deadline(deadline)
        proofs={}
        for service in services:
            identity=self.ids[service];value=self._request('GET','/containers/'+identity+'/json',deadline=deadline)
            require(value is not None and value['Id']==identity and value['State']['Running'] is False
                and type(value['State']['Pid']) is int and value['State']['Pid']==0,'retirement requires the original stopped ID')
            require(self.cgroup_empty(identity),'retired cgroup still populated')
            check_deadline(deadline)
            proofs[service]={'id':identity,'running':False,'pid':0,'cgroup_empty':True}
        return proofs

    def browser_ready(self,*,deadline=None):
        self.retired(('chirpstack','redis','simulator'),deadline=deadline);check_deadline(deadline)
        for service in ('mqtt','postgres','ingest','openhab'):
            value=self._request('GET','/containers/'+self.ids[service]+'/json',deadline=deadline)
            require(value is not None and value['Id']==self.ids[service] and value['State']['Running'] is True
                    and type(value['State']['Pid']) is int and value['State']['Pid']>1,'browser dependency not running')
        check_deadline(deadline)



class DockerSocket:
    """Bounded Unix HTTP transport; never honors DOCKER_HOST or TCP endpoints."""
    def __init__(self,path=Path('/run/docker.sock'),*,owner=0,after_request=lambda method,path:None):
        import stat
        self.path=Path(path);info=self.path.lstat()
        require(self.path.resolve()==self.path and stat.S_ISSOCK(info.st_mode) and info.st_uid==owner
                and not info.st_mode & 0o007,'owned Docker socket required')
        self.identity=(info.st_dev,info.st_ino);self.after_request=after_request

    def __call__(self,method,path,*,deadline=None):
        import http.client
        import socket
        from services.lorawan.tests.qualification_guard import decode,Refused
        check_deadline(deadline)
        require(method in ('GET','POST','DELETE') and path.startswith('/') and '\n' not in path and '\r' not in path)
        info=self.path.lstat();require((info.st_dev,info.st_ino)==self.identity,'Docker socket changed')
        def timeout():return deadline.timeout(35) if deadline is not None else 35
        connection=http.client.HTTPConnection('localhost',timeout=timeout());response=None
        try:
            connection.sock=transport=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            transport.settimeout(timeout());transport.connect(str(self.path))
            transport.settimeout(timeout());check_deadline(deadline)
            connection.request(method,path,headers={'Connection':'close'})
            check_deadline(deadline)
            self.after_request(method,path)
            check_deadline(deadline);transport.settimeout(timeout())
            response=connection.getresponse();check_deadline(deadline)
            transport.settimeout(timeout());raw=response.read(1048577);check_deadline(deadline)
            require(len(raw)<=1048576)
            if response.status==404 and re.fullmatch('/containers/[a-f0-9]{64}(?:/json|\\?force=1&v=0)',path):return None
            require(response.status in (200,201,204,304))
            return decode(raw,limit=1048576) if raw else None
        except PhaseExpired:raise
        except (OSError,ValueError,http.client.HTTPException,Refused) as error:
            raise Refused('Docker protocol refused') from None
        finally:
            if response is not None:response.close()
            connection.close()


class SystemdNotify:
    def __init__(self,address):
        require(isinstance(address,str) and address[:1] in ('/','@') and len(address)<108)
        self.address='\0'+address[1:] if address.startswith('@') else address

    def __call__(self,message,fd=None):
        import array,socket
        raw=message.encode();require(len(raw)<=8192)
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM|socket.SOCK_CLOEXEC) as connection:
            connection.settimeout(5);connection.connect(self.address)
            ancillary=[] if fd is None else [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))]
            require(connection.sendmsg([raw],ancillary)==len(raw))

    def barrier(self):
        import os,select
        read,write=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK)
        try:
            self('BARRIER=1',write);os.close(write);write=None
            ready,_,_=select.select([read],[],[],5)
            require(ready and os.read(read,1)==b'','PID1 notification barrier unacknowledged')
        finally:
            os.close(read)
            if write is not None:os.close(write)


class Controller:
    """One original admitted scope; never signals a reused PID or parent slice."""
    def __init__(self,record,*,proc_root=Path('/proc'),cgroup_root=Path('/sys/fs/cgroup')):
        self.record=deepcopy(record);self.proc=Path(proc_root);self.cg=Path(cgroup_root)
        require(set(record)=={'pid','starttime','uid','cgroup','dev','ino','unit','invocation','guardian_unit'})
        require(type(record['pid']) is int and record['pid']>1 and type(record['starttime']) is int and record['starttime']>0 and record['uid']==1000)
        require(re.fullmatch('earthship-job-[a-f0-9]{32}\\.scope',record['unit']) and re.fullmatch('[a-f0-9]{32}',record['invocation']))
        expected='/user.slice/user-1000.slice/user@1000.service/earthship.slice/earthship-work.slice/'+record['unit']
        require(record['cgroup']==expected and re.fullmatch('earthship-sensor-guard-[a-f0-9]{32}\\.service',record['guardian_unit']))
        self.scope=self.cg/expected.lstrip('/')

    def scope_identity(self):
        if not self.scope.exists():return False
        info=self.scope.stat();require(self.scope.resolve()==self.scope and (info.st_dev,info.st_ino)==(self.record['dev'],self.record['ino']),'controller scope identity changed')
        require(not any(p.is_dir() for p in self.scope.iterdir()),'unexpected controller descendant cgroup')
        return True

    def process(self,pid):
        root=self.proc/str(pid)
        groups=(root/'cgroup').read_text();require(len(groups)<4096 and groups=='0::'+self.record['cgroup']+'\n','process left original scope')
        rows=[line.split()[1:] for line in (root/'status').read_text().splitlines() if line.startswith('Uid:')]
        require(len(rows)==1 and len(rows[0])==4)
        sudo_monitor=rows[0]==[str(self.record['uid']),'0','0','0']
        require(sudo_monitor or len(set(rows[0]))==1)
        uid=0 if sudo_monitor else int(rows[0][0]);require(uid in (0,self.record['uid']))
        if uid==0:
            args=(root/'cmdline').read_bytes();require(len(args)<=32768)
            fields=args.split(b'\0');require(fields[0] in (b'/usr/bin/sudo',b'sudo',b'/usr/bin/systemd-run',b'systemd-run')
                    and ('--unit='+self.record['guardian_unit']).encode() in fields,'unrecognized root scope member')
            if sudo_monitor:
                require(fields[0] in (b'/usr/bin/sudo',b'sudo')
                    and fields[1:5]==[b'-n',b'/usr/bin/systemd-run',b'--system',b'--pipe'],'unrecognized sudo monitor')
        return uid  # A privileged monitor can never authenticate as the Sat controller/RPC peer.

    def alive(self):
        try:
            raw=(self.proc/str(self.record['pid'])/'stat').read_text();require(len(raw)<=4096)
        except FileNotFoundError:return False
        fields=raw[raw.rfind(')')+2:].split();require(len(fields)>=20)
        if int(fields[19])!=self.record['starttime']:return False
        require(self.process(self.record['pid'])==self.record['uid'])
        require(self.scope_identity(),'original controller scope disappeared')
        return True

    def verify_context(self,mode,phase=None,*,deadline=None):
        """Closed allocation states for this exact admitted unit and invocation."""
        import os,subprocess
        check_deadline(deadline)
        require(mode in ('qualification','lifecycle-proof') and self.alive());check_deadline(deadline)
        if mode=='lifecycle-proof':
            require(phase is None);tasks={'96'};memory='1073741824'
        else:
            require(phase in ('admitted',*WORKLOAD_PHASES));memory='1073741824'
            tasks=({'32','60'} if phase=='browser-ready' else {'64'} if phase=='admitted'
                else {'60'} if phase=='browser' else {'32'})
        manager_env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/1000',DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus')
        raw=subprocess.check_output(['/usr/bin/systemctl','--user','show','-p','InvocationID','-p','ControlGroup','-p','TasksMax',self.record['unit']],text=True,timeout=deadline.timeout(5) if deadline is not None else 5,env=manager_env)
        check_deadline(deadline)
        rows=[line.split('=',1) for line in raw.splitlines()]
        require(all(len(row)==2 for row in rows) and len(rows)==3 and len({row[0] for row in rows})==3)
        manager=dict(rows)
        require(set(manager)=={'InvocationID','ControlGroup','TasksMax'} and manager['InvocationID']==self.record['invocation']
                and manager['ControlGroup']==self.record['cgroup'],'controller manager identity changed')
        kernel=(self.scope/'pids.max').read_text().strip()
        require(manager['TasksMax'] in tasks and kernel in tasks,'controller phase task cap differs')
        # During browser-ready only, systemd may have applied one side of the
        # fixed32->60 handoff. Both retired reservations already remain revoked.
        if phase!='browser-ready':require(manager['TasksMax']==kernel)
        for path,expected in [(self.scope/'memory.max',memory),(self.scope/'memory.swap.max','0'),
                (self.scope.parent/'memory.max','6442450944'),(self.scope.parent/'memory.swap.max','0'),
                (self.scope.parent/'pids.max','256'),(self.scope.parent/'cpu.max','800000 100000')]:
            require(path.read_text().strip()==expected,'controller or pool hard cap differs')
        quota,period=(self.scope/'cpu.max').read_text().split()
        require(quota.isdecimal() and period.isdecimal() and int(period)>0 and int(quota)==2*int(period))
        require(self.alive(),'controller identity changed during readback')
        check_deadline(deadline)
        return {'phase':phase,'manager_tasks':manager['TasksMax'],'kernel_tasks':kernel,'invocation':manager['InvocationID'],'cgroup':manager['ControlGroup']}

    def python_exited(self,*,deadline=None):
        """The main controller and its owned root launch clients alone remain."""
        check_deadline(deadline);require(self.alive());check_deadline(deadline)
        pids=(self.scope/'cgroup.procs').read_text().split()
        require(0<len(pids)<=60 and len(set(pids))==len(pids) and all(p.isdecimal() for p in pids))
        require(str(self.record['pid']) in pids)
        for pid in map(int,pids):
            require(pid==self.record['pid'] or self.process(pid)==0,'Python workload has not exited')
            check_deadline(deadline)

    def populated(self):
        if not self.scope_identity():return False
        entries=[line.split() for line in (self.scope/'cgroup.events').read_text().splitlines()]
        require(all(len(row)==2 for row in entries) and len({row[0] for row in entries})==len(entries))
        values=dict(entries);require(values.get('populated') in ('0','1'))
        return values['populated']=='1'

    def kill(self,directory):
        import os
        require(directory==self.scope and self.scope_identity())
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            info=os.fstat(fd);require((info.st_dev,info.st_ino)==(self.record['dev'],self.record['ino']))
            child=os.open('cgroup.kill',os.O_WRONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            try:require(os.write(child,b'1\n')==2)
            finally:os.close(child)
        finally:os.close(fd)

    def quiesce(self):
        import time
        self.alive()  # A moved original process is ambiguous, not permission to kill elsewhere.
        if not self.populated():return
        pids=(self.scope/'cgroup.procs').read_text().split();require(len(pids)<=96 and all(p.isdecimal() for p in pids))
        for pid in pids:
            try:self.process(int(pid))
            except FileNotFoundError:pass  # Exited member; cgroup.kill never targets a numeric PID.
        self.kill(self.scope)
        deadline=time.monotonic()+15
        while self.populated():
            require(time.monotonic()<deadline,'controller cleanup not quiescent');time.sleep(.05)


def container_caps(service,identity,container,*,cgroup_root=Path('/sys/fs/cgroup'),proc_root=Path('/proc')):
    require(service in CAPS and re.fullmatch('[a-f0-9]{64}',identity))
    require(container['Id']==identity and container['State']['Running'] is True and type(container['State']['Pid']) is int and container['State']['Pid']>1)
    relative='/system.slice/docker-'+identity+'.scope'
    require((Path(proc_root)/str(container['State']['Pid'])/'cgroup').read_text()=='0::'+relative+'\n')
    path=Path(cgroup_root)/relative.lstrip('/');require(path.resolve()==path)
    memory,cpu,tasks=CAPS[service]
    values={name:(path/name).read_text().strip() for name in ['memory.max','memory.swap.max','pids.max','cpu.max',
        'memory.current','memory.peak','pids.current','memory.events','pids.events']}
    require(values['memory.max']==str(memory*1024**2) and values['memory.swap.max']=='0' and values['pids.max']==str(tasks))
    quota,period=values['cpu.max'].split();require(quota.isdecimal() and period.isdecimal() and int(period)>0 and int(quota)*4==int(cpu*4)*int(period))
    return {'id':identity,'cgroup':relative,**values}


class RequestHandler:
    """No creation, exec, arbitrary ID, generic HTTP or shell command protocol."""
    def __init__(self,state,*,controller,manifest_digest,lease_check,mode='qualification',after_action=lambda service:None,lease_end=None):
        require(mode in ('qualification','lifecycle-proof') and state.docker.mode==mode);self.mode=mode
        self.state=state;self.controller=controller;self.manifest_digest=manifest_digest;self.lease_check=lease_check;self.after_action=after_action
        self.lease_end=lease_end

    def request(self,payload,peer,*,deadline=None):
        started=time.monotonic()  # Direct callers also spend precheck time from entry.
        if type(payload) is dict and payload.get('operation') in PHASE_REQUESTS:
            require(self.mode=='qualification' and self.state.mode=='qualification'
                    and set(payload)=={'operation','manifest_sha256'},'qualification phase authority required')
            end=min(started+30,self.lease_end) if self.lease_end is not None else started+30
            if deadline is None:deadline=PhaseDeadline(end)
            require(isinstance(deadline,PhaseDeadline) and deadline.end<=end,'original transport deadline required')
            with phase_scope(deadline):
                answer=self._request(payload,peer,deadline=deadline);deadline.check();return answer
        require(deadline is None,'phase deadline on ordinary operation')
        return self._request(payload,peer)

    def _request(self,payload,peer,*,deadline=None):
        check_deadline(deadline)
        require(type(payload) is dict and peer[1]==self.controller.record['uid'] and self.controller.alive())
        check_deadline(deadline)
        require(self.controller.process(peer[0])==self.controller.record['uid'])
        check_deadline(deadline)
        require(payload.get('manifest_sha256')==self.manifest_digest)
        if deadline is not None:self.lease_check(deadline=deadline)
        else:self.lease_check()
        check_deadline(deadline)
        if payload.get('operation')=='hello':
            require(set(payload)=={'operation','manifest_sha256'} and peer[0]==self.controller.record['pid'])
            return {'ready':True}
        if payload.get('operation') in PHASE_REQUESTS:
            require(self.mode=='qualification' and self.state.mode=='qualification'
                    and set(payload)=={'operation','manifest_sha256'} and peer[0]==self.controller.record['pid'])
            operation=payload['operation']
            self.controller.verify_context('qualification','browser' if operation=='enter-browser' else self.state.state['workload_phase'],deadline=deadline)
            check_deadline(deadline)
            if operation=='retire-chirpstack-for-browser':self.controller.python_exited(deadline=deadline);check_deadline(deadline)
            return self.state.transition(operation,deadline=deadline)
        require(payload.get('operation')=='lifecycle' and set(payload)=={'operation','manifest_sha256','action','service'})
        require(self.mode!='lifecycle-proof' or payload['service']=='mqtt','proof mode permits only MQTT lifecycle')
        self.state.action(payload['action'],payload['service'])
        if payload['action'] in ('start','restart'):self.after_action(payload['service'])
        returncode=0
        if payload['service']=='simulator':
            result=self.state.docker.request('POST','/containers/'+self.state.state['ids']['simulator']+'/wait?condition=not-running')
            require(type(result) is dict and type(result.get('StatusCode')) is int and not result.get('Error'))
            returncode=result['StatusCode']
        return {'returncode':returncode,'stdout':'','stderr':''}


def serve_request(server,handler,*,lease_check,lease_end,mode):
    """One continuing-check/accept pass; a timeout without a request may retry."""
    import json,socket,struct
    from services.lorawan.tests.qualification_guard import decode
    require(mode in ('qualification','lifecycle-proof'))
    deadline=PhaseDeadline(min(time.monotonic()+30,lease_end)) if mode=='qualification' else None
    connection=None
    try:
        with phase_scope(deadline):
            if deadline is None:lease_check()
            else:lease_check(deadline=deadline)
            check_deadline(deadline)
            try:connection,_=server.accept()
            except socket.timeout:return
            accepted_at=time.monotonic()
            # The pass started earlier than accept. Its end is therefore also
            # the earlier of accepted_at+30, the check-pass end and the lease.
            if deadline is not None:require(deadline.end<=min(accepted_at+30,lease_end));deadline.check()
            connection.settimeout(deadline.timeout(35) if deadline is not None else 35)
            peer=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));check_deadline(deadline)
            raw,ancillary,flags,_=connection.recvmsg(8193,0);check_deadline(deadline)
            require(not ancillary and not flags & (socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(raw)<=8192)
            payload=decode(raw);check_deadline(deadline)
            if type(payload) is dict and payload.get('operation') in PHASE_REQUESTS:
                answer=handler.request(payload,peer,deadline=deadline)
                raw=json.dumps(answer,separators=(',',':')).encode();check_deadline(deadline)
                connection.settimeout(deadline.timeout(35) if deadline is not None else 35);check_deadline(deadline)
                connection.sendall(raw);check_deadline(deadline)
                return
        # The phase-only scope ends before the unchanged ordinary operations.
        connection.settimeout(35)
        answer=handler.request(payload,peer)
        connection.sendall(json.dumps(answer,separators=(',',':')).encode())
    finally:
        if connection is not None:connection.close()


class Lease:
    """Immutable root/nonce/source/boot binding; expiry never authorizes starts."""
    def __init__(self,path,digest,*,root,nonce,boot_id,clock):
        self.path=Path(path);self.digest=digest;self.root=Path(root);self.nonce=nonce;self.boot_id=boot_id;self.clock=clock
        require(re.fullmatch('[a-f0-9]{64}',digest))

    def verify(self,*,allow_expired=False):
        import os,stat,math
        from services.lorawan.tests.qualification_guard import decode
        require(self.path.resolve()==self.path)
        fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            info=os.fstat(fd);require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
            raw=os.read(fd,1048577);require(len(raw)<=1048576 and sha256(raw).hexdigest()==self.digest)
            value=decode(raw,limit=1048576)
        finally:os.close(fd)
        require(set(value)=={'schema','mode','late_request_proof','stack','controller','lock','source_root','sources','boot_id','deadline'})
        require(value['mode'] in ('qualification','lifecycle-proof') and type(value['late_request_proof']) is bool
                and (not value['late_request_proof'] or value['mode']=='lifecycle-proof'))
        require(value['schema']=='earthship-sensor-admission/v1' and value['stack']['root']==str(self.root)
                and value['stack']['nonce']==self.nonce and value['boot_id']==self.boot_id)
        require(type(value['deadline']) in (int,float) and math.isfinite(value['deadline']) and value['deadline']>0)
        if not allow_expired:require(self.clock()<value['deadline'],'original qualification deadline expired')
        source=Path(value['source_root']);require(source.is_absolute() and source.resolve()==source)
        require(set(value['sources'])=={'qualification_guard.py','qualification_runtime.py','stack_ownership.py'})
        for name,digest in value['sources'].items():
            path=source/name;info=path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and not info.st_mode & 0o022 and info.st_nlink==1 and path.resolve()==path)
            require(re.fullmatch('[a-f0-9]{64}',digest) and info.st_size<=262144 and sha256(path.read_bytes()).hexdigest()==digest,'guardian source changed')
        return value

    def verify_mode(self,mode,*,allow_expired=False):
        require(mode in ('qualification','lifecycle-proof'))
        value=self.verify(allow_expired=allow_expired)
        require(value['mode']==mode,'guardian mode differs from immutable manifest')
        return value


def check_service_context(unit,*,mode='lifecycle-proof',proc_root=Path('/proc'),cgroup_root=Path('/sys/fs/cgroup'),deadline=None):
    import os,subprocess
    check_deadline(deadline)
    require(mode in ('qualification','lifecycle-proof'))
    tasks='8' if mode=='qualification' else '16'
    require(os.getuid()==1000 and re.fullmatch('earthship-sensor-guard-[a-f0-9]{32}\\.service',unit))
    relative='/system.slice/'+unit
    require((Path(proc_root)/'self/cgroup').read_text()=='0::'+relative+'\n','system-manager guardian context required')
    path=Path(cgroup_root)/relative.lstrip('/');require(path.resolve()==path)
    for name,expected in [('memory.max',str(64*1024**2)),('memory.swap.max','0'),('pids.max',tasks)]:
        require((path/name).read_text().strip()==expected,'guardian hard cap differs')
    cpu=(path/'cpu.max').read_text().split()
    require(len(cpu)==2 and all(value.isdecimal() for value in cpu) and int(cpu[0])*2==int(cpu[1]) and int(cpu[1])>0,'guardian CPU cap differs')
    manager_tasks=subprocess.check_output(['/usr/bin/systemctl','show','--value','-p','TasksMax',unit],text=True,timeout=deadline.timeout(5) if deadline is not None else 5).strip()
    check_deadline(deadline)
    require(manager_tasks==tasks,'guardian manager task cap differs')
    return path


def fdstore_count(unit,*,deadline=None):
    import subprocess
    check_deadline(deadline)
    result=subprocess.run(['/usr/bin/systemctl','show','--value','--property=NFileDescriptorStore',unit],check=True,capture_output=True,text=True,timeout=deadline.timeout(5) if deadline is not None else 5)
    check_deadline(deadline)
    require(result.stdout.strip() in ('0','1'));return int(result.stdout.strip())


def docker_cgroup_empty(identity,*,cgroup_root=Path('/sys/fs/cgroup')):
    require(re.fullmatch('[a-f0-9]{64}',identity))
    path=Path(cgroup_root)/'system.slice'/('docker-'+identity+'.scope')
    try:path.lstat()
    except FileNotFoundError:return True
    require(path.resolve()==path)
    rows=[line.split() for line in (path/'cgroup.events').read_text().splitlines()]
    require(all(len(row)==2 for row in rows) and len({row[0] for row in rows})==len(rows))
    entries=dict(rows)
    require(entries.get('populated') in ('0','1'))
    tasks=(path/'pids.current').read_text().strip();require(tasks.isdecimal())
    return entries['populated']=='0' and tasks=='0'


def run_owned_session(operation,state,failure_path):
    """A released lease must exit successfully; failed cleanup must restart."""
    from services.lorawan.tests.qualification_guard import persist
    try:
        operation()
    except Exception:
        # Do not publish request content, and never let diagnostic I/O prevent
        # cleanup. The test controller retains its own command/result failure.
        try:persist(failure_path,{'request_failed':True})
        except Exception:pass
    state.cleanup()  # Failure propagates with the real admission FD retained.
    return 0


def recover_owned_session(state,notifier):
    """Validated recovered ownership is cleanup-only, but still Type=notify."""
    require(state.recovered)
    notifier('READY=1');notifier.barrier()
    state.cleanup()  # Failure propagates; the stored real admission FD remains.
    return 0


def service_main(argv=None):
    """Fixed system-manager entrypoint. Installed-version proof is mandatory."""
    import argparse,errno,os,signal,socket,stat,struct,subprocess,time
    from services.lorawan.tests import qualification_guard as protocol
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--sha256',required=True)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--nonce',required=True)
    parser.add_argument('--mode',required=True,choices=['qualification','lifecycle-proof'])
    args=parser.parse_args(argv)
    require(re.fullmatch('[a-f0-9]{32}',args.nonce))
    unit='earthship-sensor-guard-'+args.nonce+'.service';check_service_context(unit,mode=args.mode)
    collect=subprocess.check_output(['/usr/bin/systemctl','show','--value','-p','CollectMode',unit],text=True,timeout=5).strip()
    require(collect=='inactive','failed units must remain loaded on systemd259')
    inherited=protocol.inherited_descriptor(os.environ);fd=0 if inherited is None else inherited
    lock=Path('/run/user/1000/earthship-job-admission.lock');info=os.fstat(fd);identity=(info.st_dev,info.st_ino)
    protocol.verify_lock(lock,fd,uid=1000,identity=identity)
    notifier=SystemdNotify(os.environ.get('NOTIFY_SOCKET',''))
    def count(*,deadline=None):return fdstore_count(unit,deadline=deadline)
    store=protocol.FdStore(notify=notifier,barrier=notifier.barrier,count=count)
    if inherited is None:store.pin(fd)
    else:notifier.barrier();require(count()==1,'inherited descriptor not retained by PID1')
    # From here every failure retains PID1's descriptor and prevents unit GC.
    runtime=Path('/run')/('earthship-sensor-guard-'+args.nonce);directory=runtime.lstat()
    require(runtime.resolve()==runtime and stat.S_ISDIR(directory.st_mode) and directory.st_uid==1000 and stat.S_IMODE(directory.st_mode)==0o700)
    lease=Lease(args.manifest,args.sha256,root=args.root,nonce=args.nonce,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),clock=time.monotonic)
    envelope=lease.verify_mode(args.mode,allow_expired=True)
    require(envelope['lock']=={'path':str(lock),'dev':identity[0],'ino':identity[1]})
    source=Path(envelope['source_root']);require(Path(__file__).resolve()==source/'qualification_runtime.py'
        and Path(protocol.__file__).resolve()==source/'qualification_guard.py')
    from services.lorawan.tests import stack_ownership
    require(Path(stack_ownership.__file__).resolve()==source/'stack_ownership.py')
    controller=Controller(envelope['controller']);require(controller.record['guardian_unit']==unit)
    def request_sent(method,path):
        # Fixed StageB fault witness, never enabled for actual qualification.
        marker=runtime/'late-request-sent.json'
        identity=envelope['stack']['containers']['mqtt']['Id']
        if envelope['late_request_proof'] and method=='POST' and path=='/containers/'+identity+'/start' and not marker.exists():
            protocol.persist(marker,{'manifest_sha256':args.sha256,'id':identity,'sent_at':time.monotonic(),'hold_seconds':10})
            time.sleep(10)
    docker=DockerBackend(envelope['stack'],request=DockerSocket(after_request=request_sent),cgroup_empty=docker_cgroup_empty,mode=envelope['mode'])
    original_configuration=docker.configuration
    def checked_configuration():lease.verify_mode(args.mode,allow_expired=True);original_configuration()
    docker.configuration=checked_configuration
    def release():
        lease.verify_mode(args.mode,allow_expired=True);check_service_context(unit,mode=args.mode)
        protocol.verify_lock(lock,fd,uid=1000,identity=identity)
        store.release()  # Recheck independent flock release after process exit/GC.
    receipt=runtime/'receipt.json'
    require(inherited is None or receipt.exists(),'recovered FD without matching receipt requires reconciliation')
    state=protocol.GuardianState(receipt,manifest_digest=args.sha256,docker=docker,quiesce=controller.quiesce,release=release)
    if state.recovered:
        return recover_owned_session(state,notifier)
    controller.verify_context(args.mode,'python' if args.mode=='qualification' else None)
    state.register(docker.ids)
    for container_id in docker.ids.values():
        require(docker.request('GET','/containers/'+container_id+'/json')['State']['Running'] is False,'fixture started before FDStore acknowledgement')
    def lease_check(*,deadline=None):
        check_deadline(deadline)
        lease.verify_mode(args.mode);check_deadline(deadline)
        protocol.verify_lock(lock,fd,uid=1000,identity=identity);check_deadline(deadline)
        require(count(deadline=deadline)==1);check_deadline(deadline)
        check_service_context(unit,mode=args.mode,deadline=deadline);check_deadline(deadline)
        controller.verify_context(args.mode,state.state.get('workload_phase'),deadline=deadline);check_deadline(deadline)
        state.check_retired(deadline=deadline);check_deadline(deadline)
    def measured(service):
        path=runtime/'container-caps.json'
        values=protocol.read_private(path) if path.exists() else {}
        require(type(values) is dict and set(values)<=set(SERVICES))
        identity=docker.ids[service]
        values[service]=container_caps(service,identity,docker.request('GET','/containers/'+identity+'/json'))
        protocol.persist(path,values)
    handler=RequestHandler(state,controller=controller,manifest_digest=args.sha256,lease_check=lease_check,mode=envelope['mode'],after_action=measured,lease_end=envelope['deadline'])
    address=runtime/'control.sock'
    if address.exists():
        old=address.lstat();require(stat.S_ISSOCK(old.st_mode) and old.st_uid==1000)
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as probe:
            probe.settimeout(1);require(probe.connect_ex(str(address))==errno.ECONNREFUSED,'active or unknown prior control socket')
        current=address.lstat();require((old.st_dev,old.st_ino)==(current.st_dev,current.st_ino));address.unlink()
    stop=False
    def stopping(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
    def serve():
        with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as server:
            server.bind(str(address));address.chmod(0o600);server.listen(4);server.settimeout(.5)
            deadline=PhaseDeadline(min(time.monotonic()+30,envelope['deadline'])) if args.mode=='qualification' else None
            with phase_scope(deadline):
                lease_check(deadline=deadline);notifier('READY=1');notifier.barrier()
            while not stop and time.monotonic()<envelope['deadline'] and (args.mode=='qualification' or controller.alive()):
                serve_request(server,handler,lease_check=lease_check,lease_end=envelope['deadline'],mode=args.mode)
    return run_owned_session(serve,state,runtime/'request-failure.json')


if __name__=='__main__':
    import sys
    try:raise SystemExit(service_main())
    except Exception:
        print('Sensor guardian requires owned-state reconciliation; admission remains retained.',file=sys.stderr)
        raise SystemExit(1)
