"""Raw preregistration contracts; fixtures never establish household qualification."""
from copy import deepcopy
from datetime import datetime,timedelta
import pytest
from test_installed_shade_raw_calibration import candidate,retained_raw_case,collection,issued,release_case
from test_installed_shade_qualification import numerical_policy
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_artifact import _digest


@pytest.fixture
def registration_routing(tmp_path,monkeypatch):
    # Explicit source-routing seam only; valid full policy math stays real.
    from thermal_model import policy_registration as registration
    policy=numerical_policy();root=tmp_path/'seal';root.mkdir(mode=0o700)
    at=datetime.fromisoformat(policy['declared_at'])+timedelta(minutes=1)
    monkeypatch.setattr(registration,'_clock',lambda:at)
    sources=[dict(raw_score_sources_path=str(tmp_path/('b'*64+'.installed-shade-score-sources-v2.json')))]
    proof=dict(development_origins={'b'*64+'.installed-shade-score-sources-v2.json':'b'*64},
        development_source_bindings=[dict(native_binding_sha256='a'*64,raw_score_sources_sha256='b'*64)])
    monkeypatch.setattr(registration,'_score_raw_development_sources',lambda *args:deepcopy(proof),raising=False)
    return registration,root,policy,sources,proof,at


def test_raw_registration_has_distinct_contract_and_typed_readback(registration_routing):
    registration,root,policy,sources,proof,_=registration_routing
    path=registration.register_raw_calibrated_installed_shade_policy(root,policy,sources)
    record=registration.read_raw_calibrated_installed_shade_registered_policy(path)
    assert path.name==policy['policy_sha256']+'.installed-shade-registration-v3.json'
    assert path.stat().st_mode&0o777==0o600
    assert record['schema']=='earthship-installed-shade-policy-registration/v3'
    assert record['candidate_schema']=='earthship-installed-shade-candidate/v3'
    assert record['source_contract']=='earthship-installed-shade-score-sources/v2'
    assert record['development_sources']==sources
    assert record['development_source_bindings']==proof['development_source_bindings']
    assert record['release_authorized'] is False
    with pytest.raises(ValueError):registration.read_calibrated_installed_shade_registered_policy(path)
    assert registration.register_raw_calibrated_installed_shade_policy(root,policy,sources)==path


def test_raw_development_replays_original_queries_and_refuses_changed_baselines(retained_raw_case):
    from thermal_model import policy_registration as registration
    from thermal_model import installed_shade_qualification as qualification
    _,values,_,_,_=retained_raw_case
    scored=qualification._score_packets(values['original_pairs'],assessed_at=values['created_at'],version=4)
    from thermal_model.graduation_policy import RECORD_FIELDS
    policy=dict(candidate=dict(sensor_epochs=candidate_epochs(scored)),
        development=[{key:row[key] for key in RECORD_FIELDS} for row in scored['rows']])
    proof=registration._score_raw_development_sources(values['original_pairs'],policy,values['created_at'])
    assert proof['development_source_bindings']==scored['bindings']
    policy['development'][0]['persistence_error_f']+=1
    with pytest.raises(ValueError,match='development differs'):
        registration._score_raw_development_sources(values['original_pairs'],policy,values['created_at'])


def candidate_epochs(scored):return scored['rows'][0]['sensor_epochs']


def test_raw_development_refuses_missing_query_and_receipt_only_sources(retained_raw_case):
    from pathlib import Path
    from thermal_model import policy_registration as registration
    from thermal_model import installed_shade_qualification as qualification
    from thermal_model.graduation_policy import RECORD_FIELDS
    _,values,backend,_,header=retained_raw_case
    scored=qualification._score_packets(values['original_pairs'],assessed_at=values['created_at'],version=4)
    policy=dict(candidate=dict(sensor_epochs=candidate_epochs(scored)),
        development=[{key:row[key] for key in RECORD_FIELDS} for row in scored['rows']])
    with pytest.raises(ValueError):registration._score_raw_development_sources([header['score_sources']],policy,values['created_at'])
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):
        registration._score_raw_development_sources(values['original_pairs'],policy,values['created_at'])


@pytest.mark.parametrize('damage',['late_start','elapsed_during_replay'])
def test_raw_registration_cannot_be_sealed_after_release_interval_begins(registration_routing,monkeypatch,damage):
    registration,root,policy,sources,proof,at=registration_routing
    holdout=datetime.fromisoformat(policy['intervals']['holdout_start'])
    if damage=='late_start':monkeypatch.setattr(registration,'_clock',lambda:holdout)
    else:
        clock={'at':at};monkeypatch.setattr(registration,'_clock',lambda:clock['at'])
        def sources_elapsed(*args):clock['at']=holdout;return deepcopy(proof)
        monkeypatch.setattr(registration,'_score_raw_development_sources',sources_elapsed)
    with pytest.raises(ValueError):registration.register_raw_calibrated_installed_shade_policy(root,policy,sources)
    assert not list(root.glob('*.installed-shade-registration-v3.json'))



def test_raw_registration_refuses_if_release_starts_during_private_write(registration_routing,monkeypatch):
    registration,root,policy,sources,_,at=registration_routing
    from thermal_model import runtime_bundle
    holdout=datetime.fromisoformat(policy['intervals']['holdout_start']);clock={'at':at}
    monkeypatch.setattr(registration,'_clock',lambda:clock['at'])
    write=runtime_bundle._write_private
    def elapsed(path,raw):
        write(path,raw);clock['at']=holdout
    monkeypatch.setattr(runtime_bundle,'_write_private',elapsed)
    with pytest.raises(ValueError):registration.register_raw_calibrated_installed_shade_policy(root,policy,sources)
    assert not list(root.glob('*.installed-shade-registration-v3.json'))



@pytest.mark.parametrize('damage',['raw_binding','source_contract'])
def test_raw_seal_refuses_rehashed_source_metadata(registration_routing,damage):
    registration,root,policy,sources,_,_=registration_routing
    path=registration.register_raw_calibrated_installed_shade_policy(root,policy,sources)
    record=registration._read_private(path)
    if damage=='raw_binding':record['development_source_bindings'][0]['native_binding_sha256']='c'*64
    else:record['source_contract']='earthship-installed-shade-score-sources/v1'
    record['registration_sha256']=_digest({key:value for key,value in record.items() if key!='registration_sha256'})
    path.write_bytes(_canonical(record));path.chmod(0o600)
    with pytest.raises(ValueError):registration.read_raw_calibrated_installed_shade_registered_policy(path)
