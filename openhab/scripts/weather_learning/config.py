"""Explicit site, cost and request bounds; no implicit geographic fallback."""
from dataclasses import dataclass
import math
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

STATISTICS_BUCKET='weathernext3_statistics_spatial'
PROJECT='earthship-weather-research'
READER='weathernext-reader@'+PROJECT+'.iam.gserviceaccount.com'
COLLECTIONS={
 'gridded':'projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p1deg',
 'station':'projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p05deg',
}


@dataclass(frozen=True)
class AccessPolicy:
    backend:str='gcs'
    bucket:str=STATISTICS_BUCKET
    project:str=PROJECT
    requester_billing_project:str|None=None
    paid_access_allowed:bool=False
    full_ensemble_allowed:bool=False
    noncommercial_verified:bool=False
    max_bytes:int=8*1024*1024
    max_targets:int=360
    max_seconds:int=75
    max_attempts:int=2
    max_pixels:int=16

    def __post_init__(self):
        if (self.bucket!=STATISTICS_BUCKET or self.project!=PROJECT
                or self.requester_billing_project is not None
                or self.paid_access_allowed is not False or self.full_ensemble_allowed is not False):
            raise ValueError('statistics-only access without requester billing required')
        if self.backend not in ('gcs','earthengine'):
            raise ValueError('explicit approved backend required')
        if self.backend=='earthengine' and self.noncommercial_verified is not True:
            raise ValueError('approved noncommercial project verification required')
        for name,low,high in [('max_bytes',1024,64*1024*1024),('max_targets',1,360),
                ('max_seconds',1,180),('max_attempts',1,3),('max_pixels',1,16)]:
            value=getattr(self,name)
            if type(value) is not int or not low<=value<=high:
                raise ValueError('bounded '+name+' required')


@dataclass(frozen=True)
class Site:
    latitude:float
    longitude:float
    timezone:str

    def __post_init__(self):
        if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (self.latitude,self.longitude))
                or not -90<=self.latitude<=90 or not -180<=self.longitude<=180):
            raise ValueError('finite geographic coordinates required')
        try:ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError,TypeError,ValueError):raise ValueError('IANA timezone required') from None

    @classmethod
    def from_openhab_config(cls,config):
        try:
            latitude,longitude=map(float,config['location'].split(','))
            return cls(latitude,longitude,config['timezone'])
        except (KeyError,TypeError,AttributeError,ValueError):
            raise ValueError('authoritative OpenHAB regional configuration required') from None

    @property
    def longitude_360(self):return self.longitude%360
