"""Single-owner shadow acquisition; no OpenHAB publishing or control API."""
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl,os,pathlib,shutil,stat,time
from .contracts import identity,validate_snapshot

DEFAULT_BANDS={
 'station':('station_head_temperature_2m_mean','station_head_temperature_2m_p10','station_head_temperature_2m_p90','station_head_dewpoint_temperature_2m_mean'),
 'gridded':('surface_solar_radiation_downwards_1hr_mean','total_sky_direct_solar_radiation_at_surface_1hr_mean',
            'total_precipitation_1hr_mean','imerg_tp_1hr_mean','experimental_tp_1hr_mean',
            'wind_speed_10m_mean','total_cloud_cover_mean','mean_sea_level_pressure_mean'),
}

@contextmanager
def collector_lock(path):
    path=pathlib.Path(path)
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,0o600)
    try:
        meta=os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.getuid() or meta.st_mode&0o077:raise ValueError('private owned collector lock required')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)


def collect_once(reader,archive,*,probe=True,horizon=360,free_bytes=None,max_archive_bytes=16*1024**3):
    if type(probe) is not bool or type(horizon) is not int or not 1<=horizon<=360:
        raise ValueError('bounded explicit shadow acquisition required')
    if type(max_archive_bytes) is not int or not 16*1024**2<=max_archive_bytes<=16*1024**3:
        raise ValueError('bounded archive capacity required')
    with collector_lock(archive.root/'collector.lock'):
        free=shutil.disk_usage(archive.root).free if free_bytes is None else free_bytes
        if type(free) is not int or free<16*1024**2:raise ValueError('insufficient private archive headroom')
        used=0
        for index,path in enumerate(archive.objects.glob('*.json')):
            if index>=10000:raise ValueError('archive object-count limit reached')
            used+=path.stat().st_size
        if used+8*1024**2>max_archive_bytes:raise ValueError('private archive capacity exhausted')
        started=time.monotonic();reader.initialize()
        targets=1 if probe else horizon
        bands={'station':('station_head_temperature_2m_mean',)} if probe else DEFAULT_BANDS
        run=reader.discover_run(horizon=targets)
        snapshot=validate_snapshot(reader.fetch_points(run=run,bands_by_grid=bands,horizon=targets))
        name=identity(snapshot) if probe else archive.store_snapshot(snapshot)
        return dict(schema='earthship-weathernext-ingest-result/v1',status='PROBE_PASSED' if probe else 'ARCHIVED',
            provider='weathernext3',run_id=snapshot['run_id'],snapshot_sha256=name,
            ingestion_completed_at=snapshot['ingestion_completed_at'],points=len(snapshot['points']),
            elapsed_seconds=round(time.monotonic()-started,3),production_writes=False,automatic_actuation=False)
