"""Original capped serial-publication verifier; no standalone CLI."""
import os
from pathlib import Path


def _resource_preflight():
    from thermal_model.capture_guard import verify_resource_limits,_small_text
    from pathlib import PurePosixPath
    verify_resource_limits()
    row=_small_text('/proc/self/cgroup');path=PurePosixPath(row[3:])
    leaf=Path('/sys/fs/cgroup').joinpath(*path.parts[1:])
    quota,period=map(int,_small_text(leaf/'cpu.max').split())
    if (quota*5>period or int(_small_text(leaf/'memory.max'))>268435456 or
            int(_small_text(leaf/'pids.max'))>24 or os.getpriority(os.PRIO_PROCESS,0)<15):
        raise ValueError('strict serial installed publication resource limits required')
    memory={line.split()[0]:line.split()[1] for line in _small_text('/proc/meminfo').splitlines() if line.split()}
    if int(memory['MemAvailable:'])<1572864:raise ValueError('publication memory headroom unavailable')
    pressure=_small_text('/proc/pressure/memory').splitlines()
    for line in pressure:
        cells=dict(part.split('=',1) for part in line.split()[1:])
        if float(cells['avg10'])>.5:raise ValueError('publication memory pressure unavailable')
    # This is a capped publication reader, not the large training-capture worker.
    # Its separate preflight does not change training/capture/fitting guards.
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(key)!='1':raise ValueError('one numerical thread required')
