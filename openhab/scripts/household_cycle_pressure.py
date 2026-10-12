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
    def __init__(self,*,vmstat=Path('/proc/vmstat'),memory_events=None,resource_check=None):
        self.vmstat=Path(vmstat);self.memory_events=None if memory_events is None else Path(memory_events)
        self.resource_check=resource_check
        if resource_check is not None and not callable(resource_check):raise ValueError('resource checker required')
        self.previous=None;self.discover_cgroup=memory_events is None;self.cgroup_binding=None

    def check(self):
        binding=None
        if self.discover_cgroup:
            events,binding=self._current_binding()
            if self.cgroup_binding is not None and binding!=self.cgroup_binding:
                raise ValueError('publication cgroup binding changed')
            self.memory_events=events
        if self.resource_check is None:
            from household_cycle_resources import publication_resource_preflight
            publication_resource_preflight(leaf=self.memory_events.parent if self.discover_cgroup else None)
        else:self.resource_check()
        host=_counters(self.vmstat,{'oom_kill'})
        worker=_counters(self.memory_events,{'max','oom','oom_kill'})
        current=(host,worker)
        if self.previous is not None and current!=self.previous:
            raise ValueError('publication host OOM or worker memory-limit counters changed')
        if self.discover_cgroup:
            if self._current_binding()!=(self.memory_events,binding):
                raise ValueError('publication cgroup changed during counter read')
            self.cgroup_binding=binding
        self.previous=current

    def _current_binding(self):
        row=_small_text('/proc/self/cgroup')
        if len(row.splitlines())!=1 or not row.startswith('0::/'):
            raise ValueError('unified publication cgroup required')
        path=PurePosixPath(row[3:])
        if path.root!='/' or '..' in path.parts or str(path)!=row[3:]:
            raise ValueError('normalized publication cgroup required')
        root=Path('/sys/fs/cgroup').resolve();leaf=root.joinpath(*path.parts[1:])
        if leaf.resolve()!=leaf or not leaf.is_relative_to(root):
            raise ValueError('contained publication cgroup required')
        info=leaf.stat()
        return leaf/'memory.events',(str(leaf),info.st_dev,info.st_ino)

    def preflight(self):
        self.check()
        for _ in range(5):sleep(1);self.check()
