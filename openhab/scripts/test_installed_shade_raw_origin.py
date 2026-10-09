"""Versioned raw-calibrated issuance math is not household release evidence."""
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from test_installed_shade_calibrated import candidate,mathematical_candidate
from test_installed_shade_origin import ISSUE,native,weather,actions,outcome
from test_installed_shade_calibration import synthetic_cycle_grid
from thermal_model.installed_shade_artifact import _digest
from thermal_model.forcing_capture import _canonical


@pytest.fixture(scope='module')
def raw_math_capture(candidate):
    # Deliberate pure numerical fixture with no calibration source archive.
    # It cannot establish source-ready preparation or release qualification.
    from thermal_model import installed_shade_calibrated_origin as origin
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    artifact=mathematical_candidate(candidate)
    artifact['schema']='earthship-installed-shade-candidate/v3'
    artifact['calibration'].update(schema='earthship-installed-shade-calibration/v2',
        source_contract='earthship-installed-shade-score-sources/v2')
    for name in RAW_RUNTIME_PATHS-artifact['runtime']['source_manifest'].keys():artifact['runtime']['source_manifest'][name]='7'*64
    artifact['runtime_revision']=_digest(artifact['runtime'])
    artifact['artifact_sha256']=_digest({k:v for k,v in artifact.items() if k!='artifact_sha256'})
    issue=ISSUE+timedelta(days=40)
    prepared=origin.PreparedRawCalibratedCandidate(_canonical(artifact),issue)
    current,proof=native(issue)
    return origin.build_raw_calibrated_capture(prepared,issued_at=issue,inputs_available_at=issue,
        published_at=issue+timedelta(seconds=2),runtime=artifact['runtime'],forecast=weather(issue),
        current=current,origin_temperatures=proof,action_snapshot=actions(issue))


def test_raw_issue_has_distinct_schema_and_legacy_reader_refuses(raw_math_capture):
    from thermal_model import installed_shade_calibrated_origin as origin
    record=raw_math_capture
    assert record['schema']=='earthship-installed-shade-origin/v4'
    assert record['output']['schema']=='earthship-installed-shade-forecast/v3'
    assert record['output']['status']=='shadow' and record['output']['release_authorized'] is False
    assert record['output']['automatic_actuation'] is False
    assert len(record['output']['prediction_intervals'])==4
    assert record['output']['artifact_sha256']==record['candidate']['artifact_sha256']
    with pytest.raises(ValueError):origin.validate_calibrated_capture(record)


@pytest.mark.parametrize('hours',[1,6,12,24])
def test_raw_issue_scoring_preserves_as_issued_intervals_and_identity(raw_math_capture,hours):
    from datetime import datetime
    from thermal_model import installed_shade_calibrated_origin as origin
    record=raw_math_capture;issue=datetime.fromisoformat(record['issued_at']);target=issue+timedelta(hours=hours)
    publication=dict(time=int((issue+timedelta(seconds=2)).timestamp()*1000),state=_canonical(record['output']).decode())
    result=origin.score_raw_calibrated_capture(record,publication=publication,horizon_hours=hours,
        outcome=dict(target_at=target.isoformat(),receipt=outcome(target,73.)),
        recent_cycle_grid=synthetic_cycle_grid(issue,hours),assessed_at=target+timedelta(minutes=10))
    assert result['schema']=='earthship-installed-shade-source-scored-pair/v4'
    assert result['original_capture_sha256']==record['capture_sha256']
    assert result['publication_sha256']==_digest(publication)
    assert result['scored_pair']['artifact_sha256']==record['candidate']['artifact_sha256']
    assert result['scored_pair']['interval_width_f']==pytest.approx(64.)
    assert result['release_authorized'] is False


@pytest.mark.parametrize('damage',['band','raw_contract','runtime','candidate_schema'])
def test_rehashed_raw_issue_changes_refuse_original_replay(raw_math_capture,damage):
    from thermal_model import installed_shade_calibrated_origin as origin
    record=deepcopy(raw_math_capture)
    if damage=='band':record['output']['prediction_intervals'][0]['upper_air_f']+=1
    elif damage=='runtime':record['runtime']['source_manifest']['weather_temperature_sources.py']='a'*64
    else:
        if damage=='raw_contract':record['candidate']['calibration']['source_contract']='earthship-installed-shade-score-sources/v1'
        else:record['candidate']['schema']='earthship-installed-shade-candidate/v2'
        record['candidate']['artifact_sha256']=_digest({k:v for k,v in record['candidate'].items() if k!='artifact_sha256'})
    record['capture_sha256']=_digest({k:v for k,v in record.items() if k!='capture_sha256'})
    with pytest.raises(ValueError):origin.validate_raw_calibrated_capture(record)


def test_raw_issue_private_readback_is_typed_and_immutable(raw_math_capture,tmp_path):
    from thermal_model import installed_shade_calibrated_origin as origin
    tmp_path.chmod(0o700)
    path=origin.write_raw_calibrated_capture(tmp_path,raw_math_capture)
    assert path.name==raw_math_capture['capture_sha256']+'.installed-shade-origin-v4.json'
    assert path.stat().st_mode&0o777==0o600
    assert origin.read_raw_calibrated_capture(path)==raw_math_capture
    assert origin.write_raw_calibrated_capture(tmp_path,raw_math_capture)==path
    with pytest.raises(ValueError):origin.read_calibrated_capture(path)



from test_installed_shade_raw_calibration import retained_raw_case,collection,issued,release_case
from test_installed_shade_calibrated import runtime


def test_public_raw_preparation_replays_queries_and_partial_support_cannot_issue(retained_raw_case,candidate):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_artifact as artifact
    from thermal_model import installed_shade_calibrated_origin as origin
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    calibration,source_values,backend,_,_=retained_raw_case
    record=calibration.build_raw_calibration(**source_values)
    new=runtime(candidate)
    for name in RAW_RUNTIME_PATHS-new['source_manifest'].keys():new['source_manifest'][name]='7'*64
    values=dict(base_bundle=candidate[0],inputs=candidate[1],calibration=record,
        original_pairs=source_values['original_pairs'],base_runtime=candidate[2],runtime=new,
        created_at=source_values['created_at'])
    aggregate=artifact.build_raw_calibrated_candidate(**values)
    parameters={k:values[k] for k in ('base_bundle','inputs','calibration','original_pairs')}
    prepared=origin.prepare_raw_calibrated_candidate(aggregate,**parameters,
        expected_runtime_revision=_digest(new),assessed_at=values['created_at'])
    assert isinstance(prepared,origin.PreparedRawCalibratedCandidate)
    issue=values['created_at']+timedelta(days=1);current,proof=native(issue)
    with pytest.raises(ValueError,match='independent calibration support incomplete'):
        origin.build_raw_calibrated_capture(prepared,issued_at=issue,inputs_available_at=issue,
            published_at=issue+timedelta(seconds=2),runtime=new,forecast=weather(issue),
            current=current,origin_temperatures=proof,action_snapshot=actions(issue))
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):origin.prepare_raw_calibrated_candidate(aggregate,**parameters,
        expected_runtime_revision=_digest(new),assessed_at=values['created_at'])



@pytest.mark.parametrize('damage',['legacy_prepared_type','future_preparation'])
def test_raw_issue_refuses_wrong_preparation_type_or_future_proof(raw_math_capture,damage):
    from datetime import datetime
    from thermal_model import installed_shade_calibrated_origin as origin
    record=raw_math_capture;issue=datetime.fromisoformat(record['issued_at'])
    if damage=='legacy_prepared_type':prepared=origin.PreparedCalibratedCandidate(_canonical(record['candidate']),issue)
    else:prepared=origin.PreparedRawCalibratedCandidate(_canonical(record['candidate']),issue+timedelta(seconds=1))
    with pytest.raises(ValueError,match='source-verified calibrated candidate unavailable at issue'):
        origin.build_raw_calibrated_capture(prepared,issued_at=issue,inputs_available_at=issue,
            published_at=record['published_at'],runtime=record['runtime'],forecast=record['forecast'],
            current=record['current'],origin_temperatures=record['origin_temperatures'],action_snapshot=record['action_snapshot'])
