"""Original-bound retrospective solar inputs, with no live forecast admission.

A historical availability assumption is explicitly separate from acquisition.
This packet cannot pass the operational native forecast validator. Its pure
component arithmetic is shared; its evidence class never becomes prospective.
"""
from .config import Site
from .contracts import canonical,identity,instant
from .evidence import utc
from .historical import verify_history
from .native_forecast import _snapshot,_encode,_decode,MAX_CAPSULE_BYTES,validate_native_forecast
from .native_solar_forecast import SOLAR_CONTRACT,SCHEMA as LIVE_SCHEMA,window,component_rows
from .pv_training_sources import forecast_origin

SCHEMA='earthship-retrospective-component-forcing/v1'
BASES={True:'retrospective_assumed_full_cycle_9h',False:'retrospective_recorded_ingestion_next_whole_hour'}


def make_retrospective_forcing(snapshot,*,origin,horizon_hours,site,assessed_at,availability_basis):
    origin,assessed=map(utc,(origin,assessed_at));targets=window(origin,horizon_hours)
    source=verify_history(snapshot)
    if (not isinstance(site,Site) or source['site']!=site.__dict__ or
            assessed<max(origin,instant(source['ingestion_completed_at']))):
        raise ValueError('original retrospective site and acquisition clocks required')
    historical=source['historical']
    if (availability_basis!=BASES[historical] or
            origin!=forecast_origin(source,recorded=not historical)):
        raise ValueError('retrospective origin must match the declared source availability basis')
    original={k:v for k,v in source.items() if k!='points'}
    rebuilt=_snapshot(original)
    if canonical(rebuilt)!=canonical(source):raise ValueError('original retrospective native source differs')
    source_hash=identity(source)
    if 'snapshot_sha256' in snapshot and snapshot['snapshot_sha256']!=source_hash:
        raise ValueError('original retrospective source identity differs')
    rows=component_rows(source,targets)
    value=dict(schema=SCHEMA,source='weathernext3',solar_input_contract=SOLAR_CONTRACT,
        origin=origin.isoformat(),horizon_hours=horizon_hours,issued_at=source['initialized_at'],
        captured_at=source['ingestion_completed_at'],assessed_at=assessed.isoformat(),
        availability_basis=availability_basis,site=source['site'],rows=rows,rows_sha256=identity(rows),
        snapshot_sha256=source_hash,source_original=_encode(original),as_issued_forecast=False,prospective_score=False,
        release_authorized=False,automatic_actuation=False)
    value['forecast_sha256']=identity(value)
    if len(canonical(value))>MAX_CAPSULE_BYTES:raise ValueError('bounded retrospective component packet required')
    return value


def validate_retrospective_forcing(value):
    if not isinstance(value,dict) or value.get('schema')!=SCHEMA or len(canonical(value))>MAX_CAPSULE_BYTES:
        raise ValueError('bounded original retrospective solar packet required')
    source=_snapshot(_decode(value['source_original']))
    rebuilt=make_retrospective_forcing(source,origin=instant(value['origin']),horizon_hours=value['horizon_hours'],
        site=Site(**value['site']),assessed_at=instant(value['assessed_at']),availability_basis=value['availability_basis'])
    if canonical(rebuilt)!=canonical(value):raise ValueError('retrospective packet differs from original native evidence')
    return value


def validate_component_input(value):
    """Only the new pure model accepts retrospective forcing, never v1 consumers."""
    from .scenarios import ScenarioForcing,validate_scenario
    if type(value) is ScenarioForcing:
        return validate_scenario(value),'constructed_unqualified_weather_sensitivity'
    if isinstance(value,dict) and value.get('schema')==SCHEMA:
        return validate_retrospective_forcing(value),'retrospective_development_forcing'
    value=validate_native_forecast(value)
    if value['schema']!=LIVE_SCHEMA:raise ValueError('explicit native component forcing required')
    return value,'original_prospective_forcing'
