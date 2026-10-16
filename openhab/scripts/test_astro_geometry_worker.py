"""Real request-file / library identity checks, with only JVM execution stubbed."""
from pathlib import Path
from datetime import timedelta
import importlib
import pytest
from test_astro_geometry import NOW,TIMES,api as geometry


def api():return importlib.import_module('astro_geometry_worker')


def context(tmp_path):
    root=tmp_path/'native';root.mkdir(mode=0o700)
    libraries={}
    for role in ('astro_binding','openhab_core','unit_api','indriya','pax_logging_api','osgi_core'):
        path=root/(role+'.jar');path.write_bytes((role+' native fixture').encode());path.chmod(0o600);libraries[role]=path
    request=geometry().build_request(TIMES,requested_at=NOW,latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver')
    runtime=api().runtime_identity(libraries,binding_version='5.2.3',guard=lambda:None)
    source=geometry().build_source(request,observed_at=NOW+timedelta(seconds=1),native_runtime=runtime,source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)
    return root,libraries,request,source


def test_real_original_request_file_and_native_output_are_pinned(tmp_path,monkeypatch):
    root,libraries,request,source=context(tmp_path);seen=[]
    monkeypatch.setattr(api(),'_resource_preflight',lambda:None)
    def execute(argv,*,check,seconds,env):
        check();path=Path(argv[-1]);text=path.read_text();seen.append(text)
        assert text.splitlines()[2:]==request['instants'] and path.stat().st_mode & 0o777==0o600
        assert seconds==25 and '-Xmx64m' in argv and '-XX:ActiveProcessorCount=1' in argv
        assert 'JAVA_TOOL_OPTIONS' not in env and 'JDK_JAVA_OPTIONS' not in env
        return 0, ''.join(at+'\t1.25\t125.0\n' for at in request['instants']).encode()
    monkeypatch.setattr(api(),'run_training_worker',execute)
    cache=api().capture_batch(request,source,library_paths=libraries,scratch=root,guard=lambda:None,clock=lambda:NOW+timedelta(seconds=2))
    assert len(seen)==1 and cache.elevation_degrees(TIMES[0])==1.25
    assert not list(root.glob('*.native-geometry-request.txt'))


def test_changed_native_library_refuses_before_worker(tmp_path,monkeypatch):
    root,libraries,request,source=context(tmp_path);libraries['astro_binding'].write_bytes(b'changed')
    monkeypatch.setattr(api(),'_resource_preflight',lambda:None)
    monkeypatch.setattr(api(),'run_training_worker',lambda *a,**kw:pytest.fail('changed library executed'))
    with pytest.raises(ValueError):api().capture_batch(request,source,library_paths=libraries,scratch=root,guard=lambda:None)


def test_worker_failure_does_not_build_a_partial_geometry_cache(tmp_path,monkeypatch):
    root,libraries,request,source=context(tmp_path)
    monkeypatch.setattr(api(),'_resource_preflight',lambda:None)
    monkeypatch.setattr(api(),'run_training_worker',lambda *a,**kw:(1,b''))
    with pytest.raises(ValueError):api().capture_batch(request,source,library_paths=libraries,scratch=root,guard=lambda:None)


def test_source_or_request_change_during_worker_refuses(tmp_path,monkeypatch):
    root,libraries,request,source=context(tmp_path)
    monkeypatch.setattr(api(),'_resource_preflight',lambda:None)
    def execute(argv,**kw):
        Path(argv[-1]).write_text('changed original request')
        return 0, ''.join(at+'\t1.25\t125.0\n' for at in request['instants']).encode()
    monkeypatch.setattr(api(),'run_training_worker',execute)
    with pytest.raises(ValueError):api().capture_batch(request,source,library_paths=libraries,scratch=root,guard=lambda:None)


@pytest.mark.parametrize('owner,accepted',[(112,True),(9876,False)])
def test_only_runtime_service_owner_is_trusted_inside_installed_library_roots(owner,accepted,tmp_path,monkeypatch):
    import os
    from types import SimpleNamespace
    root,libraries,request,source=context(tmp_path);target=libraries['astro_binding']
    monkeypatch.setattr(api(),'NATIVE_ROOTS',(root,),raising=False)
    monkeypatch.setattr(api(),'_openhab_uid',lambda:112,raising=False)
    original=os.fstat
    def metadata(fd):
        value=original(fd)
        if Path(os.readlink('/proc/self/fd/'+str(fd)))==target:
            names=('st_dev','st_ino','st_mode','st_uid','st_size','st_mtime_ns','st_ctime_ns')
            return SimpleNamespace(**{name:owner if name=='st_uid' else getattr(value,name) for name in names})
        return value
    monkeypatch.setattr(api().os,'fstat',metadata)
    if accepted:assert api().runtime_identity(libraries,binding_version='5.2.3',guard=lambda:None)==source['native_runtime']
    else:
        with pytest.raises(ValueError):api().runtime_identity(libraries,binding_version='5.2.3',guard=lambda:None)
