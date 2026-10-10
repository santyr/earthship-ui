"""Distinct source-replayable development candidates; no release authority."""
from datetime import timedelta
from dataclasses import replace
import json
import pytest
from thermal_model.installed_shade_dynamics import InstalledShadeDynamics
from thermal_model.installed_shade_inputs import build_development_inputs, select_development_endpoints
from thermal_model.installed_shade_fit import (DevelopmentFit, EndpointFit, HORIZONS,
    _objective, _prepare_batches, _conditioning, _assess_stability, _nonoverlap_count)
from test_installed_shade_inputs import snapshot, START, EPOCHS
from test_installed_shade_dynamics import COEFFICIENTS

RUNTIME='b'*64
CODE='c'*64
NOW=START+timedelta(hours=72)


def module():
    from thermal_model import installed_shade_artifact
    return installed_shade_artifact


@pytest.fixture(scope='module')
def inputs():
    return snapshot(steps=864,rich_actions=True)


def make_report(inputs):
    # Source/candidate verification is mathematical replay, not proof that this
    # synthetic candidate was optimized or demonstrated predictive usefulness.
    data=build_development_inputs(inputs,expected_snapshot_sha256=inputs['snapshot_sha256'],sensor_epochs=EPOCHS,assessed_at=NOW)
    end=START+timedelta(hours=60)
    groups=tuple((h,select_development_endpoints(data,horizon_hours=h,start=START,end=end)) for h in HORIZONS)
    points=tuple(point for _,group in groups for point in group)
    coeff=list(COEFFICIENTS)
    for index in (2,3,8,9):coeff[index]*=.01
    coeff=tuple(coeff);model=InstalledShadeDynamics(coeff)
    loss,_,sensitivity=_objective(coeff,_prepare_batches(points));rank,condition=_conditioning(sensitivity)
    fit=EndpointFit(model,loss,loss,rank,condition,1,initial_coefficients=coeff)
    stability=_assess_stability(points,coeff,refitter=lambda _:pytest.fail('short synthetic history refit'))
    return DevelopmentFit(fit,stability,inputs['snapshot_sha256'],tuple(sorted(EPOCHS.items())),START,end,tuple((h,len(group)) for h,group in groups),tuple((h,_nonoverlap_count(group)) for h,group in groups))


@pytest.fixture(scope='module')
def numerical_report(inputs):
    return make_report(inputs)


def bundle(inputs,report):
    return module().build_candidate_bundle(inputs,report,code_revision=CODE,runtime_revision=RUNTIME,created_at=NOW)


def test_roundtrip_replays_original_sources_and_has_distinct_closed_schema(inputs,numerical_report):
    m=module();result=bundle(inputs,numerical_report)
    restored=m.validate_candidate_bundle(result,inputs,expected_runtime_revision=RUNTIME,assessed_at=NOW)
    assert restored.coefficients==numerical_report.fit.model.coefficients
    assert result['artifact']['schema']=='earthship-installed-shade-candidate/v1'
    assert result['fit_evidence']['schema']=='earthship-installed-shade-fit-evidence/v1'
    assert result['artifact']['domain']=='outdoor_shades_installed'
    assert result['artifact']['release_authorized'] is False
    assert result['fit_evidence']['fit_gates_passed'] is False
    assert result['fit_evidence']['stability']['assessed'] is False


@pytest.mark.parametrize('damage',['runtime','source','active','extra','threshold','objective','coefficient','days','stability'])
def test_rehashed_tampering_cannot_bypass_source_replay(inputs,numerical_report,damage):
    m=module();result=bundle(inputs,numerical_report)
    a=result['artifact'];e=result['fit_evidence'];runtime=RUNTIME
    if damage=='runtime':runtime='d'*64
    elif damage=='source':a['source_snapshot_sha256']='e'*64
    elif damage=='active':a['release_authorized']=True
    elif damage=='extra':a['active']=True
    elif damage=='threshold':e['limits']['max_bound_span_fraction']=1
    elif damage=='objective':e['optimizer']['final_objective']+=1
    elif damage=='coefficient':a['dynamics']['coefficients'][0]*=1.01
    elif damage=='days':e['support']['unique_local_days']+=20
    else:e['stability']['assessed']=True;e['fit_gates_passed']=True
    # Keep all digest links consistent. Semantic/source checks must still fail.
    e['candidate_payload_sha256']=m._digest(m._payload(a))
    e['fit_evidence_sha256']=m._digest({k:v for k,v in e.items() if k!='fit_evidence_sha256'})
    a['fit_evidence_sha256']=e['fit_evidence_sha256']
    a['artifact_sha256']=m._digest({k:v for k,v in a.items() if k!='artifact_sha256'})
    with pytest.raises(ValueError):m.validate_candidate_bundle(result,inputs,expected_runtime_revision=runtime,assessed_at=NOW)


def test_changed_fit_claim_or_missing_seed_is_refused(inputs,numerical_report):
    bad=replace(numerical_report,fit=replace(numerical_report.fit,final_objective=numerical_report.fit.final_objective+1))
    with pytest.raises(ValueError):bundle(inputs,bad)
    bad=replace(numerical_report,fit=replace(numerical_report.fit,initial_coefficients=()))
    with pytest.raises(ValueError):bundle(inputs,bad)


def test_old_full_model_reader_refuses_distinct_candidate(inputs,numerical_report):
    from thermal_model.artifacts import _artifact_from_payload, ArtifactValidationError
    with pytest.raises(ArtifactValidationError):_artifact_from_payload(bundle(inputs,numerical_report)['artifact'])


def test_private_immutable_bundle_write_read_and_changed_file_refusal(tmp_path,inputs,numerical_report):
    m=module();tmp_path.chmod(0o700);result=bundle(inputs,numerical_report)
    path=m.write_candidate_bundle(tmp_path,result,inputs,expected_runtime_revision=RUNTIME,assessed_at=NOW)
    assert path.stat().st_mode&0o777==0o600
    assert m.write_candidate_bundle(tmp_path,result,inputs,expected_runtime_revision=RUNTIME,assessed_at=NOW)==path
    assert m.read_candidate_bundle(path,expected_runtime_revision=RUNTIME,assessed_at=NOW)==result
    changed=json.loads(path.read_text());changed['dynamics']['coefficients'][0]+=1
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError):m.read_candidate_bundle(path,expected_runtime_revision=RUNTIME,assessed_at=NOW)


def test_future_candidate_is_not_available_at_assessment(inputs,numerical_report):
    result=bundle(inputs,numerical_report)
    with pytest.raises(ValueError):module().validate_candidate_bundle(result,inputs,expected_runtime_revision=RUNTIME,assessed_at=NOW-timedelta(seconds=1))



def test_mixed_unknown_and_known_original_modes_are_counted_honestly():
    record=snapshot(steps=864,rich_actions=True,mode_delay_hours=12)
    result=bundle(record,make_report(record))
    counts=result['fit_evidence']['support']['regimes']
    assert counts['unknown']>0 and counts['warm']>0
    assert sum(counts.values())==sum(result['fit_evidence']['support']['origin_counts'].values())
    module().validate_candidate_bundle(result,record,expected_runtime_revision=RUNTIME,assessed_at=NOW)
