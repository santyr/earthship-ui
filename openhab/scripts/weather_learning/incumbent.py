"""Temporary migration control only. Never imported by the fitting pipeline."""
import json
from .contracts import finite,identity,instant
from .evidence import utc


def capture_incumbent(raw,*,observed_at,site):
    observed_at=utc(observed_at)
    if not isinstance(raw,str) or len(raw.encode())>=65536:raise ValueError('bounded original incumbent state required')
    body=json.loads(raw)
    if not isinstance(body,dict) or type(body.get('version')) is not int or body['version'] not in (1,2) or body.get('timezone')!=site.timezone:raise ValueError('known site forecast control required')
    generated=instant(body['generatedAt'])
    if not 0<=(observed_at-generated).total_seconds()<=86400:raise ValueError('fresh control observed before decision required')
    days=body.get('days')
    if not isinstance(days,list) or len(days)>10:raise ValueError('bounded original control days required')
    values={};count=0
    for day in days:
        if not isinstance(day,dict) or not isinstance(day.get('hours'),list):raise ValueError('original control hours required')
        for row in day['hours']:
            count+=1
            if count>250 or not isinstance(row,dict):raise ValueError('bounded control hours required')
            at=instant(row['at']);value=row['tempF']
            if at in values or (value is not None and not finite(value)):raise ValueError('unique finite control temperatures required')
            values[at]=None if value is None else (value-32)*5/9
    original=dict(item='Forecast_10Day_JSON',state=raw,observed_at=observed_at.isoformat())
    return dict(provider='openmeteo',sourceSha256=identity(original),generatedAt=generated.isoformat(),observedAt=observed_at.isoformat()),values,original
