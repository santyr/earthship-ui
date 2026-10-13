"""Publication cap checks retain idle IO without a subprocess per source access."""
from pathlib import Path
import pytest
from household_cycle_resources import publication_resource_preflight


def fixture(tmp_path):
    leaf=tmp_path/'leaf';leaf.mkdir()
    for name,value in {'cpu.max':'20000 100000','memory.max':'268435456','memory.swap.max':'0','pids.max':'24'}.items():(leaf/name).write_text(value)
    memory=tmp_path/'meminfo';memory.write_text('MemAvailable: 1572864 kB\n')
    pressure=tmp_path/'pressure';pressure.write_text('some avg10=0.00 avg60=0.00 avg300=0.00 total=1\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=1\n')
    calls=[]
    def ioprio():calls.append(True);return 3<<13
    args={'leaf':leaf,'meminfo':memory,'pressure':pressure,'get_nice':lambda:15,'get_ioprio':ioprio,'environ':{'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}}
    return args,calls


def test_idle_kernel_priority_qualifies_missing_io_controller_without_process_spawn(tmp_path):
    args,calls=fixture(tmp_path);publication_resource_preflight(**args)
    assert calls==[True]


def test_explicit_io_controller_retains_weight_check_without_idle_fallback(tmp_path):
    args,calls=fixture(tmp_path);(args['leaf']/'io.weight').write_text('default 10\n')
    publication_resource_preflight(**args);assert calls==[]


@pytest.mark.parametrize('name,value',[('cpu.max','25000 100000'),('cpu.max','max 100000'),('cpu.max','0 100000'),('memory.max','268435457'),('memory.max','max'),('memory.swap.max','1'),('pids.max','25'),('pids.max','0'),('io.weight','default 11'),('io.weight','default 0'),('io.weight','default 10\n8:0 10')])
def test_relaxed_or_unknown_kernel_caps_refuse(name,value,tmp_path):
    args,_=fixture(tmp_path);(args['leaf']/name).write_text(value)
    with pytest.raises(ValueError):publication_resource_preflight(**args)


@pytest.mark.parametrize('value',[0,2<<13,-1,True,None,1<<13])
def test_non_idle_or_unknown_kernel_priority_refuses(value,tmp_path):
    args,_=fixture(tmp_path);args['get_ioprio']=lambda:value
    with pytest.raises(ValueError):publication_resource_preflight(**args)


@pytest.mark.parametrize('damage',['ram','ram_unknown','nice','thread','some_pressure','full_pressure','unknown_pressure','nan_pressure'])
def test_original_ram_pressure_nice_and_single_thread_policy_remains_required(damage,tmp_path):
    args,_=fixture(tmp_path)
    if damage=='ram':args['meminfo'].write_text('MemAvailable: 1572863 kB\n')
    elif damage=='ram_unknown':args['meminfo'].write_text('MemAvailable: unknown kB\n')
    elif damage=='nice':args['get_nice']=lambda:14
    elif damage=='thread':args['environ']['OMP_NUM_THREADS']='2'
    else:
        args['pressure'].write_text({'some_pressure':'some avg10=0.51\nfull avg10=0.0\n','full_pressure':'some avg10=0.0\nfull avg10=0.51\n','unknown_pressure':'some avg10=0.0\n','nan_pressure':'some avg10=NaN\nfull avg10=0.0\n'}[damage])
    with pytest.raises(ValueError):publication_resource_preflight(**args)


def test_native_priority_read_matches_the_original_main_process_target(monkeypatch):
    import household_cycle_resources as api
    from types import SimpleNamespace
    calls=[]
    def syscall(*args):calls.append([arg.value for arg in args]);return 3<<13
    monkeypatch.setattr(api.ctypes,'CDLL',lambda *args,**kwargs:SimpleNamespace(syscall=syscall))
    monkeypatch.setattr(api.os,'uname',lambda:SimpleNamespace(sysname='Linux',machine='x86_64'))
    assert api.current_ioprio()==3<<13
    assert calls==[[252,1,api.os.getpid()]]


@pytest.mark.parametrize('platform,value',[('aarch64',3<<13),('x86_64',-1)])
def test_unknown_abi_or_failed_kernel_read_refuses(platform,value,monkeypatch):
    import household_cycle_resources as api
    from types import SimpleNamespace
    monkeypatch.setattr(api.ctypes,'CDLL',lambda *args,**kwargs:SimpleNamespace(syscall=lambda *args:value))
    monkeypatch.setattr(api.os,'uname',lambda:SimpleNamespace(sysname='Linux',machine=platform))
    with pytest.raises(ValueError):api.current_ioprio()


@pytest.mark.parametrize('pointer,long',[ (4,4), (4,8), (8,4) ])
def test_kernel_x86_64_requires_native_lp64_process_before_loading_syscall(pointer,long,monkeypatch):
    import household_cycle_resources as api
    from types import SimpleNamespace
    monkeypatch.setattr(api.os,'uname',lambda:SimpleNamespace(sysname='Linux',machine='x86_64'))
    monkeypatch.setattr(api.ctypes,'sizeof',lambda kind:pointer if kind is api.ctypes.c_void_p else long)
    def forbidden(*args,**kwargs):pytest.fail('unsupported ABI loaded libc')
    monkeypatch.setattr(api.ctypes,'CDLL',forbidden)
    with pytest.raises(ValueError):api.current_ioprio()


def leaf_fixture(tmp_path,monkeypatch):
    import household_cycle_resources as api
    root=tmp_path/'cgroups';root.mkdir();(root/'a').mkdir();(root/'b').mkdir()
    membership=tmp_path/'membership';membership.write_text('0::/a\n')
    original=api._small_text
    monkeypatch.setattr(api,'_small_text',lambda path:original(membership if str(path)=='/proc/self/cgroup' else path))
    monkeypatch.setattr(api,'Path',lambda value:root if str(value)=='/sys/fs/cgroup' else Path(value))
    monkeypatch.setattr(api,'_parsed_leaf',None,raising=False)
    return api,root,membership


def test_resource_leaf_reuses_syntax_but_reads_current_membership(tmp_path,monkeypatch):
    api,root,membership=leaf_fixture(tmp_path,monkeypatch);calls=[];resolve=Path.resolve
    def tracked(path,*args,**kwargs):calls.append(str(path));return resolve(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',tracked)
    assert api._leaf()==root/'a';assert calls
    calls.clear();assert api._leaf()==root/'a';assert calls==[]
    membership.write_text('0::/b\n');assert api._leaf()==root/'b';assert calls


@pytest.mark.parametrize('part',['root','leaf'])
def test_resource_leaf_cache_refuses_new_symlink_components(tmp_path,monkeypatch,part):
    api,root,_=leaf_fixture(tmp_path,monkeypatch);api._leaf()
    path=root if part=='root' else root/'a';saved=path.with_name(path.name+'-saved')
    path.rename(saved);path.symlink_to(saved,target_is_directory=True)
    with pytest.raises(ValueError):api._leaf()


def test_resource_root_alias_is_resolved_again(tmp_path,monkeypatch):
    api,root,_=leaf_fixture(tmp_path,monkeypatch);alias=tmp_path/'alias';alias.symlink_to(root,target_is_directory=True)
    monkeypatch.setattr(api,'Path',lambda value:alias if str(value)=='/sys/fs/cgroup' else Path(value))
    assert api._leaf()==root/'a';calls=[];resolve=Path.resolve
    def tracked(path,*args,**kwargs):calls.append(str(path));return resolve(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',tracked);assert api._leaf()==root/'a';assert str(alias) in calls
    other=tmp_path/'other';other.mkdir();(other/'a').mkdir();alias.unlink();alias.symlink_to(other,target_is_directory=True)
    assert api._leaf()==other/'a'


@pytest.mark.parametrize('name,value',[('cpu.max','25000 100000'),('memory.max','268435457'),('memory.swap.max','1'),('pids.max','25'),('io.weight','default 11')])
def test_resource_paths_reused_without_caching_current_caps(tmp_path,name,value):
    args,_=fixture(tmp_path);publication_resource_preflight(**args)
    (args['leaf']/name).write_text(value)
    with pytest.raises(ValueError):publication_resource_preflight(**args)


@pytest.mark.parametrize('raw',[b'x'*4097,b'\xff'])
def test_resource_reader_retains_ascii_and_size_bounds(tmp_path,raw):
    args,_=fixture(tmp_path);(args['leaf']/'cpu.max').write_bytes(raw)
    with pytest.raises(ValueError):publication_resource_preflight(**args)
