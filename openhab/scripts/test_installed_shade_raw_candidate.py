"""Raw candidate proof contracts; synthetic fixtures confer no release authority."""
from copy import deepcopy
import pytest
from test_installed_shade_raw_calibration import candidate,prepared,original,source_case,raw_routing_case
from test_installed_shade_calibrated import runtime
from thermal_model.installed_shade_artifact import _digest


@pytest.fixture
def raw_candidate_values(raw_routing_case,candidate):
    calibration,values=raw_routing_case
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    new=runtime(candidate)
    for name in RAW_RUNTIME_PATHS-new['source_manifest'].keys():new['source_manifest'][name]='7'*64
    return dict(base_bundle=candidate[0],inputs=candidate[1],calibration=calibration.build_raw_calibration(**values),
        original_pairs=values['original_pairs'],base_runtime=candidate[2],runtime=new,created_at=values['created_at'])


def test_raw_candidate_requires_explicit_raw_calibration_and_contract(raw_candidate_values):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    record=artifact.build_raw_calibrated_candidate(**raw_candidate_values)
    assert record['schema']=='earthship-installed-shade-candidate/v3'
    assert record['calibration']['schema']=='earthship-installed-shade-calibration/v2'
    assert record['calibration']['source_contract']=='earthship-installed-shade-score-sources/v2'
    assert record['trained_through']==raw_candidate_values['calibration']['calibration_end']
    assert record['release_authorized'] is False and record['as_issued_evidence'] is False
    with pytest.raises(ValueError):artifact._shape(record,expected_runtime_revision=_digest(raw_candidate_values['runtime']),
        assessed_at=raw_candidate_values['created_at'])
    legacy=deepcopy(raw_candidate_values)
    legacy['calibration']['schema']='earthship-installed-shade-calibration/v1'
    legacy['calibration'].pop('source_contract')
    legacy['calibration']['calibration_sha256']=_digest({k:v for k,v in legacy['calibration'].items() if k!='calibration_sha256'})
    with pytest.raises(ValueError):artifact.build_raw_calibrated_candidate(**legacy)


@pytest.mark.parametrize('damage',['closure','dependency','metadata'])
def test_raw_candidate_refuses_incompatible_runtime_and_rehashed_metadata(raw_candidate_values,damage):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values=deepcopy(raw_candidate_values)
    if damage=='metadata':
        record=artifact.build_raw_calibrated_candidate(**values)
        record['calibration']['source_contract']='earthship-installed-shade-score-sources/v1'
        record['artifact_sha256']=_digest({k:v for k,v in record.items() if k!='artifact_sha256'})
        parameters={k:values[k] for k in ('base_bundle','inputs','calibration','original_pairs')}
        with pytest.raises(ValueError):artifact.validate_raw_calibrated_candidate(record,**parameters,
            expected_runtime_revision=_digest(values['runtime']),assessed_at=values['created_at'])
    else:
        if damage=='closure':values['runtime']['source_manifest'].pop('thermal_model/installed_shade_raw_score_sources.py')
        else:values['runtime']['dependencies']['numpy']='9.0.0'
        with pytest.raises(ValueError):artifact.build_raw_calibrated_candidate(**values)



def test_raw_candidate_private_storage_and_legacy_reader_refusal(raw_candidate_values,tmp_path):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values=raw_candidate_values;record=artifact.build_raw_calibrated_candidate(**values)
    root=tmp_path/'raw-candidate';root.mkdir(mode=0o700)
    parameters={k:values[k] for k in ('base_bundle','inputs','calibration','original_pairs')}
    revision=_digest(values['runtime'])
    path=artifact.write_raw_calibrated_candidate(root,record,**parameters,
        expected_runtime_revision=revision,assessed_at=values['created_at'])
    assert path.name==record['artifact_sha256']+'.installed-shade-candidate-v3.json'
    assert path.stat().st_mode&0o777==0o600
    actual=artifact.read_raw_calibrated_candidate(path,expected_runtime_revision=revision,assessed_at=values['created_at'])
    assert actual['artifact']==record and actual['calibration']==values['calibration']
    with pytest.raises(ValueError):artifact.read_calibrated_candidate(path,
        expected_runtime_revision=revision,assessed_at=values['created_at'])


from test_installed_shade_raw_calibration import retained_raw_case,collection,issued,release_case


def test_raw_candidate_readback_replays_original_calibration_queries(retained_raw_case,candidate):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_artifact as artifact
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    calibration,source_values,backend,root,_=retained_raw_case
    new=runtime(candidate)
    for name in RAW_RUNTIME_PATHS-new['source_manifest'].keys():new['source_manifest'][name]='7'*64
    record=calibration.build_raw_calibration(**source_values)
    values=dict(base_bundle=candidate[0],inputs=candidate[1],calibration=record,
        original_pairs=source_values['original_pairs'],base_runtime=candidate[2],runtime=new,
        created_at=source_values['created_at'])
    aggregate=artifact.build_raw_calibrated_candidate(**values)
    archive=root/'candidate';archive.mkdir(mode=0o700)
    parameters={k:values[k] for k in ('base_bundle','inputs','calibration','original_pairs')}
    revision=_digest(new)
    path=artifact.write_raw_calibrated_candidate(archive,aggregate,**parameters,
        expected_runtime_revision=revision,assessed_at=values['created_at'])
    assert artifact.read_raw_calibrated_candidate(path,expected_runtime_revision=revision,
        assessed_at=values['created_at'])['artifact']==aggregate
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):artifact.read_raw_calibrated_candidate(path,
        expected_runtime_revision=revision,assessed_at=values['created_at'])
