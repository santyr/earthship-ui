"""Approved native inference policy; original fitting guard remains unchanged."""
from collections import deque
import math
import os
from pathlib import Path
from time import monotonic
from thermal_model.training_pressure_guard import TrainingHeadroom, _counters, _text


class NativeInferenceHeadroom(TrainingHeadroom):
    """Keep strict per-callback checks; bound swap reads over a trailing second.

    The retained baseline can precede the boundary, making the bound conservative
    when samples are sparse. Failed checks latch; a caller cannot renew a budget
    by retrying after refusal. Worker caps and memory events are also checked.
    """
    def __init__(self,*,meminfo=Path('/proc/meminfo'),vmstat=Path('/proc/vmstat'),
                 pressure=Path('/proc/pressure/memory'),worker_check=None):
        super().__init__(meminfo=meminfo,vmstat=vmstat,pressure=pressure)
        if worker_check is None:
            from household_cycle_pressure import PublicationHeadroom
            worker_check=PublicationHeadroom().check
        if not callable(worker_check):raise ValueError('worker resource checker required')
        self.worker_check=worker_check;self.samples=deque();self.pressure_samples=deque();self.refused=False

    def check(self):
        if self.refused:raise ValueError('native inference headroom previously refused')
        try:
            self.worker_check()
            memory=_counters(self.meminfo,{'MemAvailable','SwapTotal','SwapFree'},units=True)
            counters=_counters(self.vmstat,{'pswpin','pswpout','oom_kill'})
            pressure={}
            for line in _text(self.pressure).splitlines():
                cells=line.split()
                if not cells or cells[0] not in {'some','full'} or cells[0] in pressure:raise ValueError('invalid pressure rows')
                pairs=[part.split('=') for part in cells[1:]]
                if any(len(pair)!=2 for pair in pairs):raise ValueError('invalid pressure fields')
                values=dict(pairs)
                if len(values)!=len(pairs) or set(values)!={'avg10','avg60','avg300','total'}:raise ValueError('invalid pressure fields')
                averages=[float(values[key]) for key in ('avg10','avg60','avg300')]
                limit=.5 if cells[0]=='some' else .1
                if any(not math.isfinite(x) or not 0<=x<=limit for x in averages):raise ValueError('memory pressure exceeded')
                if not values['total'].isascii() or not values['total'].isdecimal():raise ValueError('invalid pressure counter')
                pressure[cells[0]]=int(values['total'])
            if set(pressure)!={'some','full'}:raise ValueError('incomplete memory pressure')
            if memory['MemAvailable']<1572864 or memory['SwapFree']>memory['SwapTotal']:raise ValueError('memory reserve unavailable')
            now=monotonic()
            if self.previous is not None:
                at,old,old_pressure=self.previous
                if now<=at or any(counters[k]!=old[k] for k in ('pswpout','oom_kill')):
                    raise ValueError('swap-out activity or OOM counter changed')
                swapped_in=counters['pswpin']-old['pswpin']
                if swapped_in<0:raise ValueError('host swap-read counter regressed')
                for key,limit in (('some',.5),('full',.1)):
                    delta=pressure[key]-old_pressure[key]
                    if delta<0:raise ValueError('memory pressure counter regressed')
            self.pressure_samples.append((now,pressure))
            while len(self.pressure_samples)>1 and self.pressure_samples[1][0]<=now-1:
                self.pressure_samples.popleft()
            if len(self.pressure_samples)>65536:raise ValueError('bounded inference pressure samples exceeded')
            for key,limit in (('some',.5),('full',.1)):
                if pressure[key]-self.pressure_samples[0][1][key]>1000000*limit/100:
                    raise ValueError('trailing one-second memory pressure exceeded')
            self.samples.append((now,counters['pswpin']))
            # Retain the sample before the boundary: do not discard an
            # unmeasured partial interval or interpolate cumulative counters.
            while len(self.samples)>1 and self.samples[1][0]<=now-1:
                self.samples.popleft()
            if len(self.samples)>65536:raise ValueError('bounded inference pressure samples exceeded')
            if (counters['pswpin']-self.samples[0][1])*os.sysconf('SC_PAGE_SIZE')>1048576:
                raise ValueError('host swap-read activity exceeded trailing one-second allowance')
            self.previous=(now,counters,pressure)
        except (OSError,UnicodeError,ValueError,OverflowError) as error:
            self.refused=True
            raise ValueError('native inference host pressure or memory reserve unavailable: '+str(error)) from None

