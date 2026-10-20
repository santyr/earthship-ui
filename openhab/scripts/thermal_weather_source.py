"""Collect optional thermal weather context from owned, already available files."""
from pathlib import Path
from datetime import datetime,date,time,timedelta,timezone
from hashlib import sha256
from zoneinfo import ZoneInfo
import json,os,stat
from copy import deepcopy
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.thermal_weather_conditioning import validate_admission,validate_context
from weather_source_files import _read

SCRIPTS=Path(__file__).resolve().parent
RUNTIME_SOURCES=('thermal_model/installed_shade_origin.py','thermal_weather_source.py','household/thermal_weather_conditioning.py','household/codec.py','household/control_contracts.py',
    'weather_learning/site_calibration.py','weather_learning/irradiance_learning.py','weather_learning/historical_serving.py',
    'weather_learning/contracts.py','household_solar_horizon.py')
SELECTION_FIELDS={'schema','admission_path','admission_file_sha256','available_at','automatic_actuation','selection_sha256'}


def conditioning_runtime():
    return {name:sha256((SCRIPTS/name).read_bytes()).hexdigest() for name in RUNTIME_SOURCES}


def hash_reference(ref,*,guard):
    path=Path(ref['path']);maximum=ref['maximum'];source=ref['source']
    if not path.is_absolute() or path.resolve()!=path or type(maximum) is not int or not 1<=maximum<=32*1024**2 or type(source) is not bool:raise ValueError('bounded resolved thermal source required')
    info=path.lstat();owners=(0,os.getuid()) if source else (os.getuid(),)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid not in owners or info.st_mode&0o022 or info.st_size>maximum or
            not source and (stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1)):
        raise ValueError('owned bounded thermal weather source required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC);digest=sha256();size=0
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        if (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('thermal source inode changed')
        while True:
            guard();raw=f.read(262144)
            if not raw:break
            size+=len(raw)
            if size>maximum:raise ValueError('bounded thermal source bytes required')
            digest.update(raw)
        after=os.fstat(f.fileno())
    if (size!=info.st_size or (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns) or digest.hexdigest()!=ref['sha256']):raise ValueError('original thermal weather source changed')


def _cache_positions(ref,*,site,runtime,zone,available):
    from astro_geometry_series import build_series_request,replay_series
    day=date.fromisoformat(ref['day']);start=datetime.combine(day,time.min,ZoneInfo(zone)).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),time.min,ZoneInfo(zone)).astimezone(timezone.utc)
    points=[];at=start
    while at<end:at+=timedelta(minutes=5);points.append(at)
    raw=_read(ref['path'],524288);value=loads(raw)
    if sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('original native geometry source changed')
    request=build_series_request(points,requested_at=value['request']['requested_at'],latitude=site['latitude'],longitude=site['longitude'],timezone_name=zone)
    series=replay_series(raw,request=request,expected_series_sha256=value['series_sha256'],expected_native_runtime=runtime)
    actual=instant(series.descriptor()['available_at'])
    if actual>available or 'available_at' in ref and instant(ref['available_at'])!=actual:raise ValueError('native cached geometry unavailable during collection')
    return [row for cache in series.to_dict()['caches'] for row in cache['positions']],actual.isoformat()


def _midpoints(rows,issue):return [(instant(row['at'])-timedelta(minutes=30)).isoformat() for row in rows if instant(row['at'])>issue]


def collect_context(*,selection,forecast,geometry,issue,sensor_epoch,guard,geometry_root=None,clock=lambda:datetime.now(timezone.utc)):
    """Read only; missing geometry is never calculated in the serving cycle."""
    guard();raw=_read(selection,16384);selected=loads(raw)
    if (set(selected)!=SELECTION_FIELDS or selected['schema']!='earthship-thermal-weather-selection/v1' or selected['automatic_actuation'] is not False or
            selected['selection_sha256']!=identity({k:v for k,v in selected.items() if k!='selection_sha256'})):
        raise ValueError('explicit owned thermal weather selection required')
    admission_raw=_read(selected['admission_path'],32768);admission=loads(admission_raw)
    if sha256(admission_raw).hexdigest()!=selected['admission_file_sha256']:raise ValueError('original thermal admission source changed')
    validate_admission(admission,issue=issue)
    if admission['source_sensor_epoch']!=sensor_epoch or admission['runtime_manifest']!=conditioning_runtime():raise ValueError('thermal weather runtime or sensor phase changed')
    if not instant(admission['admitted_at'])<=instant(selected['available_at'])<=clock():raise ValueError('thermal weather selection unavailable during collection')
    for ref in admission['originals']:hash_reference(ref,guard=guard)
    packet=geometry.to_dict();descriptor=geometry.descriptor();site=descriptor['site'];zone=descriptor['timezone'];runtime=packet['native_runtime']
    targets=_midpoints(forecast['rows'],issue);days=sorted({instant(at).astimezone(ZoneInfo(zone)).date().isoformat() for at in targets});positions={};refs=[]
    cache=Path.home()/'.local/state/earthship-weather/daily-pv/geometry' if geometry_root is None else Path(geometry_root)
    for day in days:
        guard();key=identity(dict(day=day,site=dict(latitude=site['latitude'],longitude=site['longitude'],timezone=zone),native_runtime=runtime));path=cache/(key+'.geometry.json')
        body=_read(path,524288);ref=dict(path=str(path),sha256=sha256(body).hexdigest(),maximum=524288,source=False,day=day)
        rows,available=_cache_positions(ref,site=site,runtime=runtime,zone=zone,available=clock());ref['available_at']=available;refs.append(ref);positions.update({r['at']:r for r in rows})
    points=[positions[at] for at in targets]
    ref=dict(path=selected['admission_path'],sha256=selected['admission_file_sha256'],maximum=32768,source=False)
    value=dict(schema='earthship-thermal-weather-context/v1',issue=issue.isoformat(),prepared_at=clock().isoformat(),admission=admission,admission_ref=ref,
        selection=selected,forecast_sha256=identity(forecast),rows=deepcopy(forecast['rows']),midpoint_positions=points,geometry_refs=refs,native_runtime=runtime,site=site,timezone=zone,automatic_actuation=False)
    value['context_sha256']=identity(value)
    validate_context(value,issue=issue,available=instant(value['prepared_at']),forecast=forecast,sensor_epoch=sensor_epoch)
    if _read(selection,16384)!=raw or conditioning_runtime()!=admission['runtime_manifest']:raise ValueError('thermal selection changed during collection')
    return value


def verify_bindings(value,*,guard):
    """Validate as-issued immutable sources, without rereading today's selector."""
    issue=instant(value['issue']);validate_context(value,issue=issue,available=instant(value['prepared_at']))
    admission=value['admission'];selected=value['selection'];ref=value['admission_ref']
    if (set(selected)!=SELECTION_FIELDS or selected['selection_sha256']!=identity({k:v for k,v in selected.items() if k!='selection_sha256'}) or
            selected['admission_path']!=ref['path'] or selected['admission_file_sha256']!=ref['sha256'] or
            not instant(admission['admitted_at'])<=instant(selected['available_at'])<=instant(value['prepared_at'])):
        raise ValueError('original thermal selection source differs')
    hash_reference(ref,guard=guard)
    if canonical(loads(_read(ref['path'],32768)))!=canonical(admission) or conditioning_runtime()!=admission['runtime_manifest']:
        raise ValueError('original thermal admission or runtime source differs')
    for source in admission['originals']:hash_reference(source,guard=guard)
    points={}
    for geometry in value['geometry_refs']:
        hash_reference(geometry,guard=guard)
        site=value['site']
        rows,_=_cache_positions(geometry,site=site,runtime=value['native_runtime'],zone=value['timezone'],available=instant(value['prepared_at']))
        points.update({row['at']:row for row in rows})
    if canonical([points[at] for at in _midpoints(value['rows'],issue)])!=canonical(value['midpoint_positions']):raise ValueError('original thermal midpoint source differs')
