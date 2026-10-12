"""Publication headroom for capped inference, separate from fitting policy.

The original publication preflight enforces caps, host RAM reserve, PSI and one
numerical thread. Host swap traffic can belong to unrelated processes; actual
new host OOM events or this worker's memory-limit events still stop inference.
"""
from pathlib import Path,PurePosixPath
from time import sleep
from thermal_model.training_pressure_guard import _counters
from thermal_model.capture_guard import _small_text


class PublicationHeadroom:
    def __init__(self,*,vmstat=Path('/proc/vmstat'),memory_events=None):
        self.vmstat=Path(vmstat);self.memory_events=None if memory_events is None else Path(memory_events)
        self.previous=None

    def check(self):
        from thermal_installed_intel import _resource_preflight
        _resource_preflight()
        if self.memory_events is None:
            row=_small_text('/proc/self/cgroup')
            # The original preflight already verifies the unified bounded leaf.
            leaf=Path('/sys/fs/cgroup').joinpath(*PurePosixPath(row[3:]).parts[1:])
            self.memory_events=leaf/'memory.events'
        host=_counters(self.vmstat,{'oom_kill'})
        worker=_counters(self.memory_events,{'max','oom','oom_kill'})
        current=(host,worker)
        if self.previous is not None and current!=self.previous:
            raise ValueError('publication host OOM or worker memory-limit counters changed')
        self.previous=current

    def preflight(self):
        self.check()
        for _ in range(5):sleep(1);self.check()
