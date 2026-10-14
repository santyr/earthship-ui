"""Repeated native replay admission must verify idle I/O without process spawn."""
import subprocess


def test_native_resource_admission_never_spawns_an_ionice_probe(monkeypatch):
    import native_thermal_live as native
    original=subprocess.check_output
    def checked(argv,*args,**kwargs):
        if argv and str(argv[0]).endswith('/ionice'):
            raise AssertionError('native numerical replay spawned a per-step I/O priority probe')
        return original(argv,*args,**kwargs)
    monkeypatch.setattr(subprocess,'check_output',checked)
    # This test is run inside the actual approved capped scope, not a fake
    # cgroup. Successful admission still proves the real process caps/priority.
    from household_cycle_resources import publication_native_policy
    with publication_native_policy():
        native._resource_preflight()


def test_native_resource_checker_refuses_changed_bound_helper_bytes(monkeypatch):
    import pytest
    import native_thermal_live as native
    monkeypatch.setattr(native,'_source_bytes',lambda *a,**kw:b'changed helper bytes',raising=False)
    with pytest.raises(ValueError,match='native resource checker source changed'):
        native._resource_preflight()


def test_native_admission_resolves_only_the_freshly_read_helper(monkeypatch):
    from pathlib import Path
    import native_thermal_live as native
    # Exercise the original pin verifier against a matching test pin. Live
    # serving selects its new operational policy outside the fitted adapter.
    from hashlib import sha256
    monkeypatch.setattr(native,'RESOURCE_SOURCE_SHA256',sha256(Path(native.__file__).with_name('household_cycle_resources.py').read_bytes()).hexdigest())
    calls=[];original=Path.resolve
    def tracked(path,*args,**kwargs):
        calls.append(str(path));return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',tracked)
    native._resource_preflight()
    helper=str(Path(native.__file__).with_name('household_cycle_resources.py'))
    assert calls.count(helper)==1
    assert str(Path(native.__file__)) not in calls


def test_native_admission_refuses_loaded_checker_from_another_location(monkeypatch):
    import pytest
    import native_thermal_live as native
    monkeypatch.setattr(native,'_publication_resource_preflight',lambda:None)
    with pytest.raises(ValueError,match='native resource checker source changed'):
        native._resource_preflight()
