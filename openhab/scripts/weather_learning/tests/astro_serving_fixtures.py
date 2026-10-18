"""Synthetic native Astro schedule; no historical or approximate sun model."""
from datetime import datetime,time,timedelta
import json
from zoneinfo import ZoneInfo
from learning_fixtures import SITE


def astro_source(decision,damage=None):
    zone=ZoneInfo(SITE.timezone);first=decision.astimezone(zone).date();days=[]
    for index in range(10):
        day=first+timedelta(days=index);base=datetime.combine(day,time.min,zone)
        rise=base+timedelta(hours=6,minutes=59);start=base+timedelta(hours=7);sunset=base+timedelta(hours=19)
        next_rise=base+timedelta(days=1,hours=6,minutes=59)
        days.append(dict(day=day.isoformat(),sunriseAt=rise.isoformat(),daylightStartAt=start.isoformat(),sunsetAt=sunset.isoformat(),
            nextSunriseAt=next_rise.isoformat(),daylightSeconds=43200,sunsetToNextSunriseSeconds=43140,
            noonElevationDegrees=45.,noonAzimuthDegrees=180.,noonReferenceRadiationWm2=600.))
    value=dict(version=1,schema='astro-future-solar-context/v1',sourceThing='astro:sun:local',calculationVersion='openhab-astro-5.2.3',
        timezone=SITE.timezone,geolocation=f'{SITE.latitude},{SITE.longitude}',recordedAt=(decision-timedelta(minutes=20)).isoformat(),
        validUntil=datetime.combine(first+timedelta(days=1),time.min,zone).isoformat(),days=days)
    available=decision-timedelta(minutes=10)
    if damage=='future':available=decision+timedelta(seconds=1)
    if damage=='expired':value['validUntil']=decision.isoformat()
    if damage=='site':value['geolocation']='38.3,-105.7'
    if damage=='version':value['calculationVersion']='openhab-astro-5.2.1'
    raw=json.dumps(value)
    if damage=='duplicate':raw=raw[:-1]+',"version":1}'
    return dict(raw=raw,available_at=available)
