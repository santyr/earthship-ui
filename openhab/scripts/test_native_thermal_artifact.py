"""Native artifact identity requires original data, fit and runtime correspondence."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import importlib,json
import pytest
from test_native_thermal_inputs import build,geometry
from test_installed_shade_inputs import snapshot,START,END
from native_thermal_fit import fit_native_development


def api():return importlib.import_module('native_thermal_artifact')
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


@pytest.fixture(scope='module')
def originals():
    import os
    previous=os.environ.get('EARTHSHIP_QUALIFICATION_FIT');os.environ['EARTHSHIP_QUALIFICATION_FIT']='1'
    try:
        record=snapshot();data=build(record);g=geometry(record)
        fit=fit_native_development(data,expected_dataset_sha256=data.sha256,training_start=START,
            training_end=END,guard=lambda:None,timeout_seconds=20)
    finally:
        if previous is None:os.environ.pop('EARTHSHIP_QUALIFICATION_FIT',None)
        else:os.environ['EARTHSHIP_QUALIFICATION_FIT']=previous
    return record,data,g,fit


def fixture(tmp_path,originals):
    record,data,g,fit=originals;tmp_path.chmod(0o700)
    base=dict(schema='earthship-thermal-runtime-binding/v1',code_revision='a'*64,observer_revision='b'*64,
        interpreter_sha256='c'*64,python_version='3.12.0',dependencies={'numpy':'1.26.0','scipy':'1.11.0','psycopg2':'2.9.0'},
        source_manifest={'thermal_intel.py':'a'*64,'thermal_model/origin_capture.py':'b'*64})
    names=['openhab/scripts/'+name for name in ('native_thermal_inputs.py','native_thermal_model.py',
        'native_thermal_fit.py','native_thermal_artifact.py','astro_geometry.py','astro_geometry_series.py',
        'astro_forecast_context.py','astro_geometry_worker.py')]+['scripts/java/NativeSolarGeometry.java']
    sources={name:'d'*64 for name in names}
    runtime=dict(schema='earthship-native-thermal-runtime-binding/v1',base_runtime=base,
        native_source_manifest=sources,native_code_revision=sha256(encode(sources)).hexdigest())
    evidence=dict(schema='earthship-native-development-fit-evidence/v2',created_at=(END+timedelta(seconds=5)).isoformat(),
        code_revision='e'*40,fit_runtime=runtime,fit=fit,release_authorized=False,production_model_changed=False)
    paths={}
    for role,name,value in (('snapshot',record['snapshot_sha256']+'.training-inputs-v2.json',record),
        ('dataset',data.sha256+'.native-development-data-v1.json',data.to_dict()),
        ('geometry',g.sha256+'.native-geometry-series-v1.json',g.to_dict()),('fit_evidence','fit.json',evidence)):
        path=tmp_path/name;path.write_bytes(encode(value));path.chmod(0o600);paths[role]=path
    return paths,runtime,END+timedelta(seconds=8)


def candidate(tmp_path,originals):
    paths,runtime,now=fixture(tmp_path,originals)
    value=api().build_native_candidate(originals=paths,runtime=runtime,created_at=now)
    return value,paths,runtime,now


def test_native_artifact_roundtrips_complete_original_lineage_and_old_reader_refuses(tmp_path,originals):
    value,paths,runtime,now=candidate(tmp_path,originals)
    assert value['schema']=='earthship-provisional-thermal-candidate/v2'
    assert set(value['originals'])=={'snapshot','dataset','geometry','fit_evidence'}
    assert value['fit']['dataset_sha256']==originals[1].sha256 and not value['fit']['graduated']
    target=api().write_native_candidate(tmp_path,value,assessed_at=now,runtime=runtime,expected_artifact_sha256=value['artifact_sha256'])
    assert api().read_native_candidate(target,assessed_at=now,runtime=runtime,expected_artifact_sha256=value['artifact_sha256'])==value
    from thermal_model.provisional_artifact import validate_candidate
    with pytest.raises(ValueError):validate_candidate(value,assessed_at=now)


@pytest.mark.parametrize('role',['snapshot','dataset','geometry','fit_evidence'])
def test_native_artifact_refuses_changed_original_dependency(role,tmp_path,originals):
    value,paths,runtime,now=candidate(tmp_path,originals);paths[role].write_bytes(b'{}')
    with pytest.raises(ValueError):api().validate_native_candidate(value,assessed_at=now,runtime=runtime,expected_artifact_sha256=value['artifact_sha256'])


@pytest.mark.parametrize('damage',['authority','native_rule','dataset_pin','fit_coefficients','runtime','chronology'])
def test_resealed_artifact_still_requires_original_fit_runtime_and_chronology(damage,tmp_path,originals):
    value,paths,runtime,now=candidate(tmp_path,originals)
    if damage=='authority':value['fit']['graduated']=True
    if damage=='native_rule':value['fit']['solar_feature']['exponent']=2
    if damage=='dataset_pin':value['fit']['dataset_sha256']='f'*64
    if damage=='fit_coefficients':value['fit']['coefficients'][5]+=0.001
    if damage=='runtime':value['runtime']['base_runtime']['interpreter_sha256']='f'*64;value['runtime_sha256']=api().digest(value['runtime'])
    if damage=='chronology':value['created_at']=(END+timedelta(seconds=1)).isoformat()
    value['artifact_sha256']=api().digest(value,'artifact_sha256')
    with pytest.raises(ValueError):api().validate_native_candidate(value,assessed_at=now,runtime=runtime,expected_artifact_sha256=value['artifact_sha256'])


@pytest.mark.parametrize('damage',['missing_java','unknown_source','dependency','manifest_pin'])
def test_native_runtime_is_closed_and_retains_required_native_and_base_sources(damage,tmp_path,originals):
    _,runtime,_=fixture(tmp_path,originals)
    if damage=='missing_java':runtime['native_source_manifest'].pop('scripts/java/NativeSolarGeometry.java')
    if damage=='unknown_source':runtime['native_source_manifest']['private/config.json']='f'*64
    if damage=='dependency':runtime['base_runtime']['dependencies'].pop('scipy')
    if damage=='manifest_pin':runtime['native_code_revision']='f'*64
    else:runtime['native_code_revision']=sha256(encode(runtime['native_source_manifest'])).hexdigest()
    with pytest.raises(ValueError):api().validate_native_runtime(runtime)


def test_native_artifact_rejects_unknown_external_identity_even_when_self_consistent(tmp_path,originals):
    value,_,runtime,now=candidate(tmp_path,originals)
    with pytest.raises(ValueError):api().validate_native_candidate(value,assessed_at=now,runtime=runtime,expected_artifact_sha256='f'*64)



@pytest.mark.parametrize('damage',['loss','rank','endpoint_counts'])
def test_artifact_rederives_fit_statistics_instead_of_accepting_resealed_evidence(damage,tmp_path,originals):
    paths,runtime,now=fixture(tmp_path,originals);evidence=json.loads(paths['fit_evidence'].read_bytes())
    if damage=='loss':evidence['fit']['initial_objective']+=1
    if damage=='rank':evidence['fit']['conditioning_rank']=0
    if damage=='endpoint_counts':
        evidence['fit']['endpoint_count']=2;evidence['fit']['horizon_support']['1']=2
    paths['fit_evidence'].write_bytes(encode(evidence))
    with pytest.raises(ValueError):api().build_native_candidate(originals=paths,runtime=runtime,created_at=now)
