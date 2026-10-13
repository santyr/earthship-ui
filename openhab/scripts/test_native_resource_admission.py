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
    native._resource_preflight()


def test_native_resource_checker_refuses_changed_bound_helper_bytes(monkeypatch):
    import pytest
    import native_thermal_live as native
    monkeypatch.setattr(native,'_source_bytes',lambda *a,**kw:b'changed helper bytes',raising=False)
    with pytest.raises(ValueError,match='native resource checker source changed'):
        native._resource_preflight()
