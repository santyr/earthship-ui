"""Read finite kernel commitments for the shared Earthship work slice."""
import os
from pathlib import Path
import stat

from household_job_budget import GiB, _bytes

POOL_NAME = 'earthship-work.slice'
POOL_MEMORY_MAX = 6 * GiB
HOST_RESERVE = 3 * GiB


def _text(path, maximum=16384):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        raw = os.read(fd, maximum + 1)
        if len(raw) > maximum:
            raise ValueError('bounded resource metadata required')
        return raw.decode('ascii').strip()
    finally:
        os.close(fd)


def _counter(path):
    text = _text(path, 64)
    if not text.isascii() or not text.isdecimal():
        raise ValueError('finite resource counter required')
    return _bytes(int(text))


def available_memory(path=Path('/proc/meminfo')):
    try:
        rows = [line.split() for line in _text(path).splitlines()
                if line.startswith('MemAvailable:')]
        if len(rows) != 1 or len(rows[0]) != 3 or rows[0][2] != 'kB':
            raise ValueError('one available-memory quantity required')
        number = rows[0][1]
        if not number.isascii() or not number.isdecimal():
            raise ValueError('available-memory counter required')
        return _bytes(int(number) * 1024)
    except (OSError, UnicodeError) as error:
        raise ValueError('host memory metadata unavailable') from error


def read_pool(path):
    """Snapshot immediate unit commitments, including their descendants.

    Missing data refuses this admission; a caller may take a new snapshot after
    a unit has exited. Unknown finite child units count just like known jobs.
    The kernel parent cap remains authoritative between these sampled reads.
    """
    path = Path(path).absolute()
    try:
        if path.resolve() != path or not stat.S_ISDIR(path.lstat().st_mode):
            raise ValueError('real pool cgroup directory required')
        limit = _counter(path/'memory.max')
        high = _counter(path/'memory.high')
        quota = _text(path/'cpu.max', 128).split()
        if (len(quota) != 2 or any(not part.isascii() or not part.isdecimal() for part in quota)
                or not 0 < int(quota[0]) <= 8 * int(quota[1])):
            raise ValueError('bounded shared CPU envelope required')
        if (not 0 < high <= limit <= POOL_MEMORY_MAX or
                _counter(path/'memory.swap.max') != 0 or
                not 0 < _counter(path/'pids.max') <= 256):
            raise ValueError('bounded shared memory and task envelope required')
        jobs = {}
        for count, child in enumerate(path.iterdir(), 1):
            if count > 1024:
                raise ValueError('bounded pool inventory required')
            info = child.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError('aliased pool child refused')
            if not stat.S_ISDIR(info.st_mode):
                continue
            if len(jobs) >= 256:
                raise ValueError('bounded job inventory required')
            current = _counter(child/'memory.current')
            child_limit = _counter(child/'memory.max')
            if not 0 < child_limit or current > child_limit:
                raise ValueError('finite valid job commitment required')
            jobs[child.name] = dict(used_bytes=current, limit_bytes=child_limit)
        return dict(pool_limit_bytes=limit, pool_used_bytes=_counter(path/'memory.current'), jobs=jobs)
    except (OSError, UnicodeError) as error:
        raise ValueError('shared pool metadata unavailable') from error


def check_host_pressure(path=Path('/proc/pressure/memory'), *, available=available_memory):
    """Defer on sustained stalls or emergency RAM pressure, not counter ticks.

    Ten-second PSI averages avoid per-callback rate amplification. New jobs
    additionally leave a3GiB admission reserve; running jobs stop below1.5GiB.
    """
    import math
    from household_job_budget import AdmissionDeferred, MiB
    try:
        seen=set()
        for line in _text(path).splitlines():
            cells=line.split()
            if not cells or cells[0] not in {'some','full'} or cells[0] in seen:
                raise ValueError('complete unique PSI rows required')
            seen.add(cells[0]);values={}
            for cell in cells[1:]:
                key,value=cell.split('=',1)
                if key in values:raise ValueError('unique PSI fields required')
                values[key]=value
            if set(values)!={'avg10','avg60','avg300','total'}:
                raise ValueError('complete PSI fields required')
            averages=[float(values[k]) for k in ('avg10','avg60','avg300')]
            if any(not math.isfinite(v) or not 0<=v<=100 for v in averages):
                raise ValueError('finite PSI averages required')
            if not values['total'].isascii() or not values['total'].isdecimal():
                raise ValueError('valid PSI counter required')
            if averages[0]>(5. if cells[0]=='some' else 1.):
                raise AdmissionDeferred('sustained host memory pressure')
        if seen!={'some','full'}:raise ValueError('complete PSI rows required')
        if _bytes(available())<1536*MiB:
            raise AdmissionDeferred('emergency host RAM reserve reached')
    except (OSError,UnicodeError) as error:
        raise ValueError('host pressure metadata unavailable') from error
