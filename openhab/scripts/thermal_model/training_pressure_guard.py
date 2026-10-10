"""Training-only host pressure checks and interruptible capped worker lifetime."""
import math
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic, sleep


def _text(path):
    with Path(path).open('rb') as stream:
        raw=stream.read(16385)
    if len(raw)>16384:raise ValueError('bounded resource metadata required')
    return raw.decode('ascii')


def _counters(path,names,*,units=False):
    result={}
    for line in _text(path).splitlines():
        cells=line.split();key=cells[0].rstrip(':') if cells else ''
        if key not in names:continue
        if (key in result or len(cells)!=(3 if units else 2) or
                not cells[1].isascii() or not cells[1].isdecimal() or
                (units and cells[2]!='kB')):raise ValueError('invalid resource counters')
        result[key]=int(cells[1])
    if set(result)!=set(names):raise ValueError('incomplete resource counters')
    return result


class TrainingHeadroom:
    """Require 1.5 GiB reserve, low PSI, no active swap or new OOMs.

    Occupied swap is historical residency, not an admission threshold. This
    guard is only used with the independently verified 256 MiB training cap.
    Provisional fitting may explicitly allow at most 1 MiB/s of host swap-in;
    swap-out/OOM changes and all reserve/PSI checks remain strict.
    """
    def __init__(self,*,meminfo=Path('/proc/meminfo'),vmstat=Path('/proc/vmstat'),pressure=Path('/proc/pressure/memory'),max_swapin_bytes_per_second=0):
        if type(max_swapin_bytes_per_second) is not int or not 0<=max_swapin_bytes_per_second<=1048576:
            raise ValueError('bounded host swap-read allowance required')
        self.max_swapin_bytes_per_second=max_swapin_bytes_per_second
        self.meminfo=meminfo;self.vmstat=vmstat;self.pressure=pressure;self.previous=None

    def check(self):
        try:
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
                if swapped_in<0 or swapped_in*os.sysconf('SC_PAGE_SIZE')>(now-at)*self.max_swapin_bytes_per_second:
                    raise ValueError('host swap-read activity exceeded bounded allowance')
                for key,limit in (('some',.5),('full',.1)):
                    delta=pressure[key]-old_pressure[key]
                    if delta<0 or delta>(now-at)*1000000*limit/100:raise ValueError('interval memory pressure exceeded')
            self.previous=(now,counters,pressure)
        except (OSError,UnicodeError,ValueError,OverflowError) as error:
            raise ValueError('training host pressure or memory reserve unavailable: '+str(error)) from None

    def preflight(self):
        # Observe a quiet five-second interval before importing numerical code.
        self.check()
        for _ in range(5):sleep(1);self.check()


def run_training_worker(argv,*,check,seconds=90,env=None):
    """Monitor at 250 ms intervals and kill only this fresh worker group."""
    if (type(seconds) is not int or not 1<=seconds<=90 or not isinstance(argv,(list,tuple)) or not 1<=len(argv)<=64 or
            any(not isinstance(arg,str) or not arg or '\0' in arg or len(arg)>8192 for arg in argv) or
            sum(map(len,argv))>32768 or not Path(argv[0]).is_absolute()):raise ValueError('bounded training worker required')
    check();deadline=monotonic()+seconds
    worker=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                            start_new_session=True,close_fds=True,env=env)
    raw=bytearray()
    def drain():
        while True:
            try:part=os.read(worker.stdout.fileno(),16385-len(raw))
            except BlockingIOError:return
            if not part:return
            raw.extend(part)
            if len(raw)>16384:raise ValueError('bounded training result required')
    try:
        os.set_blocking(worker.stdout.fileno(),False)
        while True:
            drain()
            check()
            remaining=deadline-monotonic()
            if remaining<=0:raise ValueError('training worker deadline exceeded')
            result=os.waitid(os.P_PID,worker.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if result is not None:
                status=result.si_status if result.si_code==os.CLD_EXITED else -result.si_status
                # Kill inherited descendants before reading: they may hold the pipe.
                try:os.killpg(worker.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                drain()
                check();return status,bytes(raw)
            sleep(min(.25,remaining))
    finally:
        try:os.killpg(worker.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        worker.wait(timeout=2)
        worker.stdout.close()



def run_collection_worker(argv,*,seconds=90):
    """Explicit small acquisition/assembly profile; never authorize fitting."""
    from thermal_installed_intel import _resource_preflight
    _resource_preflight()
    monitor=TrainingHeadroom();monitor.preflight()
    env=dict(os.environ,EARTHSHIP_GUARDED_CAPTURE_WORKER='1',EARTHSHIP_QUALIFICATION_FIT='0',
             EARTHSHIP_REMOTE_QUALIFICATION_FIT='0',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    status,_=run_training_worker(argv,check=monitor.check,seconds=seconds,env=env)
    return status
