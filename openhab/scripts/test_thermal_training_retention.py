"""Native training receipt retention without fitting or source relabeling."""
from datetime import timedelta
from copy import deepcopy

import pytest

from thermal_model.temperature_history import QualifiedTemperatureHistory,STREAMS
from thermal_model.schema import THERMAL_ITEMS
from test_thermal_temperature_history import AT,receipt


def reader(*,retain=True,missing=False):
    def grid(stream,targets,assessed):
        return [(at,None if missing and at==AT else receipt(at)) for at in targets]
    return QualifiedTemperatureHistory(lambda *_:[],grid,cutover=AT,
        assessed_at=AT+timedelta(days=2),retain_raw=retain)


def fill(value):
    return {role:value(THERMAL_ITEMS[role],AT,AT+timedelta(minutes=10)) for role in STREAMS}


def test_retained_grids_are_exact_original_native_receipts_and_values_are_unchanged():
    kept=reader();plain=reader(retain=False)
    assert fill(kept)==fill(plain)
    assert kept.evidence_manifest()==plain.evidence_manifest()
    grids=kept.temperature_grids()
    assert set(grids)==set(STREAMS)
    assert grids['air'][0][0]==AT.isoformat()
    assert grids['air'][0][1]['streamEpoch']==receipt(AT)['streamEpoch']
    assert grids['air'][0][1]['storedAt']==AT.isoformat()
    with pytest.raises(ValueError):plain.temperature_grids()


def test_retained_native_grids_preserve_missing_data_barriers():
    value=reader(missing=True);fill(value)
    assert value.temperature_grids()['mass'][0][1] is None
    assert value.evidence_manifest()['roles']['mass']['missing']==1


def test_caller_cannot_mutate_retained_evidence():
    value=reader();fill(value)
    copied=value.temperature_grids();copied['air'][0][1]['temperatureF']=99
    assert value.temperature_grids()['air'][0][1]['temperatureF']==70


def test_incomplete_reader_cannot_claim_a_complete_training_snapshot():
    value=reader();value(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=10))
    with pytest.raises(ValueError):value.temperature_grids()


def test_configured_retention_requires_native_reader_configuration(monkeypatch):
    import thermal_temperature_runtime as runtime
    with pytest.raises(ValueError):runtime.configured_history(lambda *_:[],AT,environ={},retain_raw=True)
    monkeypatch.setattr(runtime,'_configured_grid_reader',lambda *_args,**kwargs:lambda stream,targets,assessed:[(at,receipt(at)) for at in targets])
    env=dict(THERMAL_TEMP_QUALIFIED_ENABLE='1',THERMAL_TEMP_EVIDENCE_CUTOVER=AT.isoformat())
    configured=runtime.configured_history(lambda *_:[],AT+timedelta(days=1),environ=env,retain_raw=True)
    fill(configured)
    assert configured.temperature_grids()['outdoor']
