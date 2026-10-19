"""Native issue-time forecasts retain causal originals and genuine model lineage."""
from copy import deepcopy
from datetime import timedelta,datetime
import importlib
import pytest
from test_native_thermal_artifact import originals
from test_native_thermal_inputs import RUNTIME
from test_installed_shade_inputs import END
from test_installed_shade_origin import native,weather,actions
from astro_geometry import build_source,build_cache
from astro_geometry_series import build_series_request,split_series_request,build_series

ISSUE=END+timedelta(days=1,seconds=15)
def api():return importlib.import_module('native_thermal_forecast')

def future(issue,*,hours=24,missing=False,late=False,degrees=30,runtime=RUNTIME,latitude=38.3739919):
    points=[issue+timedelta(minutes=5*i) for i in range(1,hours*12+1)]
    if missing:points.pop()
    request=build_series_request(points,requested_at=issue-timedelta(seconds=6),latitude=latitude,longitude=-105.7744609,timezone_name='America/Denver')
    caches=[]
    for chunk in split_series_request(request):
        source=build_source(chunk,observed_at=issue-timedelta(seconds=5),native_runtime=runtime,source_status='ONLINE',latitude=latitude,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)
        output=''.join(at+'\t'+str(degrees)+'\t180\n' for at in chunk['instants']).encode()
        caches.append(build_cache(chunk,source,native_output=output,computed_at=issue+timedelta(seconds=1) if late else issue-timedelta(seconds=4)))
    return build_series(request,caches,expected_native_runtime=runtime)

def context(tmp_path,monkeypatch,originals,*,issue=ISSUE):
    from test_native_thermal_artifact import fixture
    import native_thermal_artifact as artifacts
    paths,runtime,created=fixture(tmp_path,originals)
    runtime['native_source_manifest']['openhab/scripts/native_thermal_forecast.py']='d'*64
    runtime['native_code_revision']=artifacts.digest(runtime['native_source_manifest'])
    candidate=artifacts.build_native_candidate(originals=paths,runtime=runtime,created_at=created)
    current,proof=native(issue)
    inputs=dict(forecast=weather(issue),current=current,origin_temperatures=proof,action_snapshot=actions(issue),native_source_paths={'mathematical':'source'})
    # Numerical/causal tests use original temperature validators. Query acquisition
    # is separately exercised by retained compressed-source integration tests.
    monkeypatch.setattr(api(),'build_binding',lambda *a,**k:{'mathematical':'binding'})
    monkeypatch.setattr(api(),'replay_binding',lambda *a,**k:None)
    g=future(issue)
    return candidate,inputs,dict(geometry=g,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],expected_geometry_sha256=g.sha256,issue=issue,available=issue,published=issue+timedelta(seconds=2))

def issued(tmp_path,monkeypatch,originals):
    c,i,k=context(tmp_path,monkeypatch,originals);return api().build_capture(c,i,**k),k

def replay(value,k):return api().validate_capture(value,runtime=k['runtime'],expected_artifact_sha256=k['expected_artifact_sha256'],expected_capture_sha256=value['capture_sha256'])

def test_native_forecast_first_endpoint_matches_independent_physical_recurrence(tmp_path,monkeypatch,originals):
    c,inputs,k=context(tmp_path,monkeypatch,originals);capture=api().build_capture(c,inputs,**k)
    coeff=c['fit']['coefficients'];air=float(inputs['current']['air']['value']);mass=float(inputs['current']['mass']['value'])
    from thermal_model.dynamics import SOLAR_TERM_SCALE
    solar=SOLAR_TERM_SCALE*min(1.3,100/(1050*0.5**1.15))
    left,right=inputs['forecast']['rows'][:2]
    for step in range(1,13):
        at=ISSUE+timedelta(minutes=5*step)
        left_at,right_at=(datetime.fromisoformat(row['at']) for row in (left,right))
        ratio=(at-left_at)/(right_at-left_at)
        outside=left['tempF']+ratio*(right['tempF']-left['tempF'])
        air,mass=(air+coeff[0]*(outside-air)+coeff[1]*(mass-air)+coeff[3]*solar+coeff[5],mass+coeff[6]*(air-mass)+coeff[7]*(outside-mass)+coeff[9]*solar)
    first=capture['output']['trajectory'][0]
    assert first['air_f']==pytest.approx(air,abs=1e-12) and first['mass_f']==pytest.approx(mass,abs=1e-12)
    assert len(capture['output']['trajectory'])==24 and first['at']==(ISSUE+timedelta(hours=1)).isoformat()
    assert replay(capture,k)==capture
    payload=api().publication(capture)
    assert payload['forecast']['geometry_series_sha256']==k['geometry'].sha256
    assert payload['confidence']['grade']=='low' and payload['automaticActuation'] is False
    assert payload['graduation']['forecastQualified'] is False and payload['forecast']['prediction_intervals'] is None

@pytest.mark.parametrize('damage',['missing','late','library','site','pin'])
def test_invalid_future_geometry_never_produces_a_forecast(tmp_path,monkeypatch,originals,damage):
    c,i,k=context(tmp_path,monkeypatch,originals)
    if damage=='missing':k['geometry']=future(ISSUE,missing=True)
    if damage=='late':k['geometry']=future(ISSUE,late=True)
    if damage=='library':
        r=deepcopy(RUNTIME);r['libraries']['astro_binding']='f'*64;k['geometry']=future(ISSUE,runtime=r)
    if damage=='site':k['geometry']=future(ISSUE,latitude=38.4)
    if damage=='pin':k['expected_geometry_sha256']='f'*64
    else:k['expected_geometry_sha256']=k['geometry'].sha256
    with pytest.raises(ValueError):api().build_capture(c,i,**k)

@pytest.mark.parametrize('damage',['stale','phase','weather','future_action','removed','late_inputs','publication'])
def test_native_forecast_preserves_original_causal_and_physical_refusals(tmp_path,monkeypatch,originals,damage):
    c,i,k=context(tmp_path,monkeypatch,originals)
    if damage=='stale':
        for role in i['origin_temperatures']['roles'].values():role['grid'][-1][1]['validUntil']=ISSUE.isoformat()
    if damage=='phase':i['origin_temperatures']['roles']['air']['identity']['sensor_epoch']='00000000-0000-0000-0000-000000000001'
    if damage=='weather':i['forecast']['captured_at']=(ISSUE+timedelta(seconds=1)).isoformat()
    if damage=='future_action':i['action_snapshot']['actions']['vent']['created_at']=(ISSUE+timedelta(seconds=1)).isoformat()
    if damage=='removed':i['action_snapshot']['actions']['outdoor_shade']['state']='removed'
    if damage=='late_inputs':k['available']=ISSUE+timedelta(seconds=1)
    if damage=='publication':k['published']=ISSUE+timedelta(seconds=90)
    with pytest.raises(ValueError):api().build_capture(c,i,**k)

def test_resealed_capture_output_must_rederive_from_native_originals(tmp_path,monkeypatch,originals):
    value,k=issued(tmp_path,monkeypatch,originals);value['output']['trajectory'][0]['air_f']+=1
    value['capture_sha256']=api().digest(value,'capture_sha256')
    with pytest.raises(ValueError):replay(value,k)

def test_external_capture_and_model_identity_are_required(tmp_path,monkeypatch,originals):
    value,k=issued(tmp_path,monkeypatch,originals)
    for name in ('expected_capture_sha256','expected_artifact_sha256'):
        args=dict(runtime=k['runtime'],expected_artifact_sha256=k['expected_artifact_sha256'],expected_capture_sha256=value['capture_sha256']);args[name]='f'*64
        with pytest.raises(ValueError):api().validate_capture(value,**args)

def test_native_capture_private_roundtrip_keeps_original_geometry(tmp_path,monkeypatch,originals):
    value,k=issued(tmp_path,monkeypatch,originals)
    path=api().persist(tmp_path,value)
    assert path.stat().st_mode&0o777==0o600
    assert api().read_capture(path,runtime=k['runtime'],expected_artifact_sha256=k['expected_artifact_sha256'],expected_capture_sha256=value['capture_sha256'])==value

def test_november_default_and_new_operator_override_remain_distinct(tmp_path,monkeypatch,originals):
    issue=ISSUE.replace(month=11,day=1);c,i,k=context(tmp_path,monkeypatch,originals,issue=issue)
    i['action_snapshot']['actions'].pop('vent');i['action_snapshot']['missing_actions']=['vent']
    first=api().build_capture(c,i,**k)
    assert first['output']['origin_actions']['vent_open']==0 and first['output']['origin_actions']['vent_provenance']=='operator_default_no_vent'
    event=actions(issue)['actions']['vent'];event['state']='open'
    for key in ('effective_at','received_at','created_at'):event[key]=issue.isoformat()
    i['action_snapshot']['actions']['vent']=event;i['action_snapshot']['missing_actions']=[]
    second=api().build_capture(c,i,**k)
    assert second['output']['origin_actions']['vent_open']==1


def test_native_capture_replays_real_compressed_temperature_queries(tmp_path,monkeypatch,originals):
    import test_thermal_sensor_epoch_origins as old
    from thermal_model.temperature_history import STREAMS
    from weather_temperature_sources import build_temperature_source,write_compressed_temperature_source,replay_temperature_source
    from thermal_model.installed_shade_raw_score_sources import build_compressed_native_origin_binding,replay_compressed_native_origin_binding
    from test_installed_shade_inputs import EPOCHS
    from thermal_temperature_runtime import shadow_temperatures_v2
    c,i,k=context(tmp_path,monkeypatch,originals);paths={};saved=[]
    def retained(rows,*,targets,assessed_at,history_start,stream,policy,sensor_epoch):
        packet=build_temperature_source(rows=rows,targets=targets,assessed_at=assessed_at,stream=stream,policy=policy,sensor_epoch=sensor_epoch)
        assert packet['history_start']==history_start.isoformat()
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        paths[role]=str(write_compressed_temperature_source(tmp_path,packet))
        return replay_temperature_source(packet)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old,'NOW',ISSUE);patch.setattr(old,'select_temperature_grid_v2',retained)
        selected=shadow_temperatures_v2(ISSUE,old.native_grid(),sensor_epochs=EPOCHS,origin_observer=saved.append)
    i['current']={role:row['current'] for role,row in selected.items()};i['origin_temperatures']=saved[0];i['native_source_paths']=paths
    monkeypatch.setattr(api(),'build_binding',build_compressed_native_origin_binding)
    monkeypatch.setattr(api(),'replay_binding',replay_compressed_native_origin_binding)
    value=api().build_capture(c,i,**k)
    assert replay(value,k)==value
    from pathlib import Path
    Path(paths['air']).unlink()
    with pytest.raises((ValueError,OSError)):replay(value,k)


def test_native_monitoring_report_cannot_mix_candidate_revisions(tmp_path,monkeypatch,originals):
    from thermal_model.provisional_score import summarize
    c,i,k=context(tmp_path,monkeypatch,originals)
    report=summarize([],artifact_sha256=c['artifact_sha256']);report['assessed_at']=ISSUE.isoformat()
    value=api().build_capture(c,i,monitoring_report=report,**k)
    assert any('awaiting observations' in reason for reason in api().publication(value)['reasons'])
    report['artifact_sha256']='f'*64
    with pytest.raises(ValueError):api().build_capture(c,i,monitoring_report=report,**k)


@pytest.mark.parametrize('field',['issue','available','published'])
@pytest.mark.parametrize('suffix',['.0000009+00:00','+00:00:00.5'])
def test_build_rejects_clock_precision_that_would_change_the_requested_instant(tmp_path,monkeypatch,originals,field,suffix):
    c,i,k=context(tmp_path,monkeypatch,originals)
    k[field]=k[field].isoformat().split('+')[0]+suffix
    with pytest.raises(ValueError):api().build_capture(c,i,**k)


@pytest.mark.parametrize('field',['issued_at','inputs_available_at','published_at'])
@pytest.mark.parametrize('suffix',['.0000009+00:00','+00:00:00.5'])
def test_resealed_capture_rejects_lossy_clock_precision(tmp_path,monkeypatch,originals,field,suffix):
    value,k=issued(tmp_path,monkeypatch,originals)
    value[field]=value[field].split('+')[0]+suffix
    value['capture_sha256']=api().digest(value,'capture_sha256')
    with pytest.raises(ValueError):replay(value,k)


def test_replay_returns_only_the_pinned_snapshot_when_final_guard_mutates_caller(tmp_path,monkeypatch,originals):
    value,k=issued(tmp_path,monkeypatch,originals);original=deepcopy(value);pin=value['capture_sha256'];count=0
    def count_check():
        nonlocal count
        count+=1
    args=dict(runtime=k['runtime'],expected_artifact_sha256=k['expected_artifact_sha256'],expected_capture_sha256=pin)
    api().validate_capture(value,check_budget=count_check,**args)
    final_check=count;count=0
    def mutate_at_final_check():
        nonlocal count
        count+=1
        if count==final_check:value['output']['automatic_actuation']=True
    try:result=api().validate_capture(value,check_budget=mutate_at_final_check,**args)
    except ValueError:return
    assert count==final_check and value['output']['automatic_actuation'] is True
    assert result==original and api().digest(result,'capture_sha256')==pin
