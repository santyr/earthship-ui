"""Explicit near24 local residual correction, with independent raw fallback.

This prepares a read-only candidate. It does not declare it issued, install a
model, replace extended corrections, change a display composite or publish Items.
The caller must supply the actual acquisition clock of the qualified origin.
"""
from bisect import bisect_left
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import json
from weather_source_files import _read

from .contracts import finite,identity,instant
from .evidence import utc
from .features import _jsonable,local_temperature_outcome,temperature_targets
from .historical_serving import HistoricalPredictor,load_selection
from .provider import TEMPERATURE,load_production_forecast
from .refresh_evaluation import RefreshRecord,_checked,_context,_freeze,_source,_provider

PROFILE='near_term_local_correction_24h_v1'


def _origin(snapshot,*,now,metadata,acquired_at,sensor_epoch):
    acquired=utc(acquired_at)
    if not now-timedelta(seconds=120)<=acquired<=now:
        raise ValueError('qualified origin acquisition unavailable at decision')
    outcome=local_temperature_outcome(metadata,target_at=now,assessed_at=now,sensor_epoch=sensor_epoch)
    # A storedAt field cannot stand in for the caller's original HTTP capture.
    if not utc(metadata['receivedAt'])<=utc(metadata['storedAt'])<=acquired:
        raise ValueError('origin acquisition precedes original persisted receipt')
    values=sorted((instant(p['valid_at']),p['value']) for p in snapshot['points']
        if p['variable']==TEMPERATURE and p['statistic']=='mean' and finite(p['value']))
    index=bisect_left([at for at,_ in values],now)
    if index<len(values) and values[index][0]==now:google=values[index][1]
    else:
        if index==0 or index==len(values):raise ValueError('same-source native origin interpolation unavailable')
        a,b=values[index-1],values[index]
        if b[0]-a[0]!=timedelta(hours=1):raise ValueError('same-source origin interpolation cannot bridge a native gap')
        fraction=(now-a[0]).total_seconds()/3600;google=a[1]*(1-fraction)+b[1]*fraction
    capture=dict(metadata=_jsonable(metadata),acquired_at=acquired.isoformat(),decision_at=now.isoformat())
    return dict(google_c=google,observed_c=outcome.value_c,bias_c=outcome.value_c-google,
        acquired_at=acquired.isoformat(),receipt_sha256=outcome.receipt_digest,
        capture_sha256=identity(capture),sensor_epoch=sensor_epoch),capture


def prepare_near_term_correction(archive,*,decision_at,site,selection_path,origin_metadata,origin_acquired_at,sensor_epoch):
    """Same-source origin bias and native hourly means on a separate 24h policy.

    The exact six-field near-term source qualification matches the publisher.
    A missing model/origin leaves that source's raw means available. Corrected
    hours include the ceil endpoint for the next 24h, labeled by exact timestamps.
    Model evidence is the existing immutable historical selection, not a fresh
    claim of near24 local skill or permission to use it for installed controls.
    """
    _context(archive,site);now=utc(decision_at)
    provider=load_production_forecast(archive,decision_at=now,required_horizon=timedelta(hours=24),site=site).to_dict()
    body=dict(schema='earthship-near-term-local-correction/v1',profile=PROFILE,decision_at=now.isoformat(),
        required_horizon_hours=24,source=None,status='UNAVAILABLE',reason=provider['reason'],
        origin=None,origin_capture=None,model=None,selected_originals=None,hours=[],issued=False,local_coverage_qualified=False,
        automatic_actuation=False,probability_claim=False)
    if provider['status']!='AVAILABLE':return _freeze(body)
    snapshot=archive.read(provider['source']['snapshot_sha256'])
    targets={target.target_at:target for target in temperature_targets(snapshot,issued_at=now)}
    body.update(source=_source(provider,snapshot,now),status='RAW_FALLBACK',reason='MODEL_UNAVAILABLE',
        hours=[dict(at=row['at'],raw_c=targets[instant(row['at'])].mean_c,local_c=None,
                    selected_c=targets[instant(row['at'])].mean_c) for row in provider['hours']])
    try:
        if selection_path is None:raise ValueError('explicit original model selection required')
        model,selection=load_selection(selection_path,kind='outdoor_temperature_c',now=now,sensor_epoch=sensor_epoch)
        if model['timezone']!=site.timezone:raise ValueError('selected near-term model timezone differs')
        selected_raw=_read(Path(selection_path),16384)
        experiment_raw=_read(Path(selection['experiment_path']),262144)
        model_raw=_read(Path(selection['model_path']),4*1024**2)
        if (json.loads(selected_raw)!=selection or json.loads(model_raw)!=model
                or sha256(experiment_raw).hexdigest()!=selection['experiment_file_sha256']
                or sha256(model_raw).hexdigest()!=selection['model_file_sha256']):
            raise ValueError('selected originals changed during preparation')
        originals=dict(selection_utf8=selected_raw.decode(),experiment_utf8=experiment_raw.decode(),model_utf8=model_raw.decode())
    except (OSError,ValueError,KeyError,TypeError):return _freeze(body)
    body['selected_originals']=originals
    # A failed origin still belongs to this selected artifact's fallback policy.
    body['model']=dict(model_sha256=model['model_sha256'],selection_sha256=selection['selection_sha256'],
        available_at=selection['available_at'],trained_at=model['trained_at'],
        training_end=model['training_end'],correction_limit_c=model['correction_limit'])
    try:
        if origin_metadata is None or origin_acquired_at is None:raise ValueError('actual acquired origin required')
        origin,capture=_origin(snapshot,now=now,metadata=origin_metadata,acquired_at=origin_acquired_at,sensor_epoch=sensor_epoch)
    except (ValueError,KeyError,TypeError,OverflowError):
        body['reason']='ORIGIN_UNAVAILABLE';return _freeze(body)
    predictor=HistoricalPredictor(model,now=now,timezone_name=site.timezone,origin_bias_c=origin['bias_c'],
        sensor_epoch=sensor_epoch,target_dates=selection['target_dates'],selection=selection)
    corrected=[]
    try:
        for raw in body['hours']:
            target=targets[instant(raw['at'])]
            if target.snapshot_digest!=snapshot['snapshot_sha256'] or target.issue_digest!=provider['issue_sha256']:
                raise ValueError('near-term predictor source differs from origin')
            value=predictor.predict(target,sensor_epoch=sensor_epoch)['value_c']
            if not finite(value) or abs(value-target.mean_c)>model['correction_limit']+1e-12:
                raise ValueError('finite bounded near-term correction required')
            corrected.append(dict(raw,local_c=value,selected_c=value))
    except (ValueError,KeyError,TypeError,OverflowError):
        body['reason']='MODEL_UNAVAILABLE';return _freeze(body)
    body.update(status='CORRECTED_READ_ONLY',reason=None,origin=origin,origin_capture=capture,hours=corrected,
        model=dict(model_sha256=model['model_sha256'],selection_sha256=selection['selection_sha256'],
            available_at=selection['available_at'],trained_at=model['trained_at'],
            training_end=model['training_end'],correction_limit_c=model['correction_limit']))
    return _freeze(body)



def replay_near_correction(record,*,archive,site):
    """Recheck a retained candidate without consulting today's selection pointer."""
    if not isinstance(record,RefreshRecord):raise ValueError('original prepared near24 record required')
    body=_checked(record.to_dict(),'record_sha256');_context(archive,site)
    if (body['schema']!='earthship-near-term-local-correction/v1' or body['profile']!=PROFILE
            or body['issued'] is not False or body['automatic_actuation'] is not False
            or body['local_coverage_qualified'] is not False):raise ValueError('original near24 preparation contract required')
    now=instant(body['decision_at'])
    if body['source'] is None:
        if body['hours'] or body['status']!='UNAVAILABLE':raise ValueError('unavailable original near24 must be empty')
        return record
    snapshot=archive.read(body['source']['snapshot_sha256'])
    provider=_provider(snapshot,decision=now,site=site,horizon=timedelta(hours=24))
    if _source(provider,snapshot,now)!=body['source']:raise ValueError('original near24 source metadata differs')
    targets={t.target_at:t for t in temperature_targets(snapshot,issued_at=now)}
    expected=[dict(at=r['at'],raw_c=targets[instant(r['at'])].mean_c,local_c=None,selected_c=targets[instant(r['at'])].mean_c) for r in provider['hours']]
    model=None;selection=None
    if body['model'] is not None:
        from .historical_serving import SELECTION_FIELDS
        from .site_calibration import _model
        originals=body.get('selected_originals')
        if not isinstance(originals,dict) or set(originals)!={'selection_utf8','experiment_utf8','model_utf8'}:
            raise ValueError('original selected near24 model bytes required')
        if any(not isinstance(v,str) or len(v.encode())>4*1024**2 for v in originals.values()):raise ValueError('bounded selected near24 originals required')
        selection=json.loads(originals['selection_utf8']);model=json.loads(originals['model_utf8']);experiment=json.loads(originals['experiment_utf8'])
        if (set(selection)!=SELECTION_FIELDS or selection['schema']!='earthship-historical-weather-selection/v1'
                or selection['kind']!='outdoor_temperature_c' or selection['automatic_actuation'] is not False
                or selection['selection_sha256']!=identity({k:v for k,v in selection.items() if k!='selection_sha256'})
                or sha256(originals['experiment_utf8'].encode()).hexdigest()!=selection['experiment_file_sha256']
                or sha256(originals['model_utf8'].encode()).hexdigest()!=selection['model_file_sha256']
                or experiment['receipt_sha256']!=identity({k:v for k,v in experiment.items() if k!='receipt_sha256'})
                or experiment['receipt_sha256']!=selection['experiment_receipt_sha256']
                or experiment['final_models']['outdoor_temperature_c']!=selection['model_sha256']
                or model['model_sha256']!=selection['model_sha256']):raise ValueError('original selected near24 evidence differs')
        _model(model);report=experiment['reports']['outdoor_temperature_c']
        names=['site_calibration.py','historical_pairs.py','contracts.py']
        if model['schema']=='earthship-site-calibration/v2':names.append('weights.py')
        if any(experiment['runtime_manifest'].get('openhab/scripts/weather_learning/'+name)!=sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in names):
            raise ValueError('original near24 numerical runtime differs')
        if (model['kind']!='outdoor_temperature_c' or model['timezone']!=site.timezone
                or model['feature_names']!=sorted(['google_c','lead_days','hour_sin','hour_cos','season_sin','season_cos','origin_bias_decay_c'])
                or model['correction_limit']>6 or report['pairs']<3 or report['target_days']<2
                or not report['candidate_mae']<report['baseline_mae']
                or not instant(model['trained_at'])<=instant(selection['available_at'])<=now<instant(model['trained_at'])+timedelta(days=14)):
            raise ValueError('original eligible near24 selection required')
        summary=dict(model_sha256=model['model_sha256'],selection_sha256=selection['selection_sha256'],available_at=selection['available_at'],
            trained_at=model['trained_at'],training_end=model['training_end'],correction_limit_c=model['correction_limit'])
        if summary!=body['model']:raise ValueError('original near24 model summary differs')
    if body['status']=='CORRECTED_READ_ONLY':
        if model is None or body['origin_capture'] is None:raise ValueError('original near24 origin and model required')
        capture=body['origin_capture'];metadata=dict(capture['metadata'])
        for key in ('receivedAt','storedAt','validUntil'):metadata[key]=instant(metadata[key])
        origin,replayed_capture=_origin(snapshot,now=now,metadata=metadata,acquired_at=instant(capture['acquired_at']),sensor_epoch=selection['sensor_epoch'])
        if origin!=body['origin'] or replayed_capture!=capture:raise ValueError('original near24 origin differs')
        predictor=HistoricalPredictor(model,now=now,timezone_name=site.timezone,origin_bias_c=origin['bias_c'],
            sensor_epoch=selection['sensor_epoch'],target_dates=selection['target_dates'],selection=selection)
        for row in expected:
            value=predictor.predict(targets[instant(row['at'])],sensor_epoch=selection['sensor_epoch'])['value_c']
            row.update(local_c=value,selected_c=value)
    elif body['status']!='RAW_FALLBACK' or body['origin'] is not None or body['origin_capture'] is not None:
        raise ValueError('explicit original near24 fallback required')
    if body['hours']!=expected:raise ValueError('retained near24 values differ from original prediction')
    return record
