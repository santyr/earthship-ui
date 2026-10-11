"""Original model context shares one expanded identity without physical authority."""
import importlib,json
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_household_power_snapshot import inputs,build as source_build,NOW
from test_household_models import prepared_thermal


def api():return importlib.import_module('household.model_snapshot')


def source_at(at):
    value=inputs();delta=int((at-NOW).total_seconds()*1000)
    value['base_inputs']['as_of']=at.isoformat();value['base_inputs']['created_at']=at.isoformat()
    for row in value['base_inputs']['sources']:
        data=json.loads(row['raw'])
        for key in ('recordedAt','observedAt','scaleObservedAt','validUntil'):
            if isinstance(data.get(key),int):data[key]+=delta
            elif isinstance(data.get(key),str):data[key]=(instant(data[key])+at-NOW).isoformat()
        row['raw']=json.dumps(data);row['expected_sha256']=sha256(row['raw'].encode()).hexdigest();row['persisted_at']=at.isoformat()
    for row in value['power_sources']:
        data=json.loads(row['raw']);data['recordedAt']+=delta
        for field in data['fields'].values():field['observedAt']+=delta;field['validUntil']+=delta
        row['raw']=json.dumps(data);row['expected_sha256']=sha256(row['raw'].encode()).hexdigest();row['persisted_at']=at.isoformat()
    return source_build(value)


def make(tmp_path,monkeypatch):
    thermal,capture=prepared_thermal(tmp_path,monkeypatch);at=instant(thermal.to_dict()['issue']);source=source_at(at)
    snapshot=api().bind_model_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],thermal_inputs=thermal,code_revision='e'*40)
    return snapshot,source,thermal,capture


def test_original_thermal_metadata_and_measurements_share_one_identity(tmp_path,monkeypatch):
    snap,source,thermal,_=make(tmp_path,monkeypatch);doc=snap.to_dict();prepared=thermal.to_dict()
    assert doc['schema']=='earthship-household-snapshot/v3'
    assert doc['source_snapshot']['snapshot_id']==source['snapshot']['snapshot_id']
    assert doc['domains']['thermal']['thermal_artifact_identity']['value']==prepared['artifact_sha256']
    assert doc['domains']['thermal']['thermal_model_confidence']['value']=='low'
    assert doc['domains']['thermal']['mass_temperature']==prepared['snapshot']['domains']['thermal']['mass_temperature']
    assert doc['as_of']==prepared['issue'] and doc['created_at']==prepared['snapshot']['created_at']
    assert doc['planner_authority']=='none' and doc['model_context_scope']=='retained_original_provisional'
    assert doc['domains']['thermal']['thermal_artifact_identity']['evidence']['quality']!='qualified'


def test_missing_model_is_explicit_not_inferred():
    source=source_at(NOW);snap=api().bind_model_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],thermal_inputs=None,code_revision='e'*40)
    assert snap.to_dict()['domains']['thermal']['thermal_model_confidence']['value'] is None
    assert snap.to_dict()['thermal_context'] is None


def test_later_source_cannot_be_backdated_to_old_thermal_origin(tmp_path,monkeypatch):
    _,source,thermal,_=make(tmp_path,monkeypatch)
    later=source_at(instant(thermal.to_dict()['issue'])+timedelta(seconds=1))
    with pytest.raises(ValueError):api().bind_model_snapshot(source_receipt=later,source_runtime_manifest=later['runtime_manifest'],thermal_inputs=thermal,code_revision='e'*40)


def test_original_source_expires_when_common_model_origin_is_later(tmp_path,monkeypatch):
    _,_,thermal,_=make(tmp_path,monkeypatch);older=source_at(instant(thermal.to_dict()['issue'])-timedelta(seconds=31))
    snap=api().bind_model_snapshot(source_receipt=older,source_runtime_manifest=older['runtime_manifest'],thermal_inputs=thermal,code_revision='e'*40)
    assert snap.to_dict()['domains']['energy']['inverter_output_w']['value'] is None
    assert snap.to_dict()['completeness']['current_energy'] is False


def test_snapshot_is_immutable_and_metadata_cannot_be_changed(tmp_path,monkeypatch):
    snap,_,_,_=make(tmp_path,monkeypatch);doc=snap.to_dict();doc.pop('snapshot_id')
    doc['domains']['thermal']['thermal_model_confidence']['value']='high'
    with pytest.raises(ValueError):api().ModelSnapshot(canonical(doc),snap.original_source)
    changed=snap.to_dict();changed['domains']['energy']['battery_soc']['value']=0
    assert snap.to_dict()['domains']['energy']['battery_soc']['value']==100


def test_model_binding_validates_exact_prepared_context(tmp_path,monkeypatch):
    snap,_,thermal,_=make(tmp_path,monkeypatch);api().verify_model_binding(snap,thermal)
    with pytest.raises(ValueError):api().verify_model_binding(snap,None)


def test_binding_and_restore_do_not_read_files(tmp_path,monkeypatch):
    snap,source,thermal,_=make(tmp_path,monkeypatch);import builtins
    def forbidden(*a,**k):pytest.fail('read inside model binding')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden)
    repeated=api().bind_model_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],thermal_inputs=thermal,code_revision='e'*40)
    assert repeated.to_dict()==snap.to_dict()
    assert api().restore_model_snapshot(snap.to_dict(),source_receipt=source).to_dict()==snap.to_dict()
