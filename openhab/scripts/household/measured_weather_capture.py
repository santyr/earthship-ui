"""Fixed read-only receiver/policy acquisition inside one common deadline."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import time,urllib.request,urllib.error
from .codec import loads
from .evidence import utc,epoch
from .energy_configuration_capture import _owned_text
from .measured_weather import SOURCES,prepare_measured_weather

FIXED_POLICY_PATHS={'radiation':Path('/home/sat/.config/hex/weather-radiation-policy.json'),
                    'rain':Path('/home/sat/.config/hex/weather-rain-policy.json')}


def _runtime_manifest():
    from household_pipeline import pipeline_runtime_manifest
    return pipeline_runtime_manifest(expanded=True,configured=True,measured=True)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('fixed receiver redirects refused')


def _http_get(*,kind,url,remaining):
    if kind not in SOURCES or url!=SOURCES[kind][1]:raise ValueError('fixed original receiver endpoint required')
    budget=remaining()
    if type(budget) not in (int,float) or not 0.001<=budget<=15.:raise ValueError('receiver budget unavailable')
    request=urllib.request.Request(url,method='GET',headers={'Accept':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    try:
        with opener.open(request,timeout=min(2.,budget)) as response:
            if response.status!=200 or response.geturl()!=url:raise ValueError('fixed receiver response identity required')
            raw=response.read(SOURCES[kind][2]+1)
        remaining()
    except urllib.error.HTTPError as error:
        if error.code in (404,503):return None
        raise ValueError('receiver transport unavailable') from None
    except (urllib.error.URLError,TimeoutError,OSError):return None
    if len(raw)>SOURCES[kind][2]:raise ValueError('original receiver response exceeds bound')
    try:return raw.decode('utf-8')
    except UnicodeError:raise ValueError('original receiver encoding unavailable') from None


def _owner(kind,raw):
    if raw is None:return None
    try:
        value=loads(raw);names=('sequence','faultCount') if kind=='radiation' else ('packetCount','invalidPackets','counterDrops','counterJumps')
        if set(value)!={'version','streamEpoch','record',*names} or type(value['version']) is not int or value['version']!=(2 if kind=='radiation' else 1):return None
        current=epoch(value['streamEpoch']);counts=tuple(value[name] for name in names)
        if any(type(number) is not int or not 0<=number<=2**53-1 for number in counts) or any(number>counts[0] for number in counts[1:]):return None
        return current,counts
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return None


def collect_measured_weather(*,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,remaining=None,source_getter=None):
    started=utc(clock());deadline=monotonic()+15.
    def check():
        local=deadline-monotonic()
        if not 0.001<=local<=15.:raise ValueError('local measured-weather deadline elapsed')
        outer=local if remaining is None else remaining()
        if type(outer) not in (int,float) or not 0.001<=outer<=15.:raise ValueError('common measured-weather deadline elapsed')
        return min(local,outer)
    if set(FIXED_POLICY_PATHS)!=set(SOURCES):raise ValueError('fixed complete policy sources required')
    check();runtime=_runtime_manifest();check();policies={};policy_at={}
    for kind,path in FIXED_POLICY_PATHS.items():
        policies[kind]=_owned_text(path,4096,check)
        if policies[kind][1] is not None and policies[kind][1][2]&0o022:raise ValueError('non-writable owned source policy required')
        policy_at[kind]=utc(clock())
    getter=_http_get if source_getter is None else source_getter
    def read(kind):
        check();raw=getter(kind=kind,url=SOURCES[kind][1],remaining=check);check()
        if raw is not None and (not isinstance(raw,str) or len(raw.encode())>SOURCES[kind][2]):raise ValueError('bounded original receiver text required')
        return raw,utc(clock())
    before={kind:read(kind) for kind in SOURCES};after={kind:read(kind) for kind in SOURCES}
    rows={}
    for kind,(name,url,_) in SOURCES.items():
        initial=_owner(kind,before[kind][0]);final=_owner(kind,after[kind][0])
        if initial is not None and final is not None and (initial[0]!=final[0] or any(new<old for old,new in zip(initial[1],final[1]))):
            raise ValueError('source owner epoch or cumulative counters changed inconsistently')
        raw,available=after[kind];policy_raw=policies[kind][0]
        rows[kind]=dict(source_identity=name,source_endpoint=url,raw=raw,sha256=None if raw is None else sha256(raw.encode()).hexdigest(),
            available_at=available.isoformat(),expected_epoch=None if initial is None else initial[0],policy_raw=policy_raw,
            policy_sha256=None if policy_raw is None else sha256(policy_raw.encode()).hexdigest(),policy_available_at=policy_at[kind].isoformat())
    for kind,path in FIXED_POLICY_PATHS.items():
        if _owned_text(path,4096,check)!=policies[kind]:raise ValueError('original source policy changed')
    check()
    if _runtime_manifest()!=runtime:raise ValueError('source runtime or registry changed')
    check();finished=utc(clock())
    if not started<=finished<=started+timedelta(seconds=15) or any(not started<=at<=finished for at in [*policy_at.values(),*[at for _,at in before.values()],*[at for _,at in after.values()]]):
        raise ValueError('original collection wall clock changed')
    result=prepare_measured_weather(sources=rows,as_of=finished,created_at=finished);check()
    return result
