"""A cold outer launcher cannot contaminate its immutable source directory."""
import os
from pathlib import Path
import subprocess
import sys


def test_outer_launcher_disables_bytecode_before_sibling_imports(tmp_path):
    source=Path(__file__).with_name('household_job_run.py')
    (tmp_path/source.name).write_bytes(source.read_bytes())
    # Private independent import stubs make --help exercise the real launcher's
    # startup without connecting to systemd or invoking a workload.
    (tmp_path/'household_job_budget.py').write_text('class AdmissionDeferred(Exception):pass\nMiB=1048576\n')
    (tmp_path/'household_job_pool.py').write_text("POOL_NAME='private-test-only.slice'\n")
    (tmp_path/'household_job_launch.py').write_text('def launch_job(*a,**kw):raise AssertionError()\n')
    environment={k:v for k,v in os.environ.items() if k not in ('PYTHONDONTWRITEBYTECODE','PYTHONPATH')}
    result=subprocess.run([sys.executable,str(tmp_path/source.name),'--help'],env=environment,capture_output=True,timeout=10)
    assert result.returncode==0
    assert not (tmp_path/'__pycache__').exists(),'outer launcher imported immutable helpers before disabling bytecode'
