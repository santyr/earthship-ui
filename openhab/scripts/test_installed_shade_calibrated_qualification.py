"""Calibrated source adapters and explicit v2 gates; no genuine release evidence."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import pytest

from test_installed_shade_calibrated import candidate,mathematical_original,runtime
from test_installed_shade_qualification import source_case,numerical_policy
from test_installed_shade_origin import prepared,original,outcome
from thermal_model import installed_shade_qualification as qualification
from thermal_model import policy_registration as registration
from thermal_model.installed_shade_artifact import _digest
from thermal_model.graduation_policy import RECORD_FIELDS,derive_policy


@pytest.fixture
def pair(tmp_path,mathematical_original):
    from thermal_model.installed_shade_calibrated_origin import write_calibrated_capture
    tmp_path.chmod(0o700);record=mathematical_original;path=write_calibrated_capture(tmp_path,record)
    at=datetime.fromisoformat(record['issued_at']);target=at+timedelta(hours=1)
    from test_installed_shade_calibration import synthetic_cycle_grid
    packet=dict(origin_path=str(path),publication=dict(time=int((at+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(record['output'])),
        horizon_hours=1,outcome=dict(target_at=target.isoformat(),receipt=outcome(target)),recent_cycle_grid=synthetic_cycle_grid(at,1))
    return packet,target+timedelta(minutes=10)


def test_calibrated_qualification_replays_v2_original_bands_and_refuses_legacy_adapter(pair,mathematical_original):
    packet,now=pair
    actual=qualification._score_packets([packet],assessed_at=now,version=2)
    assert actual['calibrated_intervals'] is True
    assert actual['rows'][0]['interval_width_f']==pytest.approx(64.)
    assert actual['bindings'][0]['original_capture_sha256']==mathematical_original['capture_sha256']
    with pytest.raises(ValueError):qualification._score_packets([packet],assessed_at=now)


def test_calibrated_registration_preserves_original_v1_development_baselines(source_case):
    packet,policy,now=source_case
    originals=registration._score_sources([packet],policy,now,version=4)
    assert originals[packet['origin_path']]['schema']=='earthship-installed-shade-origin/v1'
    policy['development'][0]['persistence_error_f']+=1
    with pytest.raises(ValueError):registration._score_sources([packet],policy,now,version=4)


def test_calibrated_registration_also_replays_explicit_v2_development_packets(pair,mathematical_original):
    from thermal_model.installed_shade_calibrated_origin import score_calibrated_capture
    packet,now=pair
    row=score_calibrated_capture(mathematical_original,**{k:v for k,v in packet.items() if k!='origin_path'},assessed_at=now)['scored_pair']
    policy=dict(candidate=dict(sensor_epochs=row['sensor_epochs']),development=[{k:row[k] for k in RECORD_FIELDS}])
    origins=registration._score_sources([packet],policy,now,version=4)
    assert origins[packet['origin_path']]['schema']=='earthship-installed-shade-origin/v2'
    with pytest.raises(ValueError):registration._score_sources([packet],policy,now,version=3)


def test_calibrated_seal_is_explicit_and_old_seal_readers_refuse_it(tmp_path,source_case,original,monkeypatch):
    # Only seal-copy classification is mocked; adapter replay tested above.
    packet,_,_=source_case;policy=numerical_policy();tmp_path.chmod(0o700)
    monkeypatch.setattr(registration,'_clock',lambda:datetime(2026,7,17,12,tzinfo=timezone.utc))
    def sources(values,*args,**kwargs):
        path=values[0]['origin_path']
        if kwargs.get('root') is not None:path=str(kwargs['root']/path)
        return {path:original}
    monkeypatch.setattr(registration,'_score_sources',sources)
    path=registration.register_calibrated_installed_shade_policy(tmp_path,policy,[packet])
    sealed=registration.read_calibrated_installed_shade_registered_policy(path)
    assert sealed['schema']=='earthship-installed-shade-policy-registration/v2'
    assert sealed['candidate_schema']=='earthship-installed-shade-candidate/v2'
    assert sealed['release_authorized'] is False
    with pytest.raises(ValueError):registration.read_installed_shade_registered_policy(path)


def test_missing_calibrated_sources_produce_closed_explicit_v2_report():
    report=qualification.qualify_calibrated_installed_shade_candidate(registration_path=None,candidate_path=None,
        runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,8,tzinfo=timezone.utc))
    assert report['schema']=='earthship-installed-shade-qualification-report/v2'
    assert report['candidate_schema']=='earthship-installed-shade-candidate/v2'
    assert report['recommended_stage']=='unavailable' and report['forecast_qualified'] is False
    qualification.validate_calibrated_installed_shade_qualification_report(report)
    with pytest.raises(ValueError):qualification.validate_installed_shade_qualification_report(report)


def policy_for(artifact):
    from test_thermal_graduation_policy import inputs
    values=inputs();begin=datetime.fromisoformat(artifact['calibration']['calibration_start'])
    old=datetime.fromisoformat(values['development'][0]['issue_at']);delta=begin-old
    for row in values['development']:
        for key in ('issue_at','target_at'):row[key]=(datetime.fromisoformat(row[key])+delta).isoformat()
    created=datetime.fromisoformat(artifact['created_at']);end=datetime.fromisoformat(artifact['trained_through'])
    values.update(candidate=dict(artifact_sha256=artifact['artifact_sha256'],runtime_sha256=artifact['runtime_revision'],
        trained_through=artifact['trained_through'],created_at=artifact['created_at'],active_parameter_count=10,sensor_epochs=artifact['sensor_epochs']),
        declared_at=created+timedelta(minutes=10),intervals=dict(development_start=begin.isoformat(),development_end=end.isoformat(),
        holdout_start=(created+timedelta(days=1)).isoformat(),holdout_end=(created+timedelta(days=90)).isoformat(),
        prospective_start=(created+timedelta(days=1)).isoformat(),prospective_end=None))
    return derive_policy(**values)


def test_v2_decision_uses_actual_issued_intervals_without_graduating_partial_evidence(pair,mathematical_original,candidate,monkeypatch):
    packet,now=pair;artifact=mathematical_original['candidate'];policy=policy_for(artifact)
    # Loader/seal orchestration seams, NOT actual registration or learned proof.
    monkeypatch.setattr(qualification,'read_calibrated_installed_shade_registered_policy',lambda _:dict(policy=policy,registration_sha256='1'*64))
    monkeypatch.setattr(qualification,'read_calibrated_candidate',lambda *args,**kwargs:dict(artifact=artifact,fit_evidence=candidate[0]['fit_evidence']))
    monkeypatch.setattr(qualification,'read_runtime_bundle',lambda _:dict(runtime=artifact['runtime']))
    report=qualification.qualify_calibrated_installed_shade_candidate(registration_path='seal',candidate_path='candidate',
        runtime_bundle_path='runtime',original_pairs=[packet],now=now)
    assert report['gates']['original_source_pairs'] is True and report['gates']['calibrated_intervals'] is True
    assert report['gates']['measured_fit'] is False and report['gates']['predictive_skill'] is False
    assert report['forecast_qualified'] is False and report['automatic_actuation_authorized'] is False
    assert report['support']['1']['independent_days']==1
    text=qualification.render_calibrated_installed_shade_qualification_report(report)
    audit=json.loads(text.split('```json\n',1)[1].split('```',1)[0])
    assert audit['thresholds']['24']['min_independent_days']==35
    assert audit['thresholds']['1']['max_mae_f']==2.
    assert audit['calibration']['method']['nominal_coverage']==.9
    assert audit['fit']['conditioning']['final_rank']==10
    assert audit['statistics']['recent_prospective']['1']['statistical_gates_passed'] is False


def test_actual_cli_selects_explicit_calibrated_contract_and_private_report(tmp_path):
    tmp_path.chmod(0o700);script=Path(__file__).resolve().parents[2]/'scripts'/'qualify-installed-shade.py'
    result=subprocess.run([sys.executable,str(script),'--contract-version','2','--output-dir',str(tmp_path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    files=list(tmp_path.glob('*.installed-shade-qualification-v2.json'));assert len(files)==1
    assert files[0].stat().st_mode&0o777==0o600
    report=json.loads(files[0].read_text());assert report['recommended_stage']=='unavailable'
    assert report['schema']=='earthship-installed-shade-qualification-report/v2'
