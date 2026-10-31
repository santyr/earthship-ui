"""Run-specific controller for the actual isolated sensor qualification.

Only the fixed MQTT proof or actual11Python+2browser selection is exposed.
Nothing runs at import. Parent must approve the staged operational handoff.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import time
from urllib.parse import quote
from services.lorawan.tests.qualification_guard import require,persist,read_private,verify_lock,SERVICES
from services.lorawan.tests.qualification_runtime import DockerBackend,DockerSocket,Controller,container_caps,docker_cgroup_empty
from services.lorawan.tests.qualification_controller import guardian_command,freeze_sources,precreate
from services.lorawan.tests.stack_ownership import PROJECT,CAPS,VOLUMES,PORTS,RUNTIME_IMAGE,_sources,rendered_memory_bytes

ROOT=Path('/home/sat/earthship-ui/.worktrees/post-upgrade-repairs-20261024')
PYTHON=Path('/home/sat/earthship-ui/artifacts/weathernext3-capabilities.local/supported-environment-20261023T060710631462Z/bin/python3.12')
NODE=Path('/home/sat/earthship-ui/artifacts/weathernext3-capabilities.local/node-runtime-1bec56ef7cfa9a76/node')
WHEEL=Path('/home/sat/earthship-ui/artifacts/post-upgrade-repairs-20261024.local/sensor-test-deps/paho_mqtt-2.1.0-py3-none-any.whl')


def profile(mode):
    require(mode in ('lifecycle-proof','qualification'))
    if mode=='lifecycle-proof':return {'controller_mib':1024,'controller_tasks':96,'external_mib':128,'services':('mqtt',)}
    # These allocations are provisional. Actual full tests and resource events decide.
    return {'controller_mib':512,'controller_tasks':64,'external_mib':2112,'services':('mqtt','postgres','redis','openhab','chirpstack','ingest')}


def verify_controller_caps(scope,pool,mode):
    """Require the fixed mode allocation before any controller side effect."""
    plan=profile(mode)
    for path,expected in [(scope/'memory.max',str(plan['controller_mib']*1024**2)),(scope/'memory.swap.max','0'),
            (scope/'pids.max',str(plan['controller_tasks'])),(pool/'memory.max','6442450944'),
            (pool/'memory.swap.max','0'),(pool/'pids.max','256'),(pool/'cpu.max','800000 100000')]:
        require(path.read_text().strip()==expected)


def prepare_python_controller(controller):
    admitted=controller.verify_context('qualification','admitted')
    subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',controller.record['unit'],'TasksMax=48'],check=True,timeout=5)
    return {'admitted':admitted,'python':controller.verify_context('qualification','python')}


def restore_browser_controller(controller):
    controller.verify_context('qualification','browser-ready')
    subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',controller.record['unit'],'TasksMax=64'],check=True,timeout=5)
    return controller.verify_context('qualification','browser')


def event_counters(raw):
    rows=[line.split() for line in raw.splitlines()]
    require(rows and all(len(row)==2 and row[1].isdecimal() for row in rows) and len({row[0] for row in rows})==len(rows),'malformed resource events')
    return {name:int(value) for name,value in rows}


def verify_resource_events(scope,pool,baseline):
    for path,key in [(scope/'memory.events','memory_events'),(scope/'pids.events','pids_events'),
                     (pool/'memory.events','pool_events'),(pool/'pids.events','pool_pids_events')]:
        require(event_counters(path.read_text())==event_counters(baseline[key]),'resource events changed during qualification')


def enter_browser_phase(child,xml,*,request,restore):
    """Source-bound success gate; never retries any lost phase reply."""
    import xml.etree.ElementTree as ET
    require(child.poll()==0 and child.returncode==0,'Python child must have exited successfully')
    suites=ET.parse(xml).getroot();require(suites.tag in ('testsuites','testsuite'))
    rows=list(suites) if suites.tag=='testsuites' else [suites]
    require(rows and all(row.tag=='testsuite' for row in rows))
    require(sum(int(row.attrib['tests']) for row in rows)==11 and
        all(int(row.attrib.get(key,0))==0 for row in rows for key in ['failures','errors','skipped']))
    cases=[case for row in rows for case in row.findall('testcase')]
    require(len(cases)==11 and len({(case.get('classname'),case.get('name')) for case in cases})==11 and
        all(case.get('name') and not any(case.find(tag) is not None for tag in ('failure','error','skipped')) for case in cases),'incomplete Python result')
    require(request('retire-chirpstack-for-browser')=={'workload_phase':'chirpstack-retired'})
    require(request('retire-redis-for-browser')=={'workload_phase':'browser-ready'})
    restore()
    require(request('enter-browser')=={'workload_phase':'browser'})


def capture_stopped(root,nonce,rendered,*,request):
    root=Path(root);containers={}
    for service in SERVICES:
        value=request('GET','/containers/'+PROJECT+'-'+service+'-1/json')
        require(value is not None and value['State']['Running'] is False and value['State']['Pid']==0)
        containers[service]=value
    networks={name:request('GET','/networks/'+name)['Id'] for name in [PROJECT+'_sensors',PROJECT+'_management']}
    volumes={name:request('GET','/volumes/'+name) for name in {n for values in VOLUMES.values() for n in values.values()}}
    images={spec['image']:request('GET','/images/'+quote(spec['image'],safe='')+'/json')['Id'] for spec in rendered['services'].values()}
    result={'schema':'earthship-sensor-qualification/v1','nonce':nonce,'root':str(root),
        'compose_sha256':sha256((root/'deploy/lorawan/compose.test.yaml').read_bytes()).hexdigest(),
        'rendered':rendered,'containers':containers,'images':images,'networks':networks,'volumes':volumes}
    backend=DockerBackend(result,request=request,cgroup_empty=lambda _:False)
    backend.validate(backend.ids)
    return result


def precreate_inventory(root,nonce,rendered,request):
    """Read-only refusal before Compose can reuse any existing fixture identity."""
    names={PROJECT+'-'+service+'-1' for service in SERVICES}
    volumes={name for values in VOLUMES.values() for name in values.values()}
    inventory=request('GET','/containers/json?all=1');require(len(inventory)<=256)
    before=[]
    for summary in inventory:
        value=request('GET','/containers/'+summary['Id']+'/json')
        require(value is not None and value['Name'].removeprefix('/') not in names
                and value['Config']['Labels'].get('com.docker.compose.project')!=PROJECT,'existing fixture requires reconciliation')
        require(not any(m['Type']=='volume' and m.get('Name') in volumes for m in value['Mounts']),'retained volume has a consumer')
        before.append({key:value[key] for key in ['Id','Name','Image','Config','HostConfig','Mounts']}|{'running':value['State']['Running']})
    for name in volumes:
        value=request('GET','/volumes/'+name)
        require(value['Name']==name and value['Driver']=='local' and value.get('Options') in (None,{})
            and value['Labels'].get('com.docker.compose.project')==PROJECT
            and value['Labels'].get('com.docker.compose.volume')==name.removeprefix(PROJECT+'_'))
    for value in request('GET','/networks'):
        if value['Name'] in (PROJECT+'_sensors',PROJECT+'_management'):
            require(value['Driver']=='bridge' and value['Labels'].get('com.docker.compose.project')==PROJECT
                    and value['Internal']==value['Name'].endswith('_sensors'))
    for spec in rendered['services'].values():
        value=request('GET','/images/'+quote(spec['image'],safe='')+'/json')
        require(re.fullmatch('sha256:[a-f0-9]{64}',value['Id']))
    private=Path(root)/'.superpowers/lorawan-private'
    require(private.is_dir() and private.resolve()==private and private.stat().st_uid==1000 and private.stat().st_mode & 0o777==0o700)
    require(set(rendered['services'])==set(SERVICES))
    for service,spec in rendered['services'].items():
        memory,cpu,tasks=CAPS[service]
        require(rendered_memory_bytes(spec.get('mem_limit'))==memory*1024**2 and rendered_memory_bytes(spec.get('memswap_limit'))==memory*1024**2
            and float(spec.get('cpus',0))==cpu and spec.get('pids_limit')==tasks and spec.get('restart')=='no' and 'build' not in spec)
        require(spec.get('labels',{}).get('org.earthship.sensor.qualification')==nonce)
        require(set(spec['networks'])==({'sensors','management'} if service in PORTS else {'sensors'}))
        require({m['target']:m['source'] for m in spec.get('volumes',[]) if m['type']=='bind'}==_sources(Path(root),service))
        require({m['target']:rendered['volumes'][m['source']]['name'] for m in spec.get('volumes',[]) if m['type']=='volume'}==VOLUMES.get(service,{}))
        ports={str(p['target'])+'/tcp':(p['host_ip'],str(p['published'])) for p in spec.get('ports',[])}
        require(ports==({PORTS[service][0]:('127.0.0.1',PORTS[service][1])} if service in PORTS else {}))
        require(spec['image']==RUNTIME_IMAGE if service in ('ingest','simulator') else re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}',spec['image']))
        for mount in spec.get('volumes',[]):
            if mount['type']=='bind':
                path=Path(mount['source']);require(path.exists() and path.resolve()==path,'missing or aliased original fixture input')
    # A current bind collision must refuse before create intents or the guardian.
    # Close every probe; a later race still requires conservative reconciliation.
    for _,published in PORTS.values():
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                probe.bind(('127.0.0.1',int(published)))
        except OSError:
            require(False,'loopback TCP test port unavailable: 127.0.0.1:'+published)
    return before


def control(directory,nonce,digest,operation,*,action=None,service=None,lose_reply=False):
    """Closed local request, no generic Docker path or command interface."""
    unit='earthship-sensor-guard-'+nonce+'.service'
    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(30);connection.connect('/run/earthship-sensor-guard-'+nonce+'/control.sock')
        pid,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require(uid==1000 and Path('/proc',str(pid),'cgroup').read_text()=='0::/system.slice/'+unit+'\n')
        payload={'operation':operation,'manifest_sha256':digest}
        if operation=='lifecycle':payload.update(action=action,service=service)
        connection.sendall(json.dumps(payload,separators=(',',':')).encode())
        if lose_reply:return None
        raw,ancillary,flags,_=connection.recvmsg(8193,0)
        require(not ancillary and not flags & (socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(raw)<=8192)
        from services.lorawan.tests.qualification_guard import decode
        return decode(raw)


def main(argv=None):
    import argparse,fcntl,stat,sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,type=Path);parser.add_argument('--nonce',required=True)
    parser.add_argument('--mode',required=True,choices=['lifecycle-proof','qualification'])
    parser.add_argument('--late-request-proof',action='store_true')
    args=parser.parse_args(argv);require(not args.late_request_proof or args.mode=='lifecycle-proof');plan=profile(args.mode);directory=args.directory
    require(Path.cwd().resolve()==ROOT and re.fullmatch('[a-f0-9]{32}',args.nonce) and directory.is_absolute() and directory.resolve()==directory)
    require(os.getuid()==1000 and Path(sys.executable)==PYTHON and os.environ.get('PYTHONDONTWRITEBYTECODE')=='1')
    relative=Path('/proc/self/cgroup').read_text().strip().removeprefix('0::')
    prefix='/user.slice/user-1000.slice/user@1000.service/earthship.slice/earthship-work.slice/'
    require(relative.startswith(prefix) and re.fullmatch(r'earthship-job-[a-f0-9]{32}\.scope',relative[len(prefix):]))
    unit=relative[len(prefix):];scope=Path('/sys/fs/cgroup')/relative.lstrip('/');pool=scope.parent
    verify_controller_caps(scope,pool,args.mode)
    subprocess.run(['/usr/bin/systemctl','--user','set-property','--runtime',unit,'CPUQuota=200%'],check=True,timeout=5)
    quota,period=(scope/'cpu.max').read_text().split();require(int(quota)==2*int(period))
    info=scope.stat();start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
    invocation=subprocess.check_output(['/usr/bin/systemctl','--user','show','--value','-p','InvocationID',unit],text=True,timeout=5).strip()
    require(re.fullmatch('[a-f0-9]{32}',invocation))
    actor=Controller({'pid':os.getpid(),'starttime':start,'uid':1000,'cgroup':relative,'dev':info.st_dev,'ino':info.st_ino,
        'unit':unit,'invocation':invocation,'guardian_unit':'earthship-sensor-guard-'+args.nonce+'.service'})
    allocation=prepare_python_controller(actor) if args.mode=='qualification' else actor.verify_context('lifecycle-proof')
    directory.mkdir(mode=0o700);source=directory/'source';hashes=freeze_sources(Path(__file__).resolve().parent,source)
    persist(directory/'controller-allocation.json',allocation)
    env=dict(os.environ,SENSOR_INTEGRATION='1',SENSOR_QUALIFICATION_NONCE=args.nonce,PYTHONDONTWRITEBYTECODE='1',
        SENSOR_TEST_PYTHON=str(PYTHON),EARTHSHIP_TEST_PYTHON=str(PYTHON),TMPDIR='/home/sat/.es-task7-tmp',
        PYTHONPATH=str(ROOT)+os.pathsep+str(WHEEL))
    for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','RAYON_NUM_THREADS','ROLLDOWN_WORKER_THREADS','TOKIO_WORKER_THREADS','UV_THREADPOOL_SIZE']:env[name]='1'
    env['ROLLDOWN_MAX_BLOCKING_THREADS']='2';env.pop('NODE_OPTIONS',None)
    env['PATH']=str(NODE.parent)+os.pathsep+env.get('PATH','')
    def command(argv):
        return subprocess.run(argv,check=True,capture_output=True,text=True,env=env,timeout=120)
    lock=Path('/run/user/1000/earthship-job-admission.lock');fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        meta=os.fstat(fd);require(stat.S_ISREG(meta.st_mode) and meta.st_uid==1000 and stat.S_IMODE(meta.st_mode)==0o600 and meta.st_nlink==1)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 75
        verify_lock(lock,fd,uid=1000,identity=(meta.st_dev,meta.st_ino))
        def budget():
            verify_lock(lock,fd,uid=1000,identity=(meta.st_dev,meta.st_ino))
            require([p for p in pool.iterdir() if p.is_dir()]==[scope] and not (pool/'cgroup.procs').read_text().strip())
            residual=max(0,int((pool/'memory.current').read_text())-int((scope/'memory.current').read_text()))
            require(residual+(plan['controller_mib']+plan['external_mib']+256)*1024**2<=6144*1024**2,'original aggregate headroom lost')
            require((pool/'memory.swap.current').read_text().strip()=='0')
            memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
            require(int(memory['MemAvailable'].split()[0])*1024>=3*1024**3)
            return residual
        residual=budget()
        host_memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
        require(int(host_memory['MemAvailable'].split()[0])*1024 >= (3072+plan['controller_mib']+plan['external_mib'])*1024**2)
        docker=DockerSocket()
        compose=ROOT/'deploy/lorawan/compose.test.yaml';compose_bytes=compose.read_bytes()
        rendered=json.loads(command(['/snap/bin/docker','compose','-f',str(compose),'--profile','*','config','--format','json']).stdout)
        before=precreate_inventory(ROOT,args.nonce,rendered,docker);persist(directory/'production-before.json',before,limit=1048576)
        precreate(ROOT,args.nonce,directory/'create-intents.json',run=command)
        require(compose.read_bytes()==compose_bytes)
        stack=capture_stopped(ROOT,args.nonce,rendered,request=docker)
        intent=read_private(directory/'create-intents.json');intent.update(phase='recorded',ids={s:c['Id'] for s,c in stack['containers'].items()});persist(directory/'create-intents.json',intent)
        envelope={'schema':'earthship-sensor-admission/v1','mode':args.mode,'late_request_proof':args.late_request_proof,'stack':stack,
            'controller':actor.record,
            'lock':{'path':str(lock),'dev':meta.st_dev,'ino':meta.st_ino},'source_root':str(source/'services/lorawan/tests'),
            'sources':{name:hashes[name] for name in ['qualification_guard.py','qualification_runtime.py','stack_ownership.py']},
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'deadline':time.monotonic()+1800}
        manifest=directory/'manifest.json';persist(manifest,envelope,limit=1048576);digest=sha256(manifest.read_bytes()).hexdigest()
        env.update(SENSOR_QUALIFICATION_MANIFEST=str(manifest),SENSOR_QUALIFICATION_SHA256=digest)
        baseline={'residual_bytes':residual,'plan':plan,'memory_events':(scope/'memory.events').read_text(),
            'pids_events':(scope/'pids.events').read_text(),'pool_events':(pool/'memory.events').read_text(),'pool_pids_events':(pool/'pids.events').read_text()}
        persist(directory/'controller-baseline.json',baseline)
        budget()
        log=(directory/'guardian.log').open('xb')
        guardian=subprocess.Popen(guardian_command(python=PYTHON,source=source,manifest=manifest,digest=digest,root=ROOT,nonce=args.nonce,mode=args.mode),
            stdin=fd,stdout=log,stderr=log,close_fds=True)
        deadline=time.monotonic()+30
        while not Path('/run/earthship-sensor-guard-'+args.nonce+'/control.sock').exists():
            require(guardian.poll() is None and time.monotonic()<deadline);budget();time.sleep(.1)
        require(control(directory,args.nonce,digest,'hello')=={'ready':True})
        if args.mode=='lifecycle-proof':
            last=-1
            while True:
                budget();path=directory/'proof-command.json'
                if not path.exists():time.sleep(.1);continue
                task=read_private(path)
                require(set(task)=={'nonce','sequence','operation'} and task['nonce']==args.nonce and type(task['sequence']) is int and 0<=task['sequence']<=100)
                require(task['operation'] in ('start','stop','restart','lost-reply-start','exit'))
                if task['sequence']==last:time.sleep(.1);continue
                require(task['sequence']>last);last=task['sequence']
                persist(directory/'proof-command-receipt.json',task)
                if task['operation']=='exit':return 0
                operation=task['operation'];answer=control(directory,args.nonce,digest,'lifecycle',action='start' if operation=='lost-reply-start' else operation,
                    service='mqtt',lose_reply=operation=='lost-reply-start')
                if answer is not None:require(answer=={'returncode':0,'stdout':'','stderr':''})
        for service in plan['services']:
            budget();require(control(directory,args.nonce,digest,'lifecycle',action='start',service=service)=={'returncode':0,'stdout':'','stderr':''})
        require(sha256(WHEEL.read_bytes()).hexdigest()=='6db9ba9b34ed5bc6b6e3812718c7e06e2fd7444540df2455d2c51bd58808feee')
        def run_tests(argv,name):
            with (directory/(name+'.stdout')).open('xb') as output,(directory/(name+'.stderr')).open('xb') as error:
                child=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=output,stderr=error)
                while child.poll() is None:
                    budget();time.sleep(.5)
                require(child.returncode==0,name+' failed')
            measurements={}
            for service,identity in intent['ids'].items():
                value=docker('GET','/containers/'+identity+'/json')
                if value is not None and value['State']['Running']:
                    measurements[service]=container_caps(service,identity,value)
                    events=event_counters(measurements[service]['memory.events'])
                    pids=event_counters(measurements[service]['pids.events'])
                    require(all(value==0 for value in [*events.values(),*pids.values()]),'owned fixture resource failure')
            verify_resource_events(scope,pool,baseline)
            persist(directory/(name+'-resources.json'),{'containers':measurements,'controller':{key:(scope/key).read_text().strip()
                for key in ['memory.current','memory.peak','memory.events','pids.current','pids.events']}})
            return child
        python_child=run_tests([str(PYTHON),'-B','-m','pytest','-q','-p','no:cacheprovider','services/lorawan/tests/test_integration.py',
            '--basetemp='+str(directory/'pytest'),'--junitxml='+str(directory/'python.xml')],'python')
        retirement=DockerBackend(stack,request=docker,cgroup_empty=docker_cgroup_empty)
        transitions=[]
        def phase_request(operation):
            budget()
            answer=control(directory,args.nonce,digest,operation)
            expected={'retire-chirpstack-for-browser':'chirpstack-retired','retire-redis-for-browser':'browser-ready','enter-browser':'browser'}[operation]
            require(answer=={'workload_phase':expected})
            proofs=retirement.retired(('chirpstack',) if operation=='retire-chirpstack-for-browser' else ('chirpstack','redis'))
            transitions.append({'operation':operation,'acknowledgement':answer,'retired':proofs,
                'controller':actor.verify_context('qualification',expected),'manifest_sha256':digest})
            persist(directory/'browser-transition.json',transitions)
            return answer
        enter_browser_phase(python_child,directory/'python.xml',request=phase_request,restore=lambda:restore_browser_controller(actor))
        run_tests([str(NODE),str(ROOT/'node_modules/@playwright/test/cli.js'),'test','--project=sensors','--reporter=json','--output='+str(directory/'browser-results')],'browser')
        stats=json.loads((directory/'browser.stdout').read_text())['stats']
        require(stats['expected']==2 and all(stats[key]==0 for key in ['unexpected','skipped','flaky']))
        cap_receipt=read_private(Path('/run')/('earthship-sensor-guard-'+args.nonce)/'container-caps.json')
        require(set(cap_receipt)==set(SERVICES) and all(cap_receipt[name]['id']==intent['ids'][name] for name in SERVICES))
        persist(directory/'all-container-start-caps.json',cap_receipt)
        persist(directory/'test-result.json',{'python_passed':11,'browser_passed':2,'mode':args.mode,'manifest_sha256':digest})
        return 0
    finally:
        # Guardian detects controller exit, quiesces this exact scope/root client,
        # removes only the seven immutable IDs, then releases its stored OFD.
        os.close(fd)


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        import sys
        print('Sensor controller stopped; reconcile owned intents/guardian receipt before another attempt.',file=sys.stderr)
        raise SystemExit(1)
