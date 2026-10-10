"""Distinct provisional model identity and original input pinning."""
from datetime import datetime,timedelta,timezone
import json
import pytest
from test_installed_shade_fit import COEFFICIENTS


def module():
    from thermal_model import provisional_artifact
    return provisional_artifact


def example(tmp_path):
    now=datetime(2026,10,10,18,tzinfo=timezone.utc)
    tmp_path.chmod(0o700);snapshot=tmp_path/'snapshot';snapshot.write_text('original fixture bytes');snapshot.chmod(0o600)
    fit=dict(mode='provisional',confidence='low',coefficients=list(COEFFICIENTS),initial_coefficients=list(COEFFICIENTS),initial_objective=2.,final_objective=1.,regularization_strength=1.,conditioning_rank=4,normalized_condition_number=None,iterations=1,endpoint_count=2,fit_executed=True,stability_assessed=False,graduated=False,prediction_intervals=None,automatic_actuation=False,source_snapshot_sha256='a'*64,sensor_epochs={role:str(__import__('uuid').UUID(int=i+1)) for i,role in enumerate(('air','mass','outdoor'))},training_start=(now-timedelta(days=1)).isoformat(),training_end=(now-timedelta(hours=1)).isoformat(),horizon_support={'1':2,'6':0,'12':0,'24':0},independent_origin_dates=1)
    return module().build_candidate(fit,runtime={'identity':'synthetic'},snapshot_path=snapshot,created_at=now),snapshot,now


def test_provisional_candidate_retains_weak_evidence_honestly(tmp_path):
    value,_,now=example(tmp_path)
    assert value['schema']=='earthship-provisional-thermal-candidate/v1'
    assert value['fit']['conditioning_rank']==4
    module().validate_candidate(value,assessed_at=now,runtime={'identity':'synthetic'})


@pytest.mark.parametrize('damage',['authority','coefficients','chronology','original_loss'])
def test_rehashed_unsafe_or_changed_originals_refuse(tmp_path,damage):
    value,snapshot,now=example(tmp_path)
    if damage=='authority':value['fit']['graduated']=True
    if damage=='coefficients':value['fit']['coefficients'][0]=float('nan')
    if damage=='chronology':value['fit']['training_end']=(now+timedelta(hours=1)).isoformat()
    if damage=='original_loss':snapshot.write_text('changed original fixture')
    if damage!='coefficients':value['artifact_sha256']=module().candidate_digest(value)
    with pytest.raises(ValueError):module().validate_candidate(value,assessed_at=now)
