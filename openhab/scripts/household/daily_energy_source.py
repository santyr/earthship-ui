"""Retained daily arguments matched to a published receipt, without qualification.

The state is observed after issue. Matching its arithmetic and source references
is not proof of calibrated capacity, causal benefit, or protected as-issued input
capture. Household plans retain this distinction and remain shadow-only.
"""
from hashlib import sha256
from zoneinfo import ZoneInfo
from .codec import canonical,loads
from .control_contracts import instant
from .evidence import digest,utc

SCHEMA='earthship-household-daily-energy-source/v1'
FIELDS={'schema','collected_at','prediction_day','record','receipt_raw','receipt_sha256','state_sha256'}
RECORD_FIELDS={'temperature_issued_at','household_energy_inputs','pv','curtail','trough','soc_origin','weather_origin'}
MAX_BYTES=65536
ZONE=ZoneInfo('America/Denver')


def daily_inputs(source,*,as_of):
    """Return independent exact daily inputs only for their original local day."""
    from .energy_model import freeze_energy_inputs,daily_energy_projection
    if not isinstance(source,dict) or set(source)!=FIELDS or source['schema']!=SCHEMA:
        raise ValueError('closed retained daily energy source required')
    if len(canonical(source))>MAX_BYTES:raise ValueError('bounded daily energy source required')
    digest(source['state_sha256']);digest(source['receipt_sha256'])
    at=utc(as_of);collected=instant(source['collected_at'])
    raw=source['receipt_raw']
    if not isinstance(raw,str) or len(raw.encode())>4096 or sha256(raw.encode()).hexdigest()!=source['receipt_sha256']:
        raise ValueError('original daily forecast receipt differs')
    receipt=loads(raw);record=source['record']
    if not isinstance(record,dict) or set(record)!=RECORD_FIELDS or not isinstance(receipt,dict):
        raise ValueError('closed retained daily arguments required')
    day=at.astimezone(ZONE).date().isoformat()
    issued=instant(record['temperature_issued_at'])
    if (source['prediction_day']!=day or receipt.get('predictionDay')!=day or
        type(receipt.get('version')) is not int or receipt['version']!=1 or
        receipt.get('issuedAt')!=record['temperature_issued_at'] or
        issued.astimezone(ZONE).date().isoformat()!=day or not issued<=collected<=at):
        raise ValueError('daily forecast unavailable for this snapshot day')
    if not isinstance(record['household_energy_inputs'],dict):raise ValueError('original daily argument object required')
    inputs=freeze_energy_inputs(**record['household_energy_inputs']).to_dict()['inputs']
    output=daily_energy_projection(**inputs)
    for computed,saved,published in (('pv_pred','pv','pvTodayKwh'),('curtail','curtail','curtailmentHoursToday'),('trough_pred','trough','overnightTroughSocPct')):
        # Canonical comparison rejects booleans masquerading as numeric output.
        if published not in receipt or canonical(output[computed])!=canonical(record[saved]) or canonical(record[saved])!=canonical(receipt[published]):
            raise ValueError('daily energy arguments do not reproduce original publication')
    if receipt.get('energySocOrigin')!=record['soc_origin']:
        raise ValueError('daily energy SoC origin differs')
    weather=record['weather_origin']
    if receipt.get('weatherInputSha256') is not None and (not isinstance(weather,dict) or receipt['weatherInputSha256']!=weather.get('sha256')):
        raise ValueError('daily energy weather origin differs')
    return inputs


def capture_daily_source(state_raw,receipt_raw,*,collected_at):
    """Freeze the selected record; never keep a mutable state reference."""
    if not isinstance(state_raw,bytes) or len(state_raw)>2097152:
        raise ValueError('bounded daily state required')
    state=loads(state_raw)
    day=utc(collected_at).astimezone(ZONE).date().isoformat()
    record=state['predictions'][day]
    value=dict(schema=SCHEMA,collected_at=utc(collected_at).isoformat(),prediction_day=day,
        record={key:record.get(key) for key in RECORD_FIELDS},receipt_raw=receipt_raw,
        receipt_sha256=sha256(receipt_raw.encode()).hexdigest(),state_sha256=sha256(state_raw).hexdigest())
    daily_inputs(value,as_of=collected_at)
    return loads(canonical(value))
