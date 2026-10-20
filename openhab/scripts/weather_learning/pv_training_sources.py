"""Original Google PV forcing with explicit experimental availability clocks."""
from datetime import timedelta
from .contracts import instant
from .archive import Archive
from .historical import verify_history


def forecast_origin(snapshot,*,recorded):
    if not recorded:return instant(snapshot['initialized_at'])+timedelta(hours=9)
    available=instant(snapshot['ingestion_completed_at']);origin=available.replace(minute=0,second=0,microsecond=0)
    return origin if origin==available else origin+timedelta(hours=1)


def ordered_runs(runs):
    # Recorded origins can precede the assumed nine-hour historical clock.
    # Pair lookup uses bisect and therefore must sort across both archives.
    selected={}
    for row in sorted(runs,key=lambda r:(r[0],r[1])):selected.setdefault(row[0],row)
    return [selected[k] for k in sorted(selected)]


def weather_runs(archive_path,operational_path,*,floor,end,site,guard):
    archive=Archive.open_readonly(str(archive_path))
    with archive._connect() as c:
        refs=c.execute('SELECT digest FROM snapshots WHERE historical=1 AND initialized>=? AND initialized<? ORDER BY initialized,completed,digest LIMIT 1001',(floor.isoformat(),end.isoformat())).fetchall()
    sources=[(archive,pin,False) for (pin,) in refs]
    if operational_path is not None:
        operational=Archive.open_readonly(str(operational_path));lower=max(floor,end-timedelta(days=90))
        with operational._connect() as c:
            refs=c.execute("SELECT digest FROM (SELECT digest,initialized,ROW_NUMBER() OVER (PARTITION BY initialized ORDER BY completed DESC,digest DESC) AS n FROM snapshots WHERE historical=0 AND initialized>=? AND completed<? AND substr(initialized,12,2) IN ('00','06','12','18')) WHERE n=1 ORDER BY initialized LIMIT 361",(lower.isoformat(),end.isoformat())).fetchall()
        if len(refs)>360:raise ValueError('bounded recorded operational PV sources required')
        sources.extend((operational,pin,True) for (pin,) in refs)
    if not 1<=len(sources)<=1000:raise ValueError('bounded original PV weather sources required')
    runs=[]
    for archive,pin,recorded in sources:
        guard();snapshot=verify_history(archive.read(pin))
        if snapshot['site']!=site:raise ValueError('PV weather site differs')
        hours={}
        for point in snapshot['points']:
            if point['statistic']!='mean' or point['variable'] not in ('station_head_temperature_2m','surface_solar_radiation_downwards_1hr','wind_speed_10m'):continue
            name=point['variable'];expected={'station_head_temperature_2m':('degC',0),'surface_solar_radiation_downwards_1hr':('W m-2',3600),'wind_speed_10m':('m s-1',0)}[name]
            if (point['unit'],point['period_seconds'])!=expected:raise ValueError('native PV weather units or period differ')
            hours.setdefault(point['valid_at'],{})[name]=point['value']
        basis='retrospective_recorded_ingestion_next_whole_hour' if recorded else 'retrospective_assumed_full_cycle_9h'
        runs.append((forecast_origin(snapshot,recorded=recorded),pin,hours,basis))
    return ordered_runs(runs)
