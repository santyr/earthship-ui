"""Read-only pre-fit capture and exact dataset reconstruction; no optimizers."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest
from thermal_model.forcing_capture import _canonical
from thermal_model.dataset import build_samples,dataset_manifest
from thermal_model.schema import THERMAL_ITEMS,OPTIONAL_OBSERVATION_ITEMS,ActionEvent,ModeEvent
from thermal_model.temperature_history import QualifiedTemperatureHistory,STREAMS
from test_thermal_pipeline import training_samples
from test_thermal_temperature_history import receipt


def module():
    from thermal_model import training_inputs
    return training_inputs


def inputs(*,missing=False,mixed=False):
    samples=training_samples();start=samples[0].at;end=samples[-1].at+timedelta(minutes=5)
    native={row.at:row for row in samples}
    def grid(stream,targets,assessed):
        role=next(role for role,value in STREAMS.items() if value[0]==stream)
        field={'air':'air_f','mass':'mass_f','outdoor':'outdoor_f'}[role]
        return [(at,None if missing and role=='air' and at==samples[1].at else receipt(at,getattr(native[at],field))) for at in targets]
    def legacy(item,left,right):
        role=next(role for role,name in {**THERMAL_ITEMS,**OPTIONAL_OBSERVATION_ITEMS}.items() if name==item)
        if role=='radiation':return [(row.at,row.radiation_wm2) for row in samples]
        if role in STREAMS:
            field={'air':'air_f','mass':'mass_f','outdoor':'outdoor_f'}[role]
            return [(row.at,getattr(row,field)) for row in samples if left<=row.at<right]
        return []
    reader=QualifiedTemperatureHistory(legacy,grid,cutover=start+timedelta(minutes=10) if mixed else start,assessed_at=end,retain_raw=True)
    action=ActionEvent('original-action','original-receipt',start,start,'indoor_shade','open','historical_reconstruction',.35)
    mode=ModeEvent('original-mode','original-receipt',start,start,'warm','manual_dm',1.)
    journal=SimpleNamespace(effective_events=lambda *_:[action],effective_modes=lambda *_:[mode])
    return dict(start=start,end=end,series_reader=reader,journal=journal,clock=lambda:end,revision_reader=lambda:'a'*64)


def test_capture_reconstructs_original_dataset_without_fitting(tmp_path,monkeypatch):
    import thermal_model.pipeline as pipeline
    def prohibited(*args,**kwargs):pytest.fail('capture invoked fitting')
    monkeypatch.setattr(pipeline,'run_training',prohibited)
    monkeypatch.setattr(pipeline,'fit_dynamics_with_evidence',prohibited)
    data=inputs();record=module().capture_training_inputs(**data)
    path=module().write_training_inputs(tmp_path,record)
    assert module().read_training_inputs(path)==record
    restored=module().restore_training_inputs(record)
    series={role:tuple(restored.series_reader(item,data['start'],data['end'])) for role,item in {**THERMAL_ITEMS,**OPTIONAL_OBSERVATION_ITEMS}.items()}
    events=restored.journal.effective_events(data['start'],data['end']);modes=restored.journal.effective_modes(data['start'],data['end'])
    samples=build_samples(series,events,modes,data['start'],data['end'])
    assert dataset_manifest(samples,events,modes)==record['dataset_manifest']
    assert len(samples)==4
    assert events[0].source=='historical_reconstruction' and events[0].confidence==.35
    assert restored.series_reader.temperature_grids()==record['temperature_grids']
    assert all(record[key] is False for key in ('fitting_executed','installed','release_authorized'))
    assert path.stat().st_mode & 0o777==0o600
    assert module().write_training_inputs(tmp_path,record)==path
    with pytest.raises(ValueError):restored.series_reader(THERMAL_ITEMS['air'],data['start'],data['end']+timedelta(minutes=5))


def test_missing_native_receipt_remains_an_invalid_barrier_after_restore():
    data=inputs(missing=True);record=module().capture_training_inputs(**data)
    assert record['series_by_role']['air'][1][1] is None
    restored=module().restore_training_inputs(record)
    assert list(restored.series_reader(THERMAL_ITEMS['air'],data['start'],data['end']))[1][1] is None
    assert record['temperature_grids']['air'][1][1] is None
    assert record['dataset_manifest']['sample_count']<4


@pytest.mark.parametrize('damage',['series','grid','manifest','flag','extra'])
def test_rehash_cannot_repair_inconsistent_or_promoted_snapshot(damage):
    record=module().capture_training_inputs(**inputs())
    if damage=='series':record['series_by_role']['air'][0][1]+=1
    elif damage=='grid':record['temperature_grids']['air'][0][1]['temperatureF']+=1
    elif damage=='manifest':record['dataset_manifest']['sample_count']+=1
    elif damage=='flag':record['fitting_executed']=True
    else:record['qualified']=True
    record['snapshot_sha256']=sha256(_canonical({key:value for key,value in record.items() if key!='snapshot_sha256'})).hexdigest()
    with pytest.raises(ValueError):module().restore_training_inputs(record)


def test_legacy_reader_without_raw_native_retention_refuses_before_io():
    data=inputs()
    def prohibited(*args,**kwargs):pytest.fail('unqualified reader reached collection')
    data['series_reader']=prohibited
    with pytest.raises(ValueError):module().capture_training_inputs(**data)


def test_oversized_series_stops_consuming_at_bound(monkeypatch):
    data=inputs();reader=data['series_reader'];count=[0]
    def oversized(*args):
        for index in range(10):count[0]+=1;yield data['start'],72.
    oversized.temperature_grids=reader.temperature_grids;oversized.evidence_manifest=reader.evidence_manifest;oversized.retains_native_grids=True
    data['series_reader']=oversized;monkeypatch.setattr(module(),'MAX_SERIES_POINTS',2)
    with pytest.raises(ValueError):module().capture_training_inputs(**data)
    assert count[0]==3


def test_exposed_snapshot_refuses_private_reader(tmp_path):
    record=module().capture_training_inputs(**inputs());path=module().write_training_inputs(tmp_path,record);path.chmod(0o644)
    with pytest.raises(ValueError):module().read_training_inputs(path)


def test_rebuilt_dataset_cannot_relabel_raw_temperatures_as_original_receipts():
    from datetime import datetime
    data=inputs();record=module().capture_training_inputs(**data)
    record['series_by_role']['air'][0][1]+=1
    raw={role:[(datetime.fromisoformat(at),value) for at,value in rows] for role,rows in record['series_by_role'].items()}
    events=data['journal'].effective_events(data['start'],data['end']);modes=data['journal'].effective_modes(data['start'],data['end'])
    samples=build_samples(raw,events,modes,data['start'],data['end'])
    record['dataset_manifest']=dataset_manifest(samples,events,modes)
    record['snapshot_sha256']=sha256(_canonical({key:value for key,value in record.items() if key!='snapshot_sha256'})).hexdigest()
    with pytest.raises(ValueError,match='native receipts'):module().restore_training_inputs(record)


def test_interrupted_private_write_removes_partial_file(tmp_path,monkeypatch):
    source=module();record=source.capture_training_inputs(**inputs())
    def interrupted(path,raw):path.write_bytes(b'partial');raise OSError('write interrupted')
    monkeypatch.setattr(source,'_write_private',interrupted)
    with pytest.raises(OSError):source.write_training_inputs(tmp_path,record)
    assert list(tmp_path.iterdir())==[]


def test_nonretaining_native_reader_refuses_before_source_io():
    data=inputs();reader=data['series_reader'];reader._raw_grids=None
    def prohibited(*args,**kwargs):pytest.fail('nonretaining reader reached source I/O')
    reader.grid_reader=prohibited
    with pytest.raises(ValueError):module().capture_training_inputs(**data)


@pytest.mark.parametrize('damage',['future_end','future_event'])
def test_future_inputs_do_not_enter_original_snapshot(damage):
    from dataclasses import replace
    data=inputs()
    if damage=='future_end':data['clock']=lambda:data['end']-timedelta(seconds=1)
    else:
        events=data['journal'].effective_events(data['start'],data['end'])
        data['journal'].effective_events=lambda *_:[replace(events[0],received_at=data['end']+timedelta(seconds=1))]
    with pytest.raises(ValueError):module().capture_training_inputs(**data)


@pytest.mark.parametrize('operation',['capture','restore'])
def test_oversized_interval_refuses_before_io_or_dataset_expansion(monkeypatch,operation):
    source=module();data=inputs();record=source.capture_training_inputs(**data)
    def prohibited(*args,**kwargs):pytest.fail('oversized interval reached source or reconstruction')
    monkeypatch.setattr(source,'build_samples',prohibited)
    ancient=data['end']-timedelta(days=36500)
    if operation=='restore':
        record['start']=ancient.isoformat()
        record['snapshot_sha256']=sha256(_canonical({key:value for key,value in record.items() if key!='snapshot_sha256'})).hexdigest()
        with pytest.raises(ValueError):source.restore_training_inputs(record)
    else:
        reader=data['series_reader'];prohibited.retains_native_grids=True
        prohibited.temperature_grids=reader.temperature_grids;prohibited.evidence_manifest=reader.evidence_manifest
        data.update(start=ancient,series_reader=prohibited)
        with pytest.raises(ValueError):source.capture_training_inputs(**data)


def test_existing_changed_snapshot_is_not_overwritten(tmp_path):
    source=module();record=source.capture_training_inputs(**inputs());path=source.write_training_inputs(tmp_path,record)
    path.write_text('{}')
    with pytest.raises(ValueError):source.write_training_inputs(tmp_path,record)
    assert path.read_text()=='{}'


def test_mixed_legacy_native_cutover_and_mode_fields_are_preserved():
    data=inputs(mixed=True);source=module();record=source.capture_training_inputs(**data)
    restored=source.restore_training_inputs(record)
    assert len(restored.samples)==4
    for role in STREAMS:
        assert record['temperature_evidence']['roles'][role]['legacy_points']==2
        assert record['temperature_evidence']['roles'][role]['qualified']==2
        assert len(record['temperature_grids'][role])==2
    assert restored.journal.effective_modes(data['start'],data['end'])==tuple(data['journal'].effective_modes(data['start'],data['end']))
    assert record['release_authorized'] is False
