"""Tiny synthetic host preflight tests; never capture or fit."""
import sys
import pytest
from thermal_model import capture_guard as guard


def info(tmp_path, available=3145728, total=4194304, free=4063232):
    path=tmp_path/'meminfo'
    path.write_text(f'MemAvailable: {available} kB\nSwapTotal: {total} kB\nSwapFree: {free} kB\n')
    return path


def test_headroom_accepts_exact_boundaries(tmp_path):
    guard.verify_host_headroom(meminfo=info(tmp_path))


@pytest.mark.parametrize('values',[(3145727,4194304,4194304),(3145728,4194304,4063231),(3145728,1,2),(-1,0,0)])
def test_headroom_refuses_low_memory_or_excess_swap(tmp_path,values):
    with pytest.raises(ValueError):guard.verify_host_headroom(meminfo=info(tmp_path,*values))


@pytest.mark.parametrize('text',['','MemAvailable: 3145728 kB\n','MemAvailable: 3145728 MB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n','MemAvailable: 3145728 kB\nMemAvailable: 3145728 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n'])
def test_headroom_refuses_missing_ambiguous_or_wrong_units(tmp_path,text):
    path=tmp_path/'meminfo';path.write_text(text)
    with pytest.raises(ValueError):guard.verify_host_headroom(meminfo=path)


def test_headroom_failure_prevents_any_worker_launch(tmp_path,monkeypatch):
    monkeypatch.setattr(guard,'verify_resource_limits',lambda:None)
    monkeypatch.setattr(guard.os,'getpriority',lambda *args:15)
    path=info(tmp_path,available=1)
    original=guard.verify_host_headroom
    def check():original(meminfo=path)
    monkeypatch.setattr(guard,'verify_host_headroom',check,raising=False)
    monkeypatch.setattr(guard.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('worker launched despite exhausted host'))
    with pytest.raises(ValueError):guard.run_guarded_capture([sys.executable,'-c','pass'],seconds=1)
