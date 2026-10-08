"""Small standalone systemd memory guard; no trainer or service execution."""
from pathlib import Path
import subprocess
import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'openhab/systemd/user/thermal-model-train.service.d/memory-preflight.awk'


@pytest.mark.parametrize('text,expected',[
    ('MemAvailable: 3145728 kB\nSwapTotal: 4194304 kB\nSwapFree: 4063232 kB\n',0),
    ('MemAvailable: 3145727 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n',1),
    ('MemAvailable: 3145728 kB\nSwapTotal: 4194304 kB\nSwapFree: 4063231 kB\n',1),
    ('MemAvailable: 3145728 kB\nSwapTotal: 0 kB\nSwapFree: 1 kB\n',1),
    ('MemAvailable: 3145728 MB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n',1),
    ('MemAvailable: 3145728 kB\nMemAvailable: 3145728 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n',1),
    ('MemAvailable: -1 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n',1),
    ('',1),
])
def test_guard_accepts_headroom_and_refuses_bad_or_insufficient_metadata(text,expected):
    result=subprocess.run(['/usr/bin/awk','-f',str(SCRIPT)],input=text,capture_output=True,text=True,timeout=2)
    assert result.returncode==expected
    assert result.stdout==''
