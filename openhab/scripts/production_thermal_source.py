"""Read-only confirmed weather originals into the physical temperature adapter."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.production_weather_conditioning import validate_context
from weather_learning.contracts import digest,finite
from weather_source_files import _read

SELECTION_FIELDS={'schema','state_directory','source_sensor_epoch','available_at','runtime_sha256','automatic_actuation','selection_sha256'}
RECEIPT_FIELDS={'schema','issue_sha256','production_emission_sha256','report_sha256','cache_bytes_sha256','generated_at','published_at','valid_until','issued','automatic_actuation','receipt_sha256'}

class Unavailable(ValueError):pass


def _reference(path,maximum):
    path=Path(path);raw=_read(path,maximum)
    return dict(path=str(path),maximum=maximum,source=False,sha256=sha256(raw).hexdigest())


def _receipt(value):
    if (not isinstance(value,dict) or set(value)!=RECEIPT_FIELDS or value['schema']!='earthship-confirmed-production-view-receipt/v1' or
        value['receipt_sha256']!=identity({k:v for k,v in value.items() if k!='receipt_sha256'}) or value['issued'] is not True or value['automatic_actuation'] is not False):
        raise ValueError('original confirmed production view receipt required')
    for name in ('issue_sha256','production_emission_sha256','report_sha256','cache_bytes_sha256'):digest(value[name])
    return value


def _points(selected,receipt,*,forecast,issue,available,epoch,site,timezone,guard):
    from weather_learning.production_emissions import read_emission,read_issue
    from weather_learning.production_scoring import _procedure
    if selected['source_sensor_epoch']!=epoch:raise Unavailable('production_temperature_sensor_phase_mismatch')
    if not instant(receipt['published_at'])<=available<=issue<instant(receipt['valid_until']):raise Unavailable('production_temperature_expired')
    state=SimpleNamespace(root=Path(selected['state_directory']));guard()
    emission=read_emission(state,receipt['production_emission_sha256']);body=read_issue(state,receipt['issue_sha256']).to_dict()
    if emission['issue_sha256']!=receipt['issue_sha256'] or emission['published_at']!=receipt['published_at'] or body['decision_at']!=receipt['generated_at']:
        raise ValueError('original production thermal emission differs')
    if body.get('origin_contexts',{}).get('temperature',{}).get('sensor_epoch')!=epoch:raise Unavailable('production_temperature_sensor_phase_mismatch')
    detail=loads(emission['attempt_original']['states']['Forecast_10Day_JSON'])
    if detail['version']!=3 or detail['timezone']!=timezone or detail['productionModel']['issueSha256']!=receipt['issue_sha256']:
        raise Unavailable('production_temperature_site_mismatch')
    actual={instant(h['at']):(d,h) for d in detail['days'] for h in d['hours']}
    originals={(r['profile'],instant(r['at'])):r for r in body['rows'] if r['kind']=='temperature'}
    published={r['row_sha256'] for r in emission['published_rows'] if r['kind']=='temperature'};points=[]
    for raw in forecast['rows']:
        at=instant(raw['at'])
        if at<=issue:continue
        if at not in actual:raise Unavailable('production_temperature_curve_incomplete')
        _,shown=actual[at];profile=shown.get('forecastProfile','extended');row=originals.get((profile,at))
        if row is None or identity(row) not in published:raise Unavailable('production_temperature_curve_incomplete')
        original=body['source_originals'][row['source_sha256']]
        if original['site']['timezone']!=timezone or any(original['site'][k]!=site[k] for k in ('latitude','longitude')):
            raise Unavailable('production_temperature_site_mismatch')
        prediction=row['prediction'];expected=row['raw_presentation_value'] if prediction is None else prediction['point_estimate']*9/5+32
        if not finite(shown['tempF']) or not -40<=shown['tempF']<=140 or shown['tempF']!=expected:
            raise Unavailable('production_temperature_point_unavailable')
        points.append(dict(at=raw['at'],temp_f=shown['tempF'],profile=profile,source_sha256=row['source_sha256'],
            mode='declared_native_point_fallback' if prediction is None else 'local_model_mean',
            model_sha256=None if prediction is None else prediction['model_sha256'],
            procedure_sha256=None if prediction is None else _procedure(body,None,prediction)['procedure_sha256']))
    guard();return points


def collect(*,selection,selected,forecast,geometry,issue,sensor_epoch,guard,clock):
    from thermal_weather_source import production_conditioning_runtime
    if (set(selected)!=SELECTION_FIELDS or selected['selection_sha256']!=identity({k:v for k,v in selected.items() if k!='selection_sha256'}) or
        selected['automatic_actuation'] is not False or selected['runtime_sha256']!=identity(production_conditioning_runtime())):
        raise ValueError('exact selected production thermal adapter required')
    root=Path(selected['state_directory'])
    if not root.is_absolute() or root.resolve()!=root:raise ValueError('resolved selected production weather root required')
    raw_selection=_read(selection,16384);descriptor=geometry.descriptor();runtime=production_conditioning_runtime()
    value=dict(schema='earthship-thermal-weather-context/v2',issue=issue.isoformat(),prepared_at=clock().isoformat(),selection=deepcopy(selected),
        forecast_sha256=identity(forecast),rows=deepcopy(forecast['rows']),points=[],production_receipt=None,production_issue_sha256=None,
        production_emission_sha256=None,production_published_at=None,production_valid_until=None,source_sensor_epoch=sensor_epoch,
        native_runtime=geometry.to_dict()['native_runtime'],site=descriptor['site'],timezone=descriptor['timezone'],mode='native_raw_fallback',
        reason='production_temperature_original_unavailable',solar_policy='unchanged_native_ending_hour_horizontal_mean',originals=[],runtime_manifest=runtime,
        physical_calibration_qualified=False,automatic_actuation=False)
    try:
        raw=_read(root/'production-forecast.json',512*1024);view=loads(raw);digest(view['report_sha256'])
        if view['report_sha256']!=identity({k:v for k,v in view.items() if k!='report_sha256'}):raise ValueError('original production view differs')
        ref=_reference(root/'production-views'/('view-'+view['report_sha256']+'.json'),4096)
        receipt=_receipt(loads(_read(ref['path'],4096)))
        if receipt['cache_bytes_sha256']!=sha256(raw).hexdigest() or receipt['report_sha256']!=view['report_sha256']:raise ValueError('original production cache bytes differ')
        refs=[ref,_reference(root/'production-emissions'/(receipt['production_emission_sha256']+'.json'),16*1024**2),
            _reference(root/'production-issues'/(receipt['issue_sha256']+'.json'),16*1024**2)]
        points=_points(selected,receipt,forecast=forecast,issue=issue,available=clock(),epoch=sensor_epoch,site=value['site'],timezone=value['timezone'],guard=guard)
        value.update(points=points,production_receipt=receipt,production_issue_sha256=receipt['issue_sha256'],production_emission_sha256=receipt['production_emission_sha256'],
            production_published_at=receipt['published_at'],production_valid_until=receipt['valid_until'],mode='confirmed_production_temperature',reason=None,originals=refs)
    except Unavailable as error:value['reason']=str(error)
    except (OSError,ValueError,KeyError,TypeError):pass
    value['prepared_at']=clock().isoformat();value['context_sha256']=identity(value)
    validate_context(value,issue=issue,available=instant(value['prepared_at']),forecast=forecast,sensor_epoch=sensor_epoch)
    if _read(selection,16384)!=raw_selection or production_conditioning_runtime()!=runtime:raise ValueError('selected thermal adapter changed during collection')
    verify(value,guard=guard);return value


def verify(value,*,guard):
    from thermal_weather_source import production_conditioning_runtime,hash_reference
    issue=instant(value['issue']);available=instant(value['prepared_at'])
    validate_context(value,issue=issue,available=available)
    if production_conditioning_runtime()!=value['runtime_manifest']:raise ValueError('original production thermal runtime differs')
    if value['mode']=='native_raw_fallback':guard();return
    selected=value['selection'];receipt=_receipt(value['production_receipt']);root=Path(selected['state_directory'])
    expected=[root/'production-views'/('view-'+receipt['report_sha256']+'.json'),root/'production-emissions'/(receipt['production_emission_sha256']+'.json'),root/'production-issues'/(receipt['issue_sha256']+'.json')]
    if [r['path'] for r in value['originals']]!=[str(p) for p in expected]:raise ValueError('original production thermal reference differs')
    for ref in value['originals']:hash_reference(ref,guard=guard)
    if loads(_read(expected[0],4096))!=receipt:raise ValueError('original production thermal receipt differs')
    forecast=dict(rows=value['rows'])
    points=_points(selected,receipt,forecast=forecast,issue=issue,available=available,epoch=value['source_sensor_epoch'],site=value['site'],timezone=value['timezone'],guard=guard)
    if points!=value['points'] or any(value[k]!=receipt[r] for k,r in (('production_issue_sha256','issue_sha256'),('production_emission_sha256','production_emission_sha256'),('production_published_at','published_at'),('production_valid_until','valid_until'))):
        raise ValueError('original emitted thermal temperature curve differs')
