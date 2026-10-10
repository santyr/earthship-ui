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


from test_installed_shade_raw_calibration import retained_source_calibration_case,source_calibration_origin_case,raw_math_capture


@pytest.fixture
def source_candidate_values(retained_source_calibration_case):
    from thermal_model.installed_shade_calibration import build_source_calibration
    values,root,_,args,backend=retained_source_calibration_case
    new=deepcopy(args['runtime']);new['code_revision']='9'*64
    result=dict(base_bundle=values['bundle'],inputs=values['inputs'],calibration=build_source_calibration(**values),
        original_pairs=values['original_pairs'],base_runtime=args['runtime'],runtime=new,created_at=values['created_at'])
    return result,root,args,backend


def test_source_candidate_has_distinct_original_query_calibration_contract(source_candidate_values):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values,_,_,_=source_candidate_values
    assert hasattr(artifact,'build_source_calibrated_candidate'),'missing original-query calibrated candidate'
    record=artifact.build_source_calibrated_candidate(**values)
    assert record['schema']=='earthship-installed-shade-candidate/v4'
    assert record['calibration']['schema']=='earthship-installed-shade-calibration/v3'
    assert record['calibration']['source_contract']=='earthship-installed-shade-score-sources/v4'
    assert record['release_authorized'] is False and record['as_issued_evidence'] is False
    assert record['calibration']['bands']['24']['overall'] is None
    for version in (2,3):
        with pytest.raises(ValueError):artifact._shape(record,expected_runtime_revision=_digest(values['runtime']),
            assessed_at=values['created_at'],_version=version)


@pytest.mark.parametrize('lost',['issue','outcome'])
def test_source_candidate_refuses_missing_originals_after_calibration(source_candidate_values,lost):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values,_,args,backend=source_candidate_values
    assert hasattr(artifact,'build_source_calibrated_candidate'),'missing original-query calibrated candidate'
    Path(args['native_source_paths']['air'] if lost=='issue' else backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):artifact.build_source_calibrated_candidate(**values)


@pytest.mark.parametrize('case',['unchanged','readback_issue','temporary_issue'])
def test_source_candidate_storage_replays_originals_and_guards_final_temporary_write(source_candidate_values,monkeypatch,case):
    import json
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_artifact as artifact,runtime_bundle
    values,root,args,_=source_candidate_values
    assert hasattr(artifact,'write_source_calibrated_candidate'),'missing original-query candidate retention'
    assert hasattr(artifact,'read_source_calibrated_candidate'),'missing original-query candidate readback'
    record=artifact.build_source_calibrated_candidate(**values)
    archive=root/'candidate';archive.mkdir(mode=0o700)
    original=runtime_bundle._write_private
    def written(path,raw):
        original(path,raw);value=json.loads(raw)
        if case=='temporary_issue' and isinstance(value,dict) and value.get('schema')=='earthship-installed-shade-candidate/v4':
            Path(args['native_source_paths']['mass']).unlink()
    monkeypatch.setattr(runtime_bundle,'_write_private',written)
    params={k:values[k] for k in ('base_bundle','inputs','calibration','original_pairs')}
    revision=_digest(values['runtime'])
    if case=='temporary_issue':
        with pytest.raises((ValueError,OSError)):artifact.write_source_calibrated_candidate(archive,record,**params,
            expected_runtime_revision=revision,assessed_at=values['created_at'])
        assert not Path(args['native_source_paths']['mass']).exists()
        assert not list(archive.glob('*.installed-shade-candidate-v4.json'))
        assert not list(archive.glob('.calibration-*'))
    else:
        path=artifact.write_source_calibrated_candidate(archive,record,**params,
            expected_runtime_revision=revision,assessed_at=values['created_at'])
        assert path.name==record['artifact_sha256']+'.installed-shade-candidate-v4.json'
        assert path.stat().st_mode&0o777==0o600
        for reader in (artifact.read_calibrated_candidate,artifact.read_raw_calibrated_candidate):
            with pytest.raises(ValueError):reader(path,expected_runtime_revision=revision,assessed_at=values['created_at'])
        if case=='readback_issue':Path(args['native_source_paths']['outdoor']).unlink()
        if case=='readback_issue':
            with pytest.raises((ValueError,OSError)):artifact.read_source_calibrated_candidate(path,expected_runtime_revision=revision,assessed_at=values['created_at'])
        else:
            actual=artifact.read_source_calibrated_candidate(path,expected_runtime_revision=revision,assessed_at=values['created_at'])
            assert actual['artifact']==record and actual['calibration']==values['calibration']


@pytest.mark.parametrize('damage',['closure','old_calibration'])
def test_source_candidate_refuses_incompatible_closure_and_calibration_profile(source_candidate_values,damage):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values,_,_,_=source_candidate_values
    values=deepcopy(values)
    if damage=='closure':values['runtime']['source_manifest'].pop('thermal_model/installed_shade_raw_score_sources.py')
    else:
        values['calibration']['schema']='earthship-installed-shade-calibration/v2'
        values['calibration']['source_contract']='earthship-installed-shade-score-sources/v2'
        values['calibration']['calibration_sha256']=_digest({k:v for k,v in values['calibration'].items() if k!='calibration_sha256'})
    with pytest.raises(ValueError):artifact.build_source_calibrated_candidate(**values)


@pytest.mark.parametrize('lost',['issue','outcome'])
def test_source_candidate_rechecks_originals_after_final_shape_work(source_candidate_values,monkeypatch,lost):
    from pathlib import Path
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values,_,args,backend=source_candidate_values
    original=artifact._shape
    def checked_then_lost(*a,**kw):
        result=original(*a,**kw)
        if kw.get('_version')==4:
            Path(args['native_source_paths']['air'] if lost=='issue' else backend.native_source_paths[-1]).unlink()
        return result
    monkeypatch.setattr(artifact,'_shape',checked_then_lost)
    with pytest.raises((ValueError,OSError)):artifact.build_source_calibrated_candidate(**values)
    assert not Path(args['native_source_paths']['air'] if lost=='issue' else backend.native_source_paths[-1]).exists()


def test_source_candidate_validator_replays_original_calibration_instead_of_rehashed_band_metadata(source_candidate_values):
    from thermal_model import installed_shade_calibrated_artifact as artifact
    values,_,_,_=source_candidate_values
    record=artifact.build_source_calibrated_candidate(**values)
    params={k:values[k] for k in ('base_bundle','inputs','calibration','original_pairs')}
    params.update(expected_runtime_revision=_digest(values['runtime']),assessed_at=values['created_at'])
    assert artifact.validate_source_calibrated_candidate(record,**params)==record
    altered=deepcopy(record);altered['calibration']['bands']['24']['overall']=1.
    altered['artifact_sha256']=_digest({k:v for k,v in altered.items() if k!='artifact_sha256'})
    with pytest.raises(ValueError):artifact.validate_source_calibrated_candidate(altered,**params)
