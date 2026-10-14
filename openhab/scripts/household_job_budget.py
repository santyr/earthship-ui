"""Shared RAM admission from host headroom and active cgroup commitments.

Kernel limits, rather than a lease file, represent RAM already promised to
running jobs. The caller must serialize admission through unit creation.
"""
MiB = 1024**2
GiB = 1024**3


class AdmissionDeferred(RuntimeError):
    """A valid request must wait for more headroom or a running job to exit."""


def _bytes(value, *, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= 2**60:
        raise ValueError('finite nonnegative resource byte count required')
    return value


def admit_memory(*, available_bytes, pool_limit_bytes, pool_used_bytes, jobs,
                 minimum_bytes, preferred_bytes, reserve_bytes):
    """Return a whole-MiB job limit, reserving every sibling's future growth.

    MemAvailable already excludes running jobs' current use. Subtract only
    their remaining promised growth there. At the pool boundary subtract full
    commitments plus any memory charged outside those observed child units.
    A requested minimum is never silently reduced.
    """
    available_bytes = _bytes(available_bytes)
    pool_limit_bytes = _bytes(pool_limit_bytes, positive=True)
    pool_used_bytes = _bytes(pool_used_bytes)
    minimum_bytes = _bytes(minimum_bytes, positive=True)
    preferred_bytes = _bytes(preferred_bytes, positive=True)
    reserve_bytes = _bytes(reserve_bytes)
    if minimum_bytes > preferred_bytes:
        raise ValueError('minimum job budget exceeds preferred budget')
    if not isinstance(jobs, dict) or len(jobs) > 256:
        raise ValueError('bounded uniquely named job commitments required')
    used = committed = 0
    for name, job in jobs.items():
        if not isinstance(name, str) or not name or len(name) > 255:
            raise ValueError('bounded job identity required')
        if not isinstance(job, dict) or set(job) != {'used_bytes', 'limit_bytes'}:
            raise ValueError('complete job commitment required')
        current = _bytes(job['used_bytes'])
        limit = _bytes(job['limit_bytes'], positive=True)
        if current > limit:
            raise ValueError('job usage exceeds verified memory limit')
        used += current
        committed += limit
    remaining_growth = committed - used
    parent_charges = max(0, pool_used_bytes - used)
    available = min(preferred_bytes,
        pool_limit_bytes - committed - parent_charges,
        available_bytes - reserve_bytes - remaining_growth)
    allocated = available // MiB * MiB
    if allocated < minimum_bytes:
        raise AdmissionDeferred('insufficient shared RAM headroom')
    return allocated
