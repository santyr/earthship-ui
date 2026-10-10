"""Source-valid provisional forecasts, separate from qualified publication profiles."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc
from .runtime_bundle import _owned_bytes,_write_private,_sync_directory
from .provisional_artifact import validate_candidate
from .installed_shade_dynamics import InstalledShadeDynamics
from .installed_shade_origin import _origin_actions,_forecast_forcing
from .origin_capture import _temperatures
from .installed_shade_raw_score_sources import build_compressed_native_origin_binding as build_binding,replay_compressed_native_origin_binding as replay_binding

CAPTURE_SCHEMA='earthship-provisional-thermal-origin/v1'
NUMERIC_SCHEMA='earthship-provisional-thermal-forecast/v1'
PUBLICATION_SCHEMA='earthship-provisional-thermal-publication/v1'
INPUT_FIELDS={'forecast','current','origin_temperatures','action_snapshot','native_source_paths'}
CAPTURE_FIELDS={'schema','issued_at','inputs_available_at','published_at','candidate','inputs','native_origin_binding','output','monitoring_report','capture_sha256'}


def digest(value,field):return sha256(_canonical({k:v for k,v in value.items() if k!=field})).hexdigest()


def _numeric(candidate,inputs,*,issue,available,published):
    candidate=validate_candidate(candidate,assessed_at=issue)
    if not available<=issue<=published<issue+timedelta(seconds=90) or issue.second or issue.microsecond or issue.minute%5:
        raise ValueError('aligned causal provisional issue required')
    if set(inputs)!=INPUT_FIELDS:raise ValueError('complete original provisional sources required')
    if _utc(inputs['origin_temperatures']['assessed_at'])>available:raise ValueError('temperature inputs unavailable at issue')
    phases,initial=_temperatures(inputs['origin_temperatures'],inputs['current'],issued_at=issue,published_at=published,version=2)
    if phases!=candidate['fit']['sensor_epochs']:raise ValueError('provisional native phase differs')
    actions=_origin_actions(inputs['action_snapshot'],issue)
    forcings=_forecast_forcing(inputs['forecast'],issue,available,actions)
    model=InstalledShadeDynamics(tuple(candidate['fit']['coefficients']))
    rolled=model.rollout(origin_at=issue,air_f=initial['air'],mass_f=initial['mass'],forcings=forcings)
    trajectory=[dict(at=row.at.isoformat(),air_f=state[0],mass_f=state[1]) for i,(row,state) in enumerate(zip(forcings,rolled.states),1) if i%12==0]
    return dict(schema=NUMERIC_SCHEMA,status='provisional',generated_at=issue.isoformat(),artifact_sha256=candidate['artifact_sha256'],
        runtime_sha256=candidate['runtime_sha256'],horizon_hours=inputs['forecast']['horizon_hours'],initial=dict(air_f=initial['air'],mass_f=initial['mass'],outdoor_f=initial['outdoor']),
        origin_actions=actions,trajectory=trajectory,confidence='low',prediction_intervals=None,advice=[],graduated=False,automatic_actuation=False)


def build_capture(candidate,inputs,*,issue,available,published,check_budget=lambda:None,monitoring_report=None):
    issue,available,published=map(_utc,(issue,available,published));inputs=json.loads(_canonical(inputs))
    if not isinstance(inputs,dict) or set(inputs)!=INPUT_FIELDS:raise ValueError('complete original provisional sources required')
    check_budget()
    binding=build_binding(inputs['origin_temperatures'],source_paths=inputs['native_source_paths'],issue_at=issue,check_budget=check_budget)
    output=_numeric(candidate,inputs,issue=issue,available=available,published=published)
    _validate_report(monitoring_report,candidate['artifact_sha256'],available)
    check_budget()
    value=json.loads(_canonical(dict(schema=CAPTURE_SCHEMA,issued_at=issue.isoformat(),inputs_available_at=available.isoformat(),published_at=published.isoformat(),
        candidate=candidate,inputs=inputs,native_origin_binding=binding,output=output,monitoring_report=monitoring_report)))
    value['capture_sha256']=digest(value,'capture_sha256')
    return value


def validate_capture(value,*,check_budget=lambda:None):
    if not isinstance(value,dict) or set(value)!=CAPTURE_FIELDS or value['schema']!=CAPTURE_SCHEMA:raise ValueError('closed provisional origin required')
    if digest(value,'capture_sha256')!=value['capture_sha256']:raise ValueError('original provisional capture differs')
    check_budget()
    replay_binding(value['native_origin_binding'],value['inputs']['origin_temperatures'],issue_at=value['issued_at'],check_budget=check_budget)
    output=_numeric(value['candidate'],value['inputs'],issue=_utc(value['issued_at']),available=_utc(value['inputs_available_at']),published=_utc(value['published_at']))
    if _canonical(output)!=_canonical(value['output']):raise ValueError('original provisional trajectory differs')
    _validate_report(value['monitoring_report'],value['candidate']['artifact_sha256'],_utc(value['inputs_available_at']))
    check_budget();return deepcopy(value)


def _validate_report(report,artifact,available):
    if report is None:return
    if (not isinstance(report,dict) or set(report)!={'schema','artifact_sha256','graduated','by_horizon','assessed_at'} or
            report['schema']!='earthship-provisional-thermal-performance/v1' or report['artifact_sha256']!=artifact or
            report['graduated'] is not False or not timedelta(0)<=available-_utc(report['assessed_at'])<=timedelta(minutes=15) or
            not isinstance(report['by_horizon'],dict) or set(report['by_horizon'])!={'1','6','12','24'}):raise ValueError('original current revision monitoring report required')
    for group in report['by_horizon'].values():
        if not isinstance(group,dict) or set(group)!={'model','persistence','recent_cycle'}:raise ValueError('closed monitoring baselines required')
        for stats in group.values():
            if not isinstance(stats,dict) or set(stats)!={'count','mae_f','bias_f'} or type(stats['count']) is not int or not 0<=stats['count']<=256:raise ValueError('bounded monitoring count required')
            if stats['count']==0:
                if stats['mae_f'] is not None or stats['bias_f'] is not None:raise ValueError('empty cohort cannot claim measured errors')
            else:
                if any(type(stats[k]) not in (int,float) or not math.isfinite(stats[k]) for k in ('mae_f','bias_f')) or not 0<=stats['mae_f']<=360 or not -360<=stats['bias_f']<=360:
                    raise ValueError('finite measured errors required')


def publication(capture):
    issue=_utc(capture['issued_at']);candidate=capture['candidate'];fit=candidate['fit']
    value=dict(schema=PUBLICATION_SCHEMA,version=8,status='provisional',generatedAt=issue.isoformat(),validUntil=(issue+timedelta(minutes=15)).isoformat(),
        model=dict(artifactSha256=candidate['artifact_sha256'],runtimeSha256=candidate['runtime_sha256'],createdAt=candidate['created_at'],trainedThrough=fit['training_end'],
            fitExecuted=True,independentOriginDates=fit['independent_origin_dates'],horizonSupport=fit['horizon_support'],regularizationStrength=fit['regularization_strength']),
        forecast=deepcopy(capture['output']),confidence=dict(grade='low',actionLabels='withheld'),
        graduation=dict(forecastQualified=False,stabilityAssessed=False,calibrationAssessed=False),automaticActuation=False,
        reasons=['Provisional model; stability and calibrated uncertainty are not established.','Production errors are monitored against persistence and recent-cycle baselines.'])
    report=capture['monitoring_report']
    if report is None:
        value['reasons'].append('Monitoring measurements are pending or unavailable.')
    else:
        value['reasons'].append('Monitoring verified at '+report['assessed_at']+'.')
        for horizon in ('1','6','12','24'):
            stats=report['by_horizon'][horizon]
            bits=[]
            for key,label in (('model','model'),('persistence','persistence'),('recent_cycle','recent cycle')):
                row=stats[key]
                bits.append(f"{label}: {row['mae_f']:.2f} F MAE (n={row['count']})" if row['count'] else f'{label}: awaiting observations')
            bias=stats['model']['bias_f']
            value['reasons'].append(horizon+'h '+ '; '.join(bits)+(f'; model bias {bias:+.2f} F.' if bias is not None else '.'))
    if len(_canonical(value))>=16384:raise ValueError('bounded provisional publication required')
    return value


def unavailable(at,reason='Provisional forecast unavailable; inputs or runtime failed validation.'):
    at=_utc(at)
    return dict(schema=PUBLICATION_SCHEMA,version=8,status='unavailable',generatedAt=at.isoformat(),validUntil=(at+timedelta(minutes=15)).isoformat(),
        model=None,forecast=None,confidence=dict(grade='unavailable',actionLabels='withheld'),graduation=dict(forecastQualified=False,stabilityAssessed=False,calibrationAssessed=False),
        automaticActuation=False,reasons=[reason])


def persist(directory,value,*,field,suffix,maximum=2*1024*1024):
    root=_private_directory(Path(directory));raw=_canonical(value)
    if len(raw)>maximum:raise ValueError('bounded provisional original required')
    path=root/(value[field]+suffix)
    if path.exists():
        if _owned_bytes(path,maximum)!=raw:raise ValueError('immutable provisional original differs')
    else:_write_private(path,raw);_sync_directory(root)
    return path


def read_capture(path,*,check_budget=lambda:None):
    from .origin_capture import _object
    value=json.loads(_owned_bytes(Path(path),2*1024*1024),object_pairs_hook=_object)
    return validate_capture(value,check_budget=check_budget)
