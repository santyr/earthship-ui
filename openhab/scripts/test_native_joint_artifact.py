"""The four-regime model has a distinct identity and replay-bound support evidence."""
from datetime import timedelta
import json
import pytest
import native_thermal_artifact as api
from native_thermal_fit import fit_native_development
from test_native_thermal_artifact import fixture,encode
from test_native_thermal_inputs import build,geometry
from test_installed_shade_inputs import snapshot,START,END

@pytest.fixture(scope='module')
def joint_originals():
    import os
    old=os.environ.get('EARTHSHIP_QUALIFICATION_FIT');os.environ['EARTHSHIP_QUALIFICATION_FIT']='1'
    try:
        r=snapshot();d=build(r);g=geometry(r)
        f=fit_native_development(d,expected_dataset_sha256=d.sha256,training_start=START,training_end=END,guard=lambda:None,timeout_seconds=20,joint=True)
        return r,d,g,f
    finally:
        if old is None:os.environ.pop('EARTHSHIP_QUALIFICATION_FIT',None)
        else:os.environ['EARTHSHIP_QUALIFICATION_FIT']=old

def make(tmp_path,joint_originals):
    paths,_,at=fixture(tmp_path,joint_originals);runtime=api.current_native_runtime()
    e=json.loads(paths['fit_evidence'].read_bytes());e.update(schema='earthship-native-development-fit-evidence/v3',fit_runtime=runtime)
    paths['fit_evidence'].write_bytes(encode(e))
    c=api.build_native_candidate(originals=paths,runtime=runtime,created_at=at)
    return c,paths,runtime,at

def test_joint_candidate_has_separate_version_and_replays_every_original(tmp_path,joint_originals):
    c,paths,runtime,at=make(tmp_path,joint_originals)
    assert c['schema']=='earthship-provisional-thermal-candidate/v3'
    assert c['fit']['regime_support']['unshaded']['status']=='prior_only'
    p=api.write_native_candidate(tmp_path,c,assessed_at=at,runtime=runtime,expected_artifact_sha256=c['artifact_sha256'])
    assert api.read_native_candidate(p,assessed_at=at,runtime=runtime,expected_artifact_sha256=c['artifact_sha256'])==c

@pytest.mark.parametrize('damage',['rating','support','coefficient','source'])
def test_resealed_joint_fit_cannot_forge_rating_measured_support_or_math(damage,tmp_path,joint_originals):
    c,paths,runtime,at=make(tmp_path,joint_originals);e=json.loads(paths['fit_evidence'].read_bytes())
    if damage=='rating':e['fit']['shade_context']['nominal_shade_rejection_fraction']=.5
    if damage=='support':e['fit']['regime_support']['unshaded']['status']='observed_unqualified'
    if damage=='coefficient':e['fit']['coefficients'][4]+=.00001
    if damage=='source':runtime['native_source_manifest'].pop('openhab/thermal-shade-context.json');runtime['native_code_revision']=api.digest(runtime['native_source_manifest'])
    paths['fit_evidence'].write_bytes(encode(e))
    with pytest.raises(ValueError):api.build_native_candidate(originals=paths,runtime=runtime,created_at=at)

def test_joint_receipt_admission_and_fast_binding_preserve_distinct_rule(tmp_path,joint_originals):
    import native_model_serving_receipt as serving
    c,paths,runtime,at=make(tmp_path,joint_originals);p=tmp_path/'candidate.json';p.write_bytes(encode(c));p.chmod(0o600)
    directory=tmp_path/'admission';directory.mkdir(mode=0o700)
    receipt=serving.admit_model(p,runtime=runtime,expected_artifact_sha256=c['artifact_sha256'],directory=directory,clock=lambda:at+timedelta(seconds=1),guard=lambda:None)
    value=json.loads(receipt.read_bytes());assert value['model_rule']=='earthship-native-joint-shade-dynamics/v3'

@pytest.mark.parametrize('fit',[None,[],False])
def test_malformed_fit_profile_is_a_clean_refusal(fit,tmp_path,joint_originals):
    c,paths,runtime,at=make(tmp_path,joint_originals);e=json.loads(paths['fit_evidence'].read_bytes());e['fit']=fit
    paths['fit_evidence'].write_bytes(encode(e))
    with pytest.raises(ValueError):api.build_native_candidate(originals=paths,runtime=runtime,created_at=at)
