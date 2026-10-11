"""Original delivered energy forecast errors; no causal or action qualification."""
from datetime import date,timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
import math
from .codec import canonical,loads,identity
from .control_contracts import instant
from .pipeline import replay_pipeline
from .planning import _runtime_manifest
from .energy_outcome_sources import replay_night_source
from advisory_windows import trough_window

MAX_BYTES=6*1024*1024
FIELDS={'schema','inputs','outcome_runtime_manifest','output','receipt_sha256'}
INPUTS={'plan_receipt','forecast_source','night_source'}
FORECAST_FIELDS={'version','predictionDay','issuedAt','pvTodayKwh','curtailmentHoursToday','overnightTroughSocPct','thermalAdvisory'}
ORIGIN_FIELDS={'version','assessedAtMs','recordedAtMs','validUntilMs','streamEpoch','evidenceSha256','socPct'}


def _forecast(source,snapshot):
    if (not isinstance(source,dict) or set(source)!={'source_identity','persisted_at','raw','sha256'} or
        source['source_identity']!='Forecast_Prediction_Receipt_JSON' or not isinstance(source['raw'],str) or len(source['raw'].encode())>4096 or
        sha256(source['raw'].encode()).hexdigest()!=source['sha256']):raise ValueError('exact original persisted energy forecast required')
    value=loads(source['raw'])
    if (not isinstance(value,dict) or not FORECAST_FIELDS<=set(value) or
        not set(value)<=FORECAST_FIELDS|{'energySocOrigin','pvDiagnostics','solarContextOrigin','weatherInputSha256'} or
        type(value['version']) is not int or value['version']!=1):raise ValueError('supported original energy forecast receipt required')
    day=date.fromisoformat(value['predictionDay']);issued=instant(value['issuedAt']);persisted=instant(source['persisted_at'])
    asof=instant(snapshot['as_of']);created=instant(snapshot['created_at']);window=trough_window(day,'America/Denver')
    if (day.isoformat()!=value['predictionDay'] or issued.astimezone(ZoneInfo('America/Denver')).date()!=day or
        asof.astimezone(ZoneInfo('America/Denver')).date()!=day or not issued<=asof<=created<=persisted<window.start or
        persisted-asof>timedelta(seconds=120)):
        raise ValueError('original energy publication chronology differs')
    number=value['overnightTroughSocPct']
    if number is not None and (type(number) not in (int,float) or not math.isfinite(number) or not 0<=number<=100):
        raise ValueError('bounded original energy prediction required')
    return value,day,persisted


def _origin(value,snapshot):
    row=snapshot['domains']['energy']['battery_soc'];ref=row['evidence'];origin=value.get('energySocOrigin')
    if (not isinstance(origin,dict) or set(origin)!=ORIGIN_FIELDS or type(origin['version']) is not int or origin['version']!=1 or
        ref is None or ref['quality']!='qualified' or row['reason'] is not None or row['value'] is None or
        ref['source_identity']!='BMS_SOC_Evidence_JSON'):
        raise ValueError('original qualified atomic SoC origin required')
    for key,expected in (
        ('assessedAtMs',int(instant(snapshot['as_of']).timestamp()*1000)),
        ('recordedAtMs',int(instant(ref['received_at']).timestamp()*1000)),
        ('validUntilMs',int(instant(ref['valid_until']).timestamp()*1000))):
        if type(origin[key]) is not int or origin[key]!=expected:raise ValueError('original atomic SoC clocks differ')
    if (origin['streamEpoch']!=ref['source_epoch'] or origin['evidenceSha256']!=ref['digest'] or
        type(origin['socPct']) not in (int,float) or origin['socPct']!=row['value']):
        raise ValueError('original atomic SoC identity differs')
    return origin


def seal_energy_outcomes(*,plan_receipt,forecast_source,night_source,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime):
    runtime=_runtime_manifest(outcome_runtime_manifest)
    plan=replay_pipeline(plan_receipt,runtime_manifest=plan_runtime_manifest,thermal_runtime=thermal_runtime)
    snapshot=plan['inputs']['snapshot'];energy=plan['output']['projections']['energy']
    assessment=None if night_source is None else replay_night_source(night_source)
    forecast=None if forecast_source is None else _forecast(forecast_source,snapshot)
    reason=None;stream_changed=None
    if energy is None or energy['output']['trough_pred'] is None:reason='original_energy_model_unavailable'
    elif forecast is None:reason='original_prediction_receipt_required'
    else:
        value,day,persisted=forecast;origin=_origin(value,snapshot)
        if value['overnightTroughSocPct']!=energy['output']['trough_pred']:
            raise ValueError('delivered energy prediction differs from original model')
        if night_source is None:reason='original_whole_night_evidence_required'
        else:
            stream_changed=night_source['expected_stream_epoch']!=origin['streamEpoch']
            if stream_changed and night_source['owner_binding'] is None:
                raise ValueError('changed producer stream lacks independent later owner binding')
            if (night_source['prediction_day']!=day.isoformat() or
                instant(night_source['assessed_at'])<persisted):raise ValueError('night outcome differs from original energy target or phase')
            bank=next(row for row in loads(night_source['bank_config_raw'])['epochs'] if row['id']==night_source['expected_bank_epoch'])
            capacity=plan['inputs']['energy_inputs']['numerical_inputs']['inputs']['bank_kwh']
            if bank.get('nominal_usable_kwh')!=capacity:raise ValueError('original numerical capacity differs from physical bank')
            if assessment['status']!='measured':reason=assessment['reason']
    target=None if forecast is None else trough_window(forecast[1],'America/Denver')
    within_horizon=None if target is None else target.end<=instant(snapshot['as_of'])+timedelta(hours=plan['inputs']['config']['horizon_hours'])
    output=dict(daily_model_target=None if target is None else dict(basis='legacy_daily_next_night_minimum',window_start=target.start.isoformat(),window_end=target.end.isoformat()),
        planner_horizon_hours=plan['inputs']['config']['horizon_hours'],outcome_within_planner_horizon=within_horizon,
        evaluation_scope='retrospective_planner_from_original_delivered_forecast',status='unavailable' if reason else 'scored',reason=reason,
        original_delivery_verified=forecast is not None,predicted_min_soc_pct=None if energy is None else energy['output']['trough_pred'],
        actual_min_soc_pct=None,error_soc_pct=None,absolute_error_soc_pct=None,reserve_violation=None,
        assessment=assessment,physical_bank_epoch=None if night_source is None else night_source['expected_bank_epoch'],
        bank_binding_scope='measurement_interval_and_original_numerical_capacity',original_bank_provenance_qualified=False,
        producer_stream_changed=stream_changed,
        causal_benefit_qualified=False,graduated=False,automatic_actuation=False)
    if reason is None:
        actual=assessment['min_soc_pct'];error=energy['output']['trough_pred']-actual
        output.update(actual_min_soc_pct=actual,error_soc_pct=error,absolute_error_soc_pct=abs(error),
            reserve_violation=actual<plan['inputs']['config']['reserve_soc'])
    value=dict(schema='earthship-household-energy-outcome-receipt/v1',inputs=dict(plan_receipt=plan,forecast_source=forecast_source,night_source=night_source),
        outcome_runtime_manifest=runtime,output=output)
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original energy score required')
    return loads(canonical(value))


def replay_energy_outcomes(receipt,*,plan_runtime_manifest,outcome_runtime_manifest,thermal_runtime):
    if (not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!='earthship-household-energy-outcome-receipt/v1' or
        len(canonical(receipt))>MAX_BYTES or not isinstance(receipt['inputs'],dict) or set(receipt['inputs'])!=INPUTS):
        raise ValueError('closed bounded original energy score required')
    runtime=_runtime_manifest(outcome_runtime_manifest)
    if canonical(runtime)!=canonical(receipt['outcome_runtime_manifest']):raise ValueError('executing energy outcome runtime differs')
    replayed=seal_energy_outcomes(**receipt['inputs'],plan_runtime_manifest=plan_runtime_manifest,outcome_runtime_manifest=runtime,thermal_runtime=thermal_runtime)
    if canonical(replayed)!=canonical(receipt):raise ValueError('rederived original energy score differs')
    return replayed
