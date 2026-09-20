from copy import deepcopy
from datetime import timedelta
import math

import pytest

from test_weather_temperature_reader import AT, EPOCH
from thermal_model.schema import THERMAL_ITEMS
from thermal_model.temperature_history import QualifiedTemperatureHistory, STREAMS, validate_evidence_manifest
from thermal_temperature_runtime import configured_history


def receipt(at, value=70):
    return dict(temperatureF=value, receivedAt=at-timedelta(seconds=30), storedAt=at,
                validUntil=at+timedelta(seconds=90), streamEpoch=EPOCH, snapshotSha256='a'*64)


def reader(*, legacy=None, grid=None, cutover=AT, now=AT+timedelta(days=3)):
    return QualifiedTemperatureHistory(legacy or (lambda item,start,end: []),
        grid or (lambda stream,targets,assessed: [(at,receipt(at)) for at in targets]),
        cutover=cutover, assessed_at=now)


def test_cutover_preserves_legacy_and_unchanged_qualified_values_without_relabeling():
    calls=[]
    def legacy(item,start,end):
        calls.append((item,start,end))
        return [(start,69)]
    r=reader(legacy=legacy)
    for role in STREAMS:
        points=r(THERMAL_ITEMS[role],AT-timedelta(minutes=5),AT+timedelta(minutes=10))
        assert points == [(AT-timedelta(minutes=5),69),(AT,70),(AT+timedelta(minutes=5),70)]
    assert all(end == AT for _,_,end in calls)
    evidence=r.evidence_manifest()
    validate_evidence_manifest(evidence)
    assert all(info['legacy_points']==1 and info['qualified']==2 for info in evidence['roles'].values())
    assert evidence['semantics']=='legacy_before_cutover_receipt_asof_after'


def test_missing_receipts_are_barriers_not_numeric_fallback():
    def forbidden(*args): pytest.fail('post-cutover numeric fallback')
    r=reader(legacy=forbidden,grid=lambda stream,targets,assessed:[(at,None) for at in targets])
    points=r(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=15))
    assert len(points)==3 and all(math.isnan(value) for _,value in points)


def test_receipt_failure_aborts_without_numeric_fallback():
    def failed(*args): raise RuntimeError('unavailable')
    def forbidden(*args): pytest.fail('post-cutover numeric fallback')
    with pytest.raises(RuntimeError,match='unavailable'):
        reader(legacy=forbidden,grid=failed)(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=5))


def test_queries_are_day_bounded_and_targets_unique():
    calls=[]
    def grid(stream,targets,assessed):
        calls.append(targets)
        return [(at,receipt(at)) for at in targets]
    points=reader(grid=grid)(THERMAL_ITEMS['mass'],AT,AT+timedelta(days=2,minutes=5))
    assert list(map(len,calls))==[288,288,1]
    assert len(set(at for at,_ in points))==577


@pytest.mark.parametrize('offset', [1,-1])
def test_unaligned_cutover_is_rejected(offset):
    with pytest.raises(ValueError): reader(cutover=AT+timedelta(seconds=offset))


def test_legacy_boundary_violation_is_rejected():
    with pytest.raises(ValueError,match='cutover boundary'):
        reader(legacy=lambda *args:[(AT,70)])(THERMAL_ITEMS['air'],AT-timedelta(minutes=5),AT+timedelta(minutes=5))


def test_other_sources_keep_their_existing_contract():
    r=reader(legacy=lambda item,start,end:[(start,12)])
    assert r(THERMAL_ITEMS['radiation'],AT,AT+timedelta(minutes=5))==[(AT,12)]


def test_invalid_grid_and_receipt_refuse_whole_series():
    bad=receipt(AT); bad['receivedAt']=AT+timedelta(seconds=1)
    for rows in ([],[(AT+timedelta(seconds=1),receipt(AT))],[(AT,bad)]):
        with pytest.raises(ValueError):
            reader(grid=lambda *args:rows)(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=5))


@pytest.mark.parametrize('gap_minutes',[30,40])
def test_dataset_cannot_interpolate_over_unqualified_grid_targets(gap_minutes):
    from test_thermal_dataset import START, END, fully_labeled_events
    from thermal_model.dataset import build_samples
    gap=START+timedelta(minutes=gap_minutes)
    def legacy(item,start,end):
        return [(start+timedelta(minutes=m),0 if item==THERMAL_ITEMS['radiation'] else 70)
                for m in range(0,int((end-start).total_seconds()/60),5)]
    r=reader(legacy=legacy,cutover=START+timedelta(minutes=30),now=END,
        grid=lambda stream,targets,assessed:[(at,None if at==gap else receipt(at)) for at in targets])
    series={role:r(item,START,END) for role,item in THERMAL_ITEMS.items()}
    samples=build_samples(series,fully_labeled_events(),[],START,END)
    assert gap not in {sample.at for sample in samples}
    assert gap+timedelta(minutes=5) in {sample.at for sample in samples}
    assert all(samples.interpolation_counts[role]==0 for role in STREAMS)


def manifest():
    r=reader()
    for role in STREAMS:r(THERMAL_ITEMS[role],AT,AT+timedelta(minutes=5))
    return r.evidence_manifest()


@pytest.mark.parametrize('field,value',[('qualified',2),('sensor_id',999),('grid_sha256','bad'),('targets',True)])
def test_provenance_tampering_is_rejected(field,value):
    evidence=manifest(); evidence['roles']['air'][field]=value
    with pytest.raises(ValueError):validate_evidence_manifest(evidence)


def test_existing_and_qualified_artifacts_validate():
    from dataclasses import replace
    from test_thermal_artifacts import valid_artifact
    from thermal_model.artifacts import (validate_artifact, ArtifactValidationError,
                                        _artifact_payload, _artifact_from_payload)
    import json
    artifact=valid_artifact()
    validate_artifact(artifact)
    from weather_temperature_reader import _utc
    data=deepcopy(artifact.data_manifest)
    end=_utc(data['end']); start=_utc(data['start'])
    r=reader(cutover=end-timedelta(minutes=5),now=end)
    for role in STREAMS:r(THERMAL_ITEMS[role],start,end)
    data['temperature_evidence']=r.evidence_manifest()
    validate_artifact(replace(artifact,data_manifest=data))
    decoded=_artifact_from_payload(json.loads(json.dumps(
        _artifact_payload(replace(artifact,data_manifest=data)),allow_nan=False)))
    validate_artifact(decoded)
    assert decoded.data_manifest['temperature_evidence']==data['temperature_evidence']
    data['temperature_evidence']['roles']['air']['sensor_id']=999
    with pytest.raises(ArtifactValidationError,match='temperature source evidence'):
        validate_artifact(replace(artifact,data_manifest=data))


def test_manifest_counts_must_cover_entire_postcutover_training_window():
    with pytest.raises(ValueError,match='training window'):
        validate_evidence_manifest(manifest(),start=AT,end=AT+timedelta(minutes=10))


def test_pipeline_persists_source_evidence_in_candidate():
    from test_thermal_pipeline import (NOW, FakeJournal, RecordingRegistry,
        orchestration_dependencies, run_training)
    calls=[]; dependencies=orchestration_dependencies(calls,eligible=True)
    dependencies['series_reader']=reader(cutover=NOW-timedelta(minutes=5),now=NOW)
    registry=RecordingRegistry()
    result=run_training(start=NOW-timedelta(days=30),end=NOW,
                        registry=registry,journal=FakeJournal(calls),**dependencies)
    evidence=result.artifact.data_manifest['temperature_evidence']
    validate_evidence_manifest(evidence,start=NOW-timedelta(days=30),end=NOW)
    assert evidence['roles']['air']['targets']==1


def test_cli_training_uses_configured_reader(monkeypatch):
    import thermal_intel
    import thermal_temperature_runtime
    from types import SimpleNamespace
    selected=object()
    monkeypatch.setattr(thermal_temperature_runtime,'configured_history',lambda legacy,now:selected)
    monkeypatch.setattr(thermal_intel,'_offline_journal',lambda parser:object())
    args=SimpleNamespace(start=AT-timedelta(days=1),end=AT,state_dir='/tmp/not-written')
    assert thermal_intel._training_kwargs(args,None,AT)['series_reader'] is selected


def env():
    return dict(THERMAL_TEMP_QUALIFIED_ENABLE='1',THERMAL_TEMP_EVIDENCE_CUTOVER=AT.isoformat(),
                THERMAL_TEMP_DB_CONFIG='/private/db.json',THERMAL_TEMP_POLICY='/private/policy.json')


def test_optin_is_explicit_and_invalid_configuration_never_falls_back():
    legacy=lambda *args:[]
    assert configured_history(legacy,AT,environ={}) is legacy
    for changes in ({'THERMAL_TEMP_QUALIFIED_ENABLE':'0'},{'THERMAL_TEMP_POLICY':'relative'},
                    {'THERMAL_TEMP_EVIDENCE_CUTOVER':'bad'}):
        with pytest.raises(ValueError):configured_history(legacy,AT,environ={**env(),**changes})


def test_runtime_worker_timeout_aborts_training_read(monkeypatch):
    import subprocess
    import thermal_temperature_runtime as runtime
    def timeout(*args,**kwargs):
        assert kwargs['timeout']<=30 and kwargs['stderr']==subprocess.DEVNULL
        raise subprocess.TimeoutExpired('worker',30)
    monkeypatch.setattr(runtime.subprocess,'run',timeout)
    r=configured_history(lambda *args:pytest.fail('fallback'),AT+timedelta(hours=1),environ=env())
    with pytest.raises(subprocess.TimeoutExpired):r(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=5))


def test_total_worker_budget_is_enforced_before_spawning(monkeypatch):
    import thermal_temperature_runtime as runtime
    clock=iter([0,901])
    monkeypatch.setattr(runtime.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(runtime.subprocess,'run',lambda *args,**kwargs:pytest.fail('expired worker launched'))
    r=configured_history(lambda *args:[],AT+timedelta(hours=1),environ=env())
    with pytest.raises(ValueError,match='budget exceeded'):
        r(THERMAL_ITEMS['air'],AT,AT+timedelta(minutes=5))
