"""Versioned calibrated candidate/issuance contracts, not household qualification."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import pytest

from test_installed_shade_origin import candidate, prepared, original, ISSUE, native, weather, actions, outcome
from test_installed_shade_qualification import source_case
from test_installed_shade_calibration import create, rows, synthetic_cycle_grid
from thermal_model.installed_shade_artifact import _digest


def artifact_module():
    from thermal_model import installed_shade_calibrated_artifact
    return installed_shade_calibrated_artifact


def origin_module():
    from thermal_model import installed_shade_calibrated_origin
    return installed_shade_calibrated_origin


def runtime(candidate):
    result=deepcopy(candidate[2]);result['code_revision']='9'*64
    result['source_manifest'].update({name:'8'*64 for name in (
        'thermal_model/installed_shade_calibration.py',
        'thermal_model/installed_shade_calibrated_artifact.py',
        'thermal_model/installed_shade_calibrated_origin.py')})
    return result


def build(candidate,source_case,**changes):
    options=dict(base_bundle=candidate[0],inputs=candidate[1],calibration=create(candidate,source_case),
        original_pairs=[source_case[0]],base_runtime=candidate[2],runtime=runtime(candidate),created_at=source_case[2])
    options.update(changes)
    return artifact_module().build_calibrated_candidate(**options)


def test_candidate_has_separate_identity_and_calibration_learning_cutoff(candidate,source_case):
    result=build(candidate,source_case)
    assert result['schema']=='earthship-installed-shade-candidate/v2'
    assert result['artifact_sha256']!=candidate[0]['artifact']['artifact_sha256']
    assert result['trained_through']==(ISSUE+timedelta(hours=1)).isoformat()
    assert result['trained_from']==candidate[0]['artifact']['trained_from']
    assert result['sensor_epochs']==candidate[0]['artifact']['sensor_epochs']
    assert result['runtime_revision']==_digest(runtime(candidate))
    assert result['base_runtime']==candidate[2]
    assert result['calibration']['bands']['1']['overall'] is None
    assert result['release_authorized'] is False and result['as_issued_evidence'] is False


@pytest.mark.parametrize('damage',['model','dependency','observer','interpreter','closure','creation','source'])
def test_new_runtime_cannot_reinterpret_base_calibration_or_omit_cutoff(candidate,source_case,damage):
    changes={};new=runtime(candidate)
    if damage=='model':new['source_manifest']['thermal_model/installed_shade_dynamics.py']='7'*64
    elif damage=='dependency':new['dependencies']['numpy']='9.0.0'
    elif damage=='observer':new['observer_revision']='7'*64;new['source_manifest']['thermal_model/origin_capture.py']='7'*64
    elif damage=='interpreter':new['interpreter_sha256']='7'*64
    elif damage=='closure':new['source_manifest'].pop('thermal_model/installed_shade_calibration.py')
    elif damage=='creation':changes['created_at']=ISSUE
    else:
        packet=deepcopy(source_case[0]);packet['outcome']['receipt']['temperatureF']+=1
        changes['original_pairs']=[packet]
    changes['runtime']=new
    with pytest.raises(ValueError):build(candidate,source_case,**changes)


def test_partial_calibration_cannot_issue_usable_bands(candidate,source_case):
    a=build(candidate,source_case);m=origin_module()
    at=source_case[2]+timedelta(days=1)
    p=m.prepare_calibrated_candidate(a,base_bundle=candidate[0],inputs=candidate[1],calibration=create(candidate,source_case),
        original_pairs=[source_case[0]],expected_runtime_revision=_digest(runtime(candidate)),assessed_at=source_case[2])
    current,proof=native(at)
    with pytest.raises(ValueError):m.build_calibrated_capture(p,issued_at=at,inputs_available_at=at,
        published_at=at+timedelta(seconds=2),runtime=runtime(candidate),forecast=weather(at),
        current=current,origin_temperatures=proof,action_snapshot=actions(at))


def mathematical_candidate(candidate):
    # A unit fixture for pure shape/issuance replay only. The dummy calibration
    # pointer has no raw source archive, so public preparation/storage refuse it.
    from thermal_model.installed_shade_calibration import _method,_summarize
    m=artifact_module();base=candidate[0]['artifact'];start=ISSUE;end=ISSUE+timedelta(days=35)
    summary=_summarize(rows(),regimes=['warm'])
    metadata=dict(calibration_sha256='6'*64,calibration_start=start.isoformat(),calibration_end=end.isoformat(),
        created_at=(end+timedelta(minutes=10)).isoformat(),method=_method(),regimes=['warm'],
        bands={h:dict(overall=v['overall']['radius_f'],regimes={'warm':v['regimes']['warm']['radius_f']}) for h,v in summary['bands'].items()})
    result=dict(schema='earthship-installed-shade-candidate/v2',domain='outdoor_shades_installed',status='development_candidate',
        base_candidate=deepcopy(base),base_runtime=deepcopy(candidate[2]),runtime=runtime(candidate),
        calibration=metadata,sensor_epochs=deepcopy(base['sensor_epochs']),trained_from=base['trained_from'],
        trained_through=end.isoformat(),created_at=(end+timedelta(minutes=10)).isoformat(),
        code_revision=runtime(candidate)['code_revision'],runtime_revision=_digest(runtime(candidate)),
        release_authorized=False,as_issued_evidence=False)
    result['artifact_sha256']=_digest(result)
    m._shape(result,expected_runtime_revision=_digest(runtime(candidate)),assessed_at=end+timedelta(days=1))
    return result


@pytest.fixture(scope='module')
def mathematical_original(candidate):
    a=mathematical_candidate(candidate);at=ISSUE+timedelta(days=40);m=origin_module()
    p=m.PreparedCalibratedCandidate(json.dumps(a).encode(),at);current,proof=native(at)
    return m.build_calibrated_capture(p,issued_at=at,inputs_available_at=at,published_at=at+timedelta(seconds=2),
        runtime=runtime(candidate),forecast=weather(at),current=current,origin_temperatures=proof,action_snapshot=actions(at))


def test_new_issue_binds_bands_to_actual_targets_without_relabeling_old_schema(mathematical_original):
    record=mathematical_original;m=origin_module();m.validate_calibrated_capture(record)
    assert record['schema']=='earthship-installed-shade-origin/v2'
    output=record['output'];assert output['schema']=='earthship-installed-shade-forecast/v2'
    assert output['status']=='shadow' and output['release_authorized'] is False
    assert len(output['prediction_intervals'])==4
    for hours,band in zip((1,6,12,24),output['prediction_intervals']):
        assert band['horizon_hours']==hours
        point=next(row for row in output['trajectory'] if row['at']==band['at'])
        assert band['lower_air_f']==point['air_f']-32.
        assert band['upper_air_f']==point['air_f']+32.
        assert band['nominal_coverage']==.90
    from thermal_model.installed_shade_origin import validate_issued_capture
    with pytest.raises(ValueError):validate_issued_capture(record)


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_score_measures_the_bands_actually_issued_and_preserves_actual_bindings(mathematical_original,hours):
    record=mathematical_original;m=origin_module();at=datetime.fromisoformat(record['issued_at'])
    target=at+timedelta(hours=hours);band=next(row for row in record['output']['prediction_intervals'] if row['horizon_hours']==hours)
    publication=dict(time=int((at+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(record['output']))
    result=m.score_calibrated_capture(record,publication=publication,horizon_hours=hours,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target,band['lower_air_f'])),
        recent_cycle_grid=synthetic_cycle_grid(at,hours),assessed_at=target+timedelta(minutes=10))
    assert result['schema']=='earthship-installed-shade-source-scored-pair/v2'
    assert result['original_capture_sha256']==record['capture_sha256'] and result['publication_sha256']==_digest(publication)
    row=result['scored_pair'];assert row['artifact_sha256']==record['candidate']['artifact_sha256']
    assert row['runtime_sha256']==_digest(record['runtime'])
    assert row['interval_width_f']==pytest.approx(64.) and row['interval_covered'] is True
    assert result['calibration_sha256']==record['candidate']['calibration']['calibration_sha256']


@pytest.mark.parametrize('damage',['band','artifact','publication','runtime'])
def test_rehashed_changes_cannot_rewrite_actual_calibrated_issue(mathematical_original,damage):
    record=deepcopy(mathematical_original);m=origin_module()
    if damage=='band':record['output']['prediction_intervals'][0]['lower_air_f']+=1
    elif damage=='artifact':record['output']['artifact_sha256']=record['candidate']['base_candidate']['artifact_sha256']
    elif damage=='runtime':record['runtime']['dependencies']['numpy']='9.0.0'
    else:
        at=datetime.fromisoformat(record['issued_at']);target=at+timedelta(hours=1)
        publication=dict(time=int((at+timedelta(seconds=2)).timestamp()*1000),state=json.dumps({**record['output'],'prediction_intervals':None}))
        with pytest.raises(ValueError):m.score_calibrated_capture(record,publication=publication,horizon_hours=1,
            outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=synthetic_cycle_grid(at,1),assessed_at=target+timedelta(minutes=10))
        return
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):m.validate_calibrated_capture(record)


def test_private_aggregate_retains_original_calibration_and_old_readers_refuse_it(tmp_path,candidate,source_case):
    m=artifact_module();a=build(candidate,source_case);root=tmp_path/'aggregate';root.mkdir(mode=0o700)
    path=m.write_calibrated_candidate(root,a,base_bundle=candidate[0],inputs=candidate[1],calibration=create(candidate,source_case),
        original_pairs=[source_case[0]],expected_runtime_revision=_digest(runtime(candidate)),assessed_at=source_case[2])
    assert path.stat().st_mode&0o777==0o600
    loaded=m.read_calibrated_candidate(path,expected_runtime_revision=_digest(runtime(candidate)),assessed_at=source_case[2])
    assert loaded['artifact']==a and loaded['calibration']['summary']['complete'] is False
    assert loaded['fit_evidence']['fit_gates_passed'] is False
    from thermal_model.installed_shade_artifact import read_candidate_bundle
    with pytest.raises(ValueError):read_candidate_bundle(path,expected_runtime_revision=_digest(runtime(candidate)),assessed_at=source_case[2])
    changed=deepcopy(a);changed['calibration']['bands']['1']['overall']=0.
    changed['artifact_sha256']=_digest({k:v for k,v in changed.items() if k!='artifact_sha256'})
    fake=root/(changed['artifact_sha256']+'.installed-shade-candidate-v2.json')
    fake.write_text(json.dumps(changed));fake.chmod(0o600)
    with pytest.raises(ValueError):m.read_calibrated_candidate(fake,expected_runtime_revision=_digest(runtime(candidate)),assessed_at=source_case[2])


def test_private_calibrated_capture_roundtrip_keeps_actual_issued_intervals(tmp_path,mathematical_original):
    m=origin_module();tmp_path.chmod(0o700);path=m.write_calibrated_capture(tmp_path,mathematical_original)
    assert path.stat().st_mode&0o777==0o600
    assert m.read_calibrated_capture(path)==mathematical_original
    assert m.write_calibrated_capture(tmp_path,mathematical_original)==path
    from thermal_model.installed_shade_origin import read_issued_capture
    with pytest.raises(ValueError):read_issued_capture(path)


def test_outcome_outside_the_original_band_is_not_covered(mathematical_original):
    record=mathematical_original;at=datetime.fromisoformat(record['issued_at']);target=at+timedelta(hours=1)
    band=record['output']['prediction_intervals'][0]
    result=origin_module().score_calibrated_capture(record,
        publication=dict(time=int((at+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(record['output'])),
        horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=outcome(target,band['lower_air_f']-.1)),
        recent_cycle_grid=synthetic_cycle_grid(at,1),assessed_at=target+timedelta(minutes=10))
    assert result['scored_pair']['interval_covered'] is False


@pytest.mark.parametrize('mode',[None,'winter'])
def test_origin_outside_declared_calibration_regime_never_issues_band(candidate,mode):
    a=mathematical_candidate(candidate);m=origin_module();at=ISSUE+timedelta(days=40)
    p=m.PreparedCalibratedCandidate(json.dumps(a).encode(),at);current,proof=native(at);knowledge=actions(at)
    if mode is None:knowledge['mode']=None
    else:knowledge['mode']['state']=mode
    with pytest.raises(ValueError):m.build_calibrated_capture(p,issued_at=at,inputs_available_at=at,published_at=at+timedelta(seconds=2),
        runtime=runtime(candidate),forecast=weather(at),current=current,origin_temperatures=proof,action_snapshot=knowledge)
