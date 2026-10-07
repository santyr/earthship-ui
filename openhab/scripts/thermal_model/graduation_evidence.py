"""Read-only scoring of fully bound original thermal observations.

An archived original output must match a real persisted publication. Native
outcomes and same-origin recent-cycle receipts keep their source epochs/clocks.
Scoring supplies no release or causal action authority.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
import math
from pathlib import Path

from thermal_model.origin_capture import read_origin_capture
from thermal_model.temperature_history import _validate_receipt
from thermal_model.forcing_capture import _canonical
from thermal_model.recent_cycles import compare


def _utc(value):
    if isinstance(value,str):
        try:value=datetime.fromisoformat(value)
        except ValueError:raise ValueError('aware evidence timestamp required') from None
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError('aware evidence timestamp required')
    return value.astimezone(timezone.utc)


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('finite bounded evidence number required')
    return float(value)


def _object(pairs):
    value={}
    for key,entry in pairs:
        if key in value:raise ValueError('duplicate original publication key')
        value[key]=entry
    return value


def score_qualified_origin(*,origin_path,publication,horizon_hours,outcome,
                           recent_cycle_grid,assessed_at):
    """Derive signed errors from original output and native measurements only."""
    if type(horizon_hours) is not int or horizon_hours not in (1,6,12,24,48):
        raise ValueError('supported source-scored horizon required')
    record=read_origin_capture(Path(origin_path))
    return _score_origin_record(record,publication=publication,horizon_hours=horizon_hours,
        outcome=outcome,recent_cycle_grid=recent_cycle_grid,assessed_at=assessed_at)


def _score_origin_record(record,*,publication,horizon_hours,outcome,recent_cycle_grid,assessed_at):
    # Internal adapter: callers must have validated/read this immutable record.
    if type(horizon_hours) is not int or horizon_hours not in (1,6,12,24,48):
        raise ValueError('supported source-scored horizon required')
    issue=_utc(record['issued_at'])
    now=_utc(assessed_at)
    if (not isinstance(publication,dict) or set(publication)!={'time','state'} or
            type(publication['time']) is not int or not isinstance(publication['state'],str) or
            len(publication['state'].encode())>16384):
        raise ValueError('bounded original persisted publication required')
    stored=datetime.fromtimestamp(publication['time']/1000,timezone.utc)
    if not issue<=stored<=now or not _utc(record['published_at'])<=now:
        raise ValueError('publication was unavailable at recorded assessment')
    try:published=json.loads(publication['state'],object_pairs_hook=_object)
    except (json.JSONDecodeError,UnicodeDecodeError):raise ValueError('original publication invalid') from None
    if _canonical(published)!=_canonical(record['output']):
        raise ValueError('persisted publication differs from original captured output')
    target_mark=issue+timedelta(hours=horizon_hours)
    candidates=[(_utc(point['at']),point) for point in record['output']['forecast']['trajectory']
                if abs((_utc(point['at'])-target_mark).total_seconds())<=1800]
    if not candidates:raise ValueError('original horizon target unavailable')
    target,point=min(candidates,key=lambda value:(abs((value[0]-target_mark).total_seconds()),value[0]))
    if not stored<target<=now-timedelta(minutes=5):
        raise ValueError('qualified later outcome is not mature')
    if not isinstance(outcome,dict) or set(outcome)!={'target_at','receipt'} or _utc(outcome['target_at'])!=target:
        raise ValueError('native outcome target differs')
    receipt=outcome['receipt'];_validate_receipt(receipt,target)
    epoch=record['source_epochs']['air']
    if receipt['streamEpoch']!=epoch:raise ValueError('native outcome sensor epoch differs')
    if not isinstance(recent_cycle_grid,list) or len(recent_cycle_grid)>64:
        raise ValueError('bounded original recent-cycle receipt grid required')
    native={}
    for row in recent_cycle_grid:
        if not isinstance(row,(list,tuple)) or len(row)!=2:raise ValueError('native comparator row invalid')
        at=_utc(row[0])
        if at>=issue or at in native:raise ValueError('future or duplicate native comparator target')
        value=row[1]
        if value is not None:
            _validate_receipt(value,at)
            if value['streamEpoch']!=epoch:raise ValueError('native comparator epoch differs')
            value={**value,**{key:_utc(value[key]) for key in ('receivedAt','storedAt','validUntil')}}
        native[at]=value
    def read(targets,assessment):
        if assessment!=issue:raise ValueError('comparator used revised issue clock')
        return [(at,native.get(at)) for at in targets]
    current=_number(record['output']['current']['hallwayF'])
    baseline=compare(issue=issue,target=target,current_f=current,grid_reader=read)
    if baseline['status']!='available':raise ValueError('seven original qualified cycles unavailable')
    observed=_number(receipt['temperatureF'])
    rows=[entry for entry in record['forecast_rows'] if _utc(entry['at'])<=issue]
    if not rows:raise ValueError('original thermal regime unbound')
    selected=max(rows,key=lambda value:_utc(value['at']));mode=selected.get('mode')
    for effective,value in selected.get('_modeTimeline',[]):
        if _utc(effective)<=issue:mode=value
    regime={'warm':'warm','spring':'shoulder','fall_charge':'shoulder','winter':'winter'}.get(mode)
    if regime is None:raise ValueError('original thermal regime unsupported')
    scored=dict(issue_at=issue.isoformat(),target_at=target.isoformat(),horizon_hours=horizon_hours,
        regime=regime,artifact_sha256=record['sha256']['artifact'],runtime_sha256=record['sha256']['runtime'],
        sensor_epochs=dict(record['source_epochs']),model_error_f=_number(point['hallwayF'])-observed,
        persistence_error_f=current-observed,recent_cycle_error_f=baseline['prediction_f']-observed,
        interval_width_f=_number(point['highF'])-_number(point['lowF']),
        interval_covered=point['lowF']<=observed<=point['highF'])
    return dict(schema='earthship-thermal-source-scored-pair/v1',scored_pair=scored,
        original_capture_sha256=sha256(_canonical(record)).hexdigest(),
        publication_sha256=sha256(_canonical(publication)).hexdigest(),
        outcome_receipt_sha256=sha256(_canonical(outcome)).hexdigest(),
        recent_cycle_grid_sha256=sha256(_canonical(recent_cycle_grid)).hexdigest(),
        recent_cycle_evidence_sha256=baseline['evidence_sha256'],known_actions=record['known_actions'],
        forecast_source_binding_verified=True,action_response_qualification_claimed=False,release_authorized=False)
