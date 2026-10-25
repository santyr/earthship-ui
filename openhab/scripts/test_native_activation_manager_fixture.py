"""Private file-backed manager double used by independent recovery processes."""
from pathlib import Path
import json,os,sys,time
from hashlib import sha256
import household_native_lifecycle as life
import household_native_family as family
import household_native_install as install
import household_cycle_deploy as deploy


def configure(root):
    life.verify_manager_domain=lambda data:{'private_process_double':True}
    def timer(unit):return life.read(root/'timers.json')[unit]
    def systemctl(action,unit=None):
        if action=='daemon-reload':return ''
        assert action in ('stop','start') and unit in life.TIMERS
        rows=life.read(root/'timers.json');row=rows[unit];row['ActiveState']='inactive' if action=='stop' else 'active'
        row['InactiveEnterTimestampMonotonic']=str(int(row['InactiveEnterTimestampMonotonic'])+1)
        life.save(root/'timers.json',rows);return ''
    def verified(path,guard):
        guard();return {'deployment_sha256':'a'*64}
    def effective(path,guard):
        guard()
        assert life._matches(life._targets(root/'units',path))
        assert all(timer(u)['ActiveState']=='inactive' for u in life.TIMERS)
        return {'status':'native_effective_family_verified'}
    life._timer=timer;deploy._systemctl=systemctl;family.verify=verified;install._verify_effective_family=effective
    life._verify_family=lambda directory,path,effective=False: install._verify_effective_family(path,guard=lambda:None) if effective else family.verify(path,guard=lambda:None)


def main():
    root=Path(sys.argv[1]);configure(root)
    if sys.argv[2]=='watch':life.watch(root/'reservation')
    else:life.recover(root/'reservation')


if __name__=='__main__':main()


def manager_domain_fixture(tmp_path,monkeypatch):
    """Real canonical template bytes; only the private manager observations are doubled."""
    nonce='a'*32;unit='thermal-native-activation-owner@'+nonce+'.service'
    group=f'/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/earthship.slice/earthship-work.slice/'+unit
    template=tmp_path/'thermal-native-activation-owner@.service'
    template.write_bytes(b'[Service]\nExecStart=python -m household_native_lifecycle\n');template.chmod(0o600)
    state=dict(InvocationID='private-invocation',ControlGroup=group,ExecStart='python -m household_native_lifecycle',
        ExecStopPost='python -m household_native_lifecycle --recover',FragmentPath=str(template),DropInPaths='',
        MemoryMax='268435456',MemorySwapMax='0',TasksMax='24',KillMode='control-group',CPUQuotaPerSecUSec='200ms')
    original=Path.read_text
    def read_text(path,*args,**kwargs):
        if path==Path('/proc/self/cgroup'):return '0::'+group+'\n'
        if path==Path('/proc')/str(os.getpid())/'cgroup':return '0::/private-learner.scope\n'
        return original(path,*args,**kwargs)
    def show(action,requested,*properties):
        assert action=='show' and requested==unit
        return '\n'.join(k+'='+v for k,v in state.items())
    monkeypatch.setattr(Path,'read_text',read_text);monkeypatch.setattr(deploy,'_systemctl',show)
    monkeypatch.setenv('INVOCATION_ID','private-invocation')
    return {'nonce':nonce,'owner':[os.getpid(),'private-start','private-boot']},state,template


def test_actual_template_filename_fingerprint_and_manager_domain(tmp_path,monkeypatch):
    import pytest
    data,state,template=manager_domain_fixture(tmp_path,monkeypatch)
    expected=sha256(template.read_bytes()).hexdigest()
    result=life.verify_manager_domain(data)
    assert result==dict(invocation='private-invocation',fragment=str(template),definition=life.fingerprint(template))
    assert result['definition'][-1]==expected
    # The exact lifecycle exception must not relax the deployment-source contract.
    with pytest.raises(ValueError,match='resolved deployment path'):deploy._bytes(template)
    template.write_bytes(b'[Service]\nchanged definition\n')
    assert life.verify_manager_domain(data)!=result


def test_template_name_exception_does_not_accept_other_at_paths(tmp_path):
    import pytest
    for name in ('other@.service','thermal-native-activation-owner@instance.service','helper@.py'):
        path=tmp_path/name;path.write_bytes(b'private');path.chmod(0o600)
        with pytest.raises(ValueError,match='resolved deployment path'):life.fingerprint(path)


def test_actual_template_rejects_unsafe_files(tmp_path,monkeypatch):
    import pytest
    data,state,template=manager_domain_fixture(tmp_path,monkeypatch)
    original=template.read_bytes()
    template.chmod(0o620)
    with pytest.raises(ValueError):life.verify_manager_domain(data)
    template.chmod(0o600)
    alias=tmp_path/'hardlink';os.link(template,alias)
    with pytest.raises(ValueError):life.verify_manager_domain(data)
    alias.unlink()
    template.rename(alias);template.symlink_to(alias)
    with pytest.raises(ValueError):life.verify_manager_domain(data)
    template.unlink();alias.rename(template)
    directory=tmp_path/'directory';directory.mkdir();parent_link=tmp_path/'parent-link';parent_link.symlink_to(tmp_path,target_is_directory=True)
    state['FragmentPath']=str(parent_link/template.name)
    with pytest.raises(ValueError):life.verify_manager_domain(data)
    state['FragmentPath']=str(template)
    template.unlink();os.mkfifo(template,0o600)
    with pytest.raises(ValueError):life.verify_manager_domain(data)
    template.unlink();template.write_bytes(b'x'*(deploy.MAX_BYTES+1));template.chmod(0o600)
    with pytest.raises(ValueError):life.verify_manager_domain(data)
    template.write_bytes(original)
    # Refuse a mutation during the descriptor read, even if its size is unchanged.
    real_read=os.read
    def changing_read(fd,size):
        raw=real_read(fd,size);template.write_bytes(b'y'*len(original));return raw
    monkeypatch.setattr(os,'read',changing_read)
    with pytest.raises(ValueError):life.verify_manager_domain(data)


def test_actual_template_manager_and_source_guards(tmp_path,monkeypatch):
    import pytest
    data,state,template=manager_domain_fixture(tmp_path,monkeypatch)
    original=life.verify_manager_domain(data)
    for key,value in dict(InvocationID='other',ControlGroup='/private-learner.scope',MemoryMax='536870912',
                         MemorySwapMax='1',TasksMax='48',CPUQuotaPerSecUSec='400ms',KillMode='process',
                         ExecStart='other',ExecStopPost='other',DropInPaths='/private/override.conf').items():
        before=state[key];state[key]=value
        with pytest.raises(ValueError,match='topology'):life.verify_manager_domain(data)
        state[key]=before
    assert life.verify_manager_domain(data)==original
    binding={'sources':{str(template):original['definition']}}
    life.verify_sources(binding)
    template.write_bytes(b'[Service]\nchanged source\n')
    for full in (True,False):
        with pytest.raises(ValueError,match='source closure'):life.verify_sources(binding,full=full)


def test_template_rejects_foreign_owner_and_parent_path_exception(tmp_path,monkeypatch):
    import pytest
    _,_,template=manager_domain_fixture(tmp_path,monkeypatch)
    uid=os.getuid()
    with monkeypatch.context() as patch:
        patch.setattr(os,'getuid',lambda:uid+1)
        with pytest.raises(ValueError,match='owned lifecycle path'):life.fingerprint(template)
    parent=tmp_path/'other@directory';parent.mkdir()
    misplaced=parent/template.name;misplaced.write_bytes(template.read_bytes());misplaced.chmod(0o600)
    with pytest.raises(ValueError,match='resolved deployment path'):life.fingerprint(misplaced)


def test_template_rejects_replacement_before_open_or_during_read(tmp_path,monkeypatch):
    import pytest
    _,_,template=manager_domain_fixture(tmp_path,monkeypatch)
    original=template.read_bytes();real_open=os.open;real_read=os.read
    def replace():
        replacement=tmp_path/'replacement';replacement.write_bytes(original);replacement.chmod(0o600)
        replacement.replace(template)
    def replacing_open(path,*args,**kwargs):
        if Path(path)==template:replace()
        return real_open(path,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(os,'open',replacing_open)
        with pytest.raises(ValueError,match='bounded owned activation template'):life.fingerprint(template)
    def replacing_read(fd,size):
        raw=real_read(fd,size);replace();return raw
    with monkeypatch.context() as patch:
        patch.setattr(os,'read',replacing_read)
        with pytest.raises(ValueError,match='changed while reading'):life.fingerprint(template)


def test_manager_rejects_shared_worker_kill_domain(tmp_path,monkeypatch):
    import pytest
    data,state,_=manager_domain_fixture(tmp_path,monkeypatch)
    original=Path.read_text
    def same_group(path,*args,**kwargs):
        if path==Path('/proc')/str(os.getpid())/'cgroup':return '0::'+state['ControlGroup']+'\n'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',same_group)
    with pytest.raises(ValueError,match='worker kill domain'):life.verify_manager_domain(data)


def test_family_verification_uses_bounded_admitted_readonly_worker(tmp_path,monkeypatch):
    import pytest
    import household_job_launch as launcher
    from household_native_training import directory
    root=directory(tmp_path/'reservation');old=directory(tmp_path/'old/family')
    request=dict(nonce='a'*32,run=str(tmp_path/'new'),previous={'stage':str(tmp_path/'old/final')},
        phase='handoff',family=str(tmp_path/'new/family'),sources={str(Path(life.__file__)):life.fingerprint(Path(life.__file__))},
        source_sha256=sha256(Path(life.__file__).read_bytes()).hexdigest())
    life.save(root/'request.json',request)
    monkeypatch.setattr(family,'verify',lambda path,guard:guard() or {'checked':str(path)})
    monkeypatch.setattr(deploy,'_systemctl',lambda *args:f'/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/earthship.slice/earthship-work.slice')
    def launch(command,**kwargs):
        assert kwargs['minimum_bytes']==kwargs['preferred_bytes']==256*1024**2
        assert kwargs['tasks']==24 and kwargs['seconds']==10 and kwargs['production'] is True
        assert command[0]==sys.executable and command[1]=='-B'
        assert command[2]==str(Path(life.__file__))
        values=dict(zip(command[3::2],command[4::2]))
        assert '--verify-family' in values and '--verification-request' in values
        life._verification_worker(Path(values['--verification-request']),values['--verification-pin'],
            Path(values['--verify-family']),Path(values['--verification-output']),effective=False)
        return 0
    monkeypatch.setattr(launcher,'launch_job',launch)
    assert life._verify_family(root,old)=={'checked':str(old)}
    for fault in ('refused','result_binding','deadline'):
        def damaged(command,**kwargs):
            if fault=='refused':return 75
            result=launch(command,**kwargs)
            if fault=='result_binding':
                path=Path(command[command.index('--verification-output')+1]);value=life.read(path)
                value['request_sha256']='0'*64;life.save(path,value)
            else:
                clock=life.time.monotonic;now=clock();monkeypatch.setattr(life.time,'monotonic',lambda:now+11)
            return result
        with monkeypatch.context() as patch:
            # Restore the clock explicitly because damaged uses the outer fixture.
            clock=life.time.monotonic
            patch.setattr(launcher,'launch_job',damaged)
            with pytest.raises((ValueError,TimeoutError)):life._verify_family(root,old)
            monkeypatch.setattr(life.time,'monotonic',clock)
    def changed(path,guard):
        value=life.read(root/'request.json');value['phase']='release';life.save(root/'request.json',value)
        return {'checked':str(path)}
    monkeypatch.setattr(family,'verify',changed)
    with pytest.raises(ValueError,match='verification request changed'):life._verify_family(root,old)
