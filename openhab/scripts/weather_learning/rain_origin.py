"""Actual current counter context; an unknown epoch never supports a local model."""
from dataclasses import asdict
from datetime import timedelta
from .contracts import canonical,identity,instant
from .rain_calibration import _policy,_resolution
from weather_rain_evidence import RainPolicy
from weather_rain_day import parse_rain_snapshot


def make_origin(*,raw,requested_at,received_at,policy,cutover,resolution_source,experiment_policy):
    requested,received,cutover=map(instant,(requested_at.isoformat(),received_at.isoformat(),cutover.isoformat()))
    experiment_policy=_policy(experiment_policy)
    if not isinstance(policy,RainPolicy) or not requested<=received<=requested+timedelta(seconds=5) or cutover>requested:raise ValueError('bounded actual rain-origin acquisition required')
    if raw is not None and (not isinstance(raw,str) or len(raw.encode())>4096):raise ValueError('bounded literal native rain origin required')
    status='unavailable';epoch=None;reason='current_native_receipt_unavailable'
    if raw is not None:
        try:
            sample=parse_rain_snapshot(raw,received,policy);epoch=sample.epoch;status='available';reason=None
        except (ValueError,TypeError,KeyError):pass
    resolution_pin=None;resolution_reason='measured_resolution_required'
    if resolution_source is not None:
        try:_resolution(resolution_source,policy=policy,received=received);resolution_pin=identity(resolution_source);resolution_reason=None
        except (ValueError,TypeError,KeyError):resolution_reason='independent_resolution_not_available'
    cohort=identity(dict(source_item='Weather_Rain_Evidence_JSON',policy_sha256=identity(asdict(policy)),cutover=cutover.isoformat(),stream_epoch=epoch,resolution_source_sha256=resolution_pin,experiment_policy_sha256=experiment_policy['policy_sha256']))
    value=dict(schema='earthship-original-rain-origin/v1',sources=dict(raw=raw,requested_at=requested.isoformat(),received_at=received.isoformat(),policy=asdict(policy),cutover=cutover.isoformat(),resolution_source=resolution_source,experiment_policy=experiment_policy),status=status,reason=reason,stream_epoch=epoch,resolution_source_sha256=resolution_pin,resolution_reason=resolution_reason,cohort_sha256=cohort,physical_calibration_qualified=False,automatic_actuation=False)
    value['context_sha256']=identity(value);return value


def validate_origin(value):
    if not isinstance(value,dict) or len(canonical(value))>131072 or value.get('schema')!='earthship-original-rain-origin/v1':raise ValueError('bounded original rain context required')
    source=value['sources'];rebuilt=make_origin(raw=source['raw'],requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),policy=RainPolicy(**source['policy']),cutover=instant(source['cutover']),resolution_source=source['resolution_source'],experiment_policy=source['experiment_policy'])
    if canonical(value)!=canonical(rebuilt):raise ValueError('original rain context differs')
    return rebuilt
