"""Explicit fixture acquisition keeps the real retained coordinator boundary."""
from contextlib import nullcontext
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import fcntl
import json
import os
import pytest
from test_native_monitor import originals
from test_household_retained_native_score import prepared, outer_context


def test_explicit_factory_scores_with_closed_config_and_nonrenewable_budget(tmp_path, originals, monkeypatch):
    import household_retained_native_score as retained
    live, settings, model, reader, args, stage = prepared(tmp_path, originals, monkeypatch)
    ticks = [0.]
    calls = []
    def factory(config, *, shared_lock_guard):
        expected = {key: settings[key] for key in ('token_file', 'native_db_config', 'native_policy', 'openhab_base')}
        expected.update(schema=live.COMPRESSED_SOURCE_SCHEMA,
                        output_directory=str(Path(settings['evidence_directory']) / ('scores-' + args['assessed_at'].strftime('%Y%m%d'))))
        assert config == expected
        assert shared_lock_guard() == 120.
        ticks[0] = 5.
        assert shared_lock_guard() == 115.
        calls.append(config)
        return reader
    monkeypatch.setattr(retained, '_reader_factory', lambda: pytest.fail('explicit acquisition selected the production factory'))
    result = retained.score_jobs(settings, guard=lambda: None, reader_factory=factory,
        serving_model=model, deadline=120., clock=lambda: args['assessed_at'], monotonic=lambda: ticks[0])
    assert result['scored'] == 1 and result['current_revision_scored'] == 1 and len(calls) == 1
    assert len(list(Path(settings['evidence_directory']).glob('scores-*/*.native-thermal-completion-v1.json'))) == 1


@pytest.mark.parametrize('kind', ['noncallable', 'ambiguous'])
def test_score_jobs_rejects_invalid_factory_before_acquisition(kind):
    import household_retained_native_score as retained
    options = dict(reader_factory=123) if kind == 'noncallable' else dict(reader=object(), reader_factory=lambda *a, **k: None)
    with pytest.raises(ValueError, match='reader factory|reader and reader_factory'):
        retained.score_jobs({}, guard=lambda: pytest.fail('invalid factory reached work'),
            deadline=120., clock=lambda: datetime.now(timezone.utc), monotonic=lambda: 0., **options)


def test_factory_is_not_called_for_a_mismatched_runtime(tmp_path, originals, monkeypatch):
    import household_retained_native_score as retained
    live, settings, model, reader, args, stage = prepared(tmp_path, originals, monkeypatch)
    settings['runtime_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='owned serving configuration differs'):
        retained.score_jobs(settings, guard=lambda: None, serving_model=model,
            reader_factory=lambda *a, **k: pytest.fail('mismatched model reached acquisition'),
            deadline=120., clock=lambda: args['assessed_at'], monotonic=lambda: 0.)


def test_factory_must_return_a_reader(tmp_path, originals, monkeypatch):
    import household_retained_native_score as retained
    live, settings, model, reader, args, stage = prepared(tmp_path, originals, monkeypatch)
    with pytest.raises(ValueError, match='reader factory returned no reader'):
        retained.score_jobs(settings, guard=lambda: None, serving_model=model,
            reader_factory=lambda *a, **k: None, deadline=120.,
            clock=lambda: args['assessed_at'], monotonic=lambda: 0.)
    assert not list(Path(settings['evidence_directory']).glob('scores-*/*.native-thermal-completion-v1.json'))


@pytest.mark.parametrize('supplied', [False, True])
def test_outer_run_forwards_only_explicit_factory_after_model_and_lock(tmp_path, monkeypatch, supplied):
    import native_model_serving_receipt as admission
    retained, config, options, ticks, events, now = outer_context(tmp_path, monkeypatch)
    seen = []
    def admitted(*a, **kw):
        kw['guard']()
        seen.append('model')
        return object()
    monkeypatch.setattr(admission, 'read_serving_model', admitted)
    factory = lambda *a, **kw: pytest.fail('outer wrapper invoked acquisition early')
    def score(settings, **kw):
        assert ('reader_factory' in kw) is supplied
        if supplied:
            assert kw['reader_factory'] is factory
        assert seen == ['model']
        fd = os.open(settings['shared_lock'], os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
        kw['guard']()
        seen.append('score')
        return {'status': 'waiting'}
    monkeypatch.setattr(retained, 'score_jobs', score)
    if supplied:
        options['reader_factory'] = factory
    assert retained.run(config, **options) == {'status': 'waiting'}
    assert seen == ['model', 'score']


@pytest.mark.parametrize('supplied', [False, True])
def test_coordinator_forwards_only_explicit_factory_with_source_checks(tmp_path, monkeypatch, supplied):
    import household_forecast_score as coordinator
    import household_cycle_deploy as deploy
    stage = tmp_path / 'stage'
    scripts = stage / 'sources/openhab/scripts'
    scripts.mkdir(parents=True)
    script = scripts / 'household_forecast_score.py'
    script.write_text('# retained numerical archive\n')
    script.chmod(0o644)
    dependency = scripts / 'household_cycle_deploy.py'
    dependency.write_text('# retained dependency context\n')
    dependency.chmod(0o644)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'schema': 'earthship-weathernext-thermal-live-config/v2'}))
    config.chmod(0o600)
    cycle = stage / 'cycle.json'
    cycle.write_text(json.dumps({'forecast_config': str(config)}))
    cycle.chmod(0o600)
    record = {'schema': 'earthship-household-cycle-deployment/v3',
              'source_manifest': {'openhab/scripts/household_forecast_score.py': sha256(script.read_bytes()).hexdigest()}}
    manifest = stage / 'deployment.json'
    manifest.write_text(json.dumps(record))
    manifest.chmod(0o600)
    monkeypatch.setattr(deploy, '__file__', str(dependency))
    monkeypatch.setattr(deploy, 'verify_stage', lambda *a, **kw: record)
    factory = lambda *a, **kw: None
    observed = []
    def run(config_arg, **kw):
        assert config_arg == config
        assert ('reader_factory' in kw) is supplied
        if supplied:
            assert kw['reader_factory'] is factory
        kw['source_guard']()
        observed.append(True)
        return {'status': 'waiting'}
    monkeypatch.setattr(coordinator, 'production_retained_runner', lambda: SimpleNamespace(run=run))
    monkeypatch.setattr(coordinator, 'production_score_policy', nullcontext)
    options = {'reader_factory': factory} if supplied else {}
    result = coordinator.run_retained_worker(script, config, stage=stage,
        deployment_sha256=sha256(manifest.read_bytes()).hexdigest(), retained_native=True,
        deadline=120., monotonic=lambda: 0., **options)
    assert result == {'status': 'waiting'} and observed == [True]


@pytest.mark.parametrize('boundary', ['coordinator', 'runner'])
def test_outer_boundaries_refuse_noncallable_factory(tmp_path, boundary):
    import household_forecast_score as coordinator
    import household_retained_native_score as retained
    with pytest.raises(ValueError, match='reader factory'):
        if boundary == 'coordinator':
            coordinator.run_retained_worker(tmp_path / 'script', tmp_path / 'config',
                stage=tmp_path, deployment_sha256='a' * 64, retained_native=True, reader_factory=123)
        else:
            retained.run(tmp_path / 'config', stage=tmp_path, deployment_sha256='a' * 64,
                deadline=120., resource_preflight=lambda: None, pressure_factory=lambda: None,
                source_guard=lambda: None, verify_archive=lambda: None, reader_factory=123)
