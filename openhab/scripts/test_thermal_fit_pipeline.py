"""Proof persistence orchestration; fitting dependencies are controlled boundaries."""
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace

import pytest

from thermal_model import fit_evidence,pipeline
from test_thermal_pipeline import (orchestration_dependencies,RecordingRegistry,FakeJournal,NOW,
                                  multihorizon_fit_result)
from test_thermal_fit_evidence import inputs


def dependencies(monkeypatch,events):
    values=orchestration_dependencies([],eligible=True)
    def fit(rows,*,collect_graduation_evidence=False):
        assert collect_graduation_evidence is True;events.append('measured_fit')
        return multihorizon_fit_result()
    values['dynamics_fitter']=fit
    # Numerical proof construction is covered with real measurements separately.
    monkeypatch.setattr(fit_evidence,'build_fit_evidence',lambda artifact,fitted:dict(release_authorized=False))
    return values


def test_requested_proof_is_persisted_before_shadow_candidate_promotion(monkeypatch):
    events=[];registry=RecordingRegistry()
    def writer(artifact,proof):
        assert proof['release_authorized'] is False
        assert registry.calls==['report'];events.append('proof')
    result=pipeline.run_training(start=NOW-timedelta(days=30),end=NOW,registry=registry,journal=FakeJournal([]),
        fit_evidence_writer=writer,**dependencies(monkeypatch,events))
    assert events==['measured_fit','proof']
    assert registry.calls==['report','candidate','promote']
    assert result.promoted is True


def test_proof_persistence_failure_preserves_previous_shadow_candidate(monkeypatch):
    events=[];registry=RecordingRegistry()
    def writer(*_):raise OSError('disk failure')
    with pytest.raises(pipeline.TrainingRefused,match='fit evidence persistence failed'):
        pipeline.run_training(start=NOW-timedelta(days=30),end=NOW,registry=registry,journal=FakeJournal([]),
            fit_evidence_writer=writer,**dependencies(monkeypatch,events))
    assert registry.calls==['report'] and registry.artifact is None


def test_raw_training_snapshot_is_written_before_candidate_promotion(monkeypatch):
    import thermal_model.training_sources as sources
    events=[];registry=RecordingRegistry()
    monkeypatch.setattr(sources,'build_training_sources',lambda samples,reader:dict(schema='earthship-thermal-training-sources/v1'))
    def writer(artifact,record):
        assert registry.calls==['report'];events.append('raw_sources')
        assert record['schema']=='earthship-thermal-training-sources/v1'
    pipeline.run_training(start=NOW-timedelta(days=30),end=NOW,registry=registry,journal=FakeJournal([]),
        training_sources_writer=writer,**orchestration_dependencies([],eligible=True))
    assert events==['raw_sources']
    assert registry.calls==['report','candidate','promote']


def test_raw_source_persistence_failure_preserves_previous_candidate(monkeypatch):
    import thermal_model.training_sources as sources
    registry=RecordingRegistry()
    monkeypatch.setattr(sources,'build_training_sources',lambda *_:{})
    def writer(*_):raise OSError('private storage failure')
    with pytest.raises(pipeline.TrainingRefused,match='training source persistence failed'):
        pipeline.run_training(start=NOW-timedelta(days=30),end=NOW,registry=registry,journal=FakeJournal([]),
            training_sources_writer=writer,**orchestration_dependencies([],eligible=True))
    assert registry.calls==['report'] and registry.artifact is None
