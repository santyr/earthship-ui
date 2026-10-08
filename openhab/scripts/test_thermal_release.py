"""Explicit output modes derived from a freshly recomputed qualification."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from test_thermal_graduation_decision import classifier_case
from test_thermal_schema import valid_shadow_payload
from thermal_model.schema import validate_shadow_output
from thermal_model.forcing_capture import _canonical

NOW=datetime(2026,10,12,12,tzinfo=timezone.utc)


def module():
    from thermal_model import release
    return release


def shift(value):
    if isinstance(value,dict):return {key:shift(entry) for key,entry in value.items()}
    if isinstance(value,list):return [shift(entry) for entry in value]
    if isinstance(value,str) and value.startswith('2026-'):
        try:return (datetime.fromisoformat(value)+timedelta(days=60)).isoformat()
        except ValueError:pass
    return value



def forecast_rows(mode='warm'):
    return [dict(at=NOW+timedelta(hours=hour), tempF=50, radiationWm2=0,
        windMph=0, weatherCode=0, mode=mode) for hour in range(3)]


def inputs(monkeypatch,*,skill=True):
    decision,args=classifier_case(monkeypatch,skill=skill)
    report=decision.qualify_candidate(**args)
    shadow=shift(valid_shadow_payload())
    shadow['model']=dict(createdAt=args['artifact'].created_at,trainedThrough=args['artifact'].trained_through,
                         codeRevision=args['artifact'].code_revision)
    report['assessed_at']=NOW.isoformat()
    report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
    def loader(at):assert at==NOW;return deepcopy(report)
    return dict(shadow=shadow,qualification_loader=loader,now=NOW,
        artifact_sha256=report['candidate']['artifact_sha256'],runtime_sha256=report['candidate']['runtime_sha256'],
        sensor_epochs=report['candidate']['sensor_epochs'],forecast_rows=forecast_rows())


def test_forecast_active_has_explicit_version_and_withholds_action_advice(monkeypatch):
    release=module();result=release.build_release_output(**inputs(monkeypatch))
    assert result['version']==2 and result['status']=='forecast_active'
    assert result['release']['schema']=='earthship-thermal-release/v1'
    assert result['release']['forecastQualified'] is True
    assert result['release']['advisoryQualified'] is False
    assert result['release']['automaticActuation'] is False
    assert result['confidence']['grade']=='high'
    assert result['schedule']['candidate'] is None
    assert all(point['actions']==[] for point in result['forecast']['trajectory'])
    assert release.validate_release_output(result)==result
    with pytest.raises(ValueError):validate_shadow_output(result)


def test_failed_predictive_skill_stays_explicit_shadow(monkeypatch):
    release=module();result=release.build_release_output(**inputs(monkeypatch,skill=False))
    assert result['version']==2 and result['status']=='shadow'
    assert result['release']['forecastQualified'] is False
    assert result['confidence']['grade']=='low'


@pytest.mark.parametrize('damage',['cached_report','artifact','runtime','epoch','old_report','future_report','stale_output','bad_sensor','physical','missing_forcing'])
def test_invalid_or_stale_transition_returns_honest_unavailable(monkeypatch,damage):
    release=module();data=inputs(monkeypatch)
    if damage=='cached_report':data['qualification_loader']=data['qualification_loader'](NOW)
    elif damage=='artifact':data['artifact_sha256']='a'*64
    elif damage=='runtime':data['runtime_sha256']='b'*64
    elif damage=='epoch':data['sensor_epochs']={'air':'changed'}
    elif damage in ('old_report','future_report'):
        report=data['qualification_loader'](NOW)
        report['assessed_at']=(NOW+timedelta(seconds=1) if damage=='future_report' else NOW-timedelta(hours=25)).isoformat()
        report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
        data['qualification_loader']=lambda _:report
    elif damage=='stale_output':data['shadow']['generatedAt']=(NOW-timedelta(hours=1)).isoformat()
    elif damage=='bad_sensor':data['shadow']['provenance']['currentAgeMinutes']['air']=21
    elif damage=='physical':data['shadow']['forecast']['trajectory'][0]['hallwayF']=999
    elif damage=='missing_forcing':data['shadow']['forecast']['availableHours']=0
    result=release.build_release_output(**data)
    assert result['status']=='unavailable'
    assert result['confidence']['grade']=='unavailable'
    assert result['forecast']['trajectory']==[]
    assert result['release']['forecastQualified'] is False


def test_forged_active_publication_cannot_pass_output_validation(monkeypatch):
    release=module();data=inputs(monkeypatch,skill=False);result=release.build_release_output(**data)
    result['status']='forecast_active';result['confidence']['grade']='high'
    with pytest.raises(ValueError):release.validate_release_output(result)


def test_qualification_completing_after_origin_preserves_original_forecast_clock(monkeypatch):
    release=module();data=inputs(monkeypatch);now=NOW+timedelta(milliseconds=250)
    report=data['qualification_loader'](NOW);report['assessed_at']=now.isoformat()
    report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
    data['qualification_loader']=lambda at:deepcopy(report);data['now']=now
    output=release.build_release_output(**data)
    assert output['status']=='forecast_active'
    assert output['generatedAt']==data['shadow']['generatedAt']
    assert output['release']['qualifiedAt']==now.isoformat()


def test_previous_qualification_report_cannot_skip_recent_monitoring(monkeypatch):
    release=module();data=inputs(monkeypatch)
    report=data['qualification_loader'](NOW);report['schema']='earthship-thermal-qualification-report/v2'
    report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
    data['qualification_loader']=lambda _:report
    assert release.build_release_output(**data)['status']=='unavailable'


@pytest.mark.parametrize('field',['created_at','trained_through','both'])
def test_fractional_artifact_clocks_match_real_published_metadata(monkeypatch,field):
    from dataclasses import asdict,replace
    from test_thermal_origin_capture import capture_inputs
    from thermal_model.pipeline import _artifact_context
    data=inputs(monkeypatch);report=data['qualification_loader'](NOW)
    artifact=capture_inputs()['artifact']
    changes={name:(datetime.fromisoformat(getattr(artifact,name))+timedelta(microseconds=123456)).isoformat()
        for name in ('created_at','trained_through') if field in (name,'both')}
    artifact=replace(artifact,**changes)
    candidate=report['candidate'];candidate.update(changes)
    candidate['artifact_sha256']=sha256(_canonical(asdict(artifact))).hexdigest()
    report['policy']['candidate']=deepcopy(candidate)
    report['policy']['policy_sha256']=sha256(_canonical({key:value for key,value in report['policy'].items() if key!='policy_sha256'})).hexdigest()
    report['policy_sha256']=report['policy']['policy_sha256']
    report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
    data['artifact_sha256']=candidate['artifact_sha256']
    data['qualification_loader']=lambda _:deepcopy(report)
    data['shadow']['model']=_artifact_context(artifact,NOW)[0]
    result=module().build_release_output(**data)
    assert result['status']=='forecast_active'
    assert result['release']['artifactSha256']==candidate['artifact_sha256']
    for published in ('createdAt','trainedThrough'):
        damaged=deepcopy(data['shadow'])
        damaged['model'][published]=(datetime.fromisoformat(damaged['model'][published])+timedelta(seconds=1)).isoformat()
        assert module().build_release_output(**{**data,'shadow':damaged})['status']=='unavailable'
        fractional=deepcopy(data['shadow'])
        fractional['model'][published]=(datetime.fromisoformat(fractional['model'][published])+timedelta(microseconds=123456)).isoformat()
        assert module().build_release_output(**{**data,'shadow':fractional})['status']=='unavailable'
    data['artifact_sha256']='a'*64
    assert module().build_release_output(**data)['status']=='unavailable'
