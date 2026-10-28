"""Original segmented inventory reads remain complete inside report reuse."""
from contextvars import Context
from contextlib import nullcontext
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from test_native_model_serving_receipt import serving, originals
from test_native_temperature_segmented_integration import retained_inputs
from test_native_thermal_forecast import ISSUE, future
from test_installed_shade_origin import weather, actions


@pytest.fixture(scope='module')
def serving_model(tmp_path_factory, originals):
    import native_thermal_forecast as forecasts
    values = serving(tmp_path_factory.mktemp('inventory-model'), originals)
    module = values[0]
    model = module.read_serving_model(values[-1], assessed_at=ISSUE, guard=lambda: None)
    yield forecasts, model
    model.verify_bindings(assessed_at=ISSUE, guard=lambda: None)


def segmented(tmp_path, serving_model, monkeypatch):
    forecasts, model = serving_model
    inputs = dict(forecast=weather(ISSUE), action_snapshot=actions(ISSUE))
    retained_inputs(tmp_path/'shared', inputs, monkeypatch)
    geometry = future(ISSUE)
    capture = forecasts.build_serving_capture(model, inputs, source_profile='segmented-v1',
        geometry=geometry, expected_geometry_sha256=geometry.sha256, issue=ISSUE,
        available=ISSUE, published=ISSUE+timedelta(seconds=2), check_budget=lambda: None)
    return forecasts, model, capture


def test_validated_segmented_inventory_reuses_decoding_but_reads_every_file(tmp_path, serving_model, monkeypatch):
    import household_score_report_reuse as reuse
    import weather_temperature_source_segments as codec
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    original_files = forecasts.origin_source_files
    original_validate = forecasts.validate_serving_capture
    decode = codec._decode_segment
    decodes = []
    def counted(*args, **kwargs):
        decodes.append(1)
        return decode(*args, **kwargs)
    monkeypatch.setattr(codec, '_decode_segment', counted)
    expected = original_files(capture)
    with reuse._capture_reads(lambda: None), capture_source_reads() as inventory:
        reads = []
        record = inventory.record
        def observed(path, raw):
            reads.append(Path(path))
            return record(path, raw)
        inventory.record = observed
        forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
        before = len(decodes)
        assert before > 0
        reads.clear()
        assert forecasts.origin_source_files(capture) == expected
        assert len(decodes) == before, 'validated inventory repeated full segmented decoding'
        assert set(expected) <= set(reads), 'an original child was omitted from fresh byte reads'
        Context().run(forecasts.origin_source_files, capture)
        assert len(decodes) > before, 'a foreign invocation borrowed inventory metadata'
        inventory.verify()
    assert forecasts.origin_source_files is original_files
    assert forecasts.validate_serving_capture is original_validate


@pytest.mark.parametrize('damage', ['manifest', 'child', 'replacement', 'binding', 'runtime'])
def test_segmented_inventory_refuses_changed_original_or_complete_key(tmp_path, serving_model, monkeypatch, damage):
    import household_score_report_reuse as reuse
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    files = forecasts.origin_source_files(capture)
    terminal = pytest.raises(ValueError) if damage in ('manifest', 'child', 'replacement') else nullcontext()
    with terminal, reuse._capture_reads(lambda: None), capture_source_reads():
        forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
        changed = deepcopy(capture)
        if damage == 'binding':
            changed['native_origin_binding']['source_manifest_sha256'] = '0'*64
        elif damage == 'runtime':
            changed['candidate']['runtime']['native_source_manifest']['openhab/scripts/native_thermal_forecast.py'] = '0'*64
        else:
            target = files[0] if damage == 'manifest' else files[-1]
            if damage == 'replacement':
                replacement = target.with_name('same-byte-replacement')
                replacement.write_bytes(target.read_bytes()); replacement.chmod(0o600); replacement.replace(target)
            else:
                target.write_bytes(target.read_bytes()+b' ')
        with pytest.raises(ValueError):
            forecasts.origin_source_files(changed)


@pytest.mark.parametrize('remaining', [-1., float('nan'), False])
def test_segmented_inventory_hit_keeps_original_numeric_deadline_refusals(tmp_path, serving_model, monkeypatch, remaining):
    import household_score_report_reuse as reuse
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    with reuse._capture_reads(lambda: None), capture_source_reads():
        forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
        with pytest.raises(ValueError):
            forecasts.origin_source_files(capture, check_budget=lambda: remaining)


def test_segmented_inventory_hit_detects_mutation_by_a_later_guard(tmp_path, serving_model, monkeypatch):
    import household_score_report_reuse as reuse
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    target = forecasts.origin_source_files(capture)[-1]
    with pytest.raises(ValueError), reuse._capture_reads(lambda: None), capture_source_reads():
        forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
        calls = []
        def guard():
            calls.append(1)
            if len(calls) == 2:
                target.write_bytes(target.read_bytes()+b' ')
            return 30.
        with pytest.raises(ValueError):
            forecasts.origin_source_files(capture, check_budget=guard)
        assert len(calls) >= 2


def test_failed_capture_does_not_admit_inventory_or_leak_temporary_metadata(tmp_path, serving_model, monkeypatch):
    import household_score_report_reuse as reuse
    import weather_temperature_source_segments as codec
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    decode = codec._decode_segment
    decodes = []
    def counted(*args, **kwargs):
        decodes.append(1)
        return decode(*args, **kwargs)
    monkeypatch.setattr(codec, '_decode_segment', counted)
    changed = deepcopy(capture)
    changed['output']['trajectory'][0]['air_f'] += 1
    changed['capture_sha256'] = forecasts.digest(changed, 'capture_sha256')
    with reuse._capture_reads(lambda: None), capture_source_reads():
        with pytest.raises(ValueError):
            forecasts.validate_serving_capture(changed, model, expected_capture_sha256=changed['capture_sha256'])
        before = len(decodes)
        forecasts.origin_source_files(capture)
        assert len(decodes) > before, 'failed capture admitted shared inventory metadata'


@pytest.mark.parametrize('limit,value', [('MAX_CAPTURE_CACHE_BYTES', 1), ('MAX_CAPTURE_CACHE_ENTRIES', 0)])
def test_segmented_inventory_retains_existing_metadata_bound(tmp_path, serving_model, monkeypatch, limit, value):
    import household_score_report_reuse as reuse
    import weather_temperature_source_segments as codec
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    decode = codec._decode_segment
    decodes = []
    def counted(*args, **kwargs):
        decodes.append(1)
        return decode(*args, **kwargs)
    monkeypatch.setattr(codec, '_decode_segment', counted)
    monkeypatch.setattr(reuse, limit, value)
    with reuse._capture_reads(lambda: None), capture_source_reads():
        forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
        before = len(decodes)
        forecasts.origin_source_files(capture)
        assert len(decodes) > before


@pytest.mark.parametrize('change', ['object', 'code'])
def test_changed_loaded_inventory_function_falls_back_to_original_replay(tmp_path, serving_model, monkeypatch, change):
    import household_score_report_reuse as reuse
    import weather_temperature_source_segments as codec
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    decode = codec._decode_segment
    decodes = []
    def counted(*args, **kwargs):
        decodes.append(1)
        return decode(*args, **kwargs)
    monkeypatch.setattr(codec, '_decode_segment', counted)
    with reuse._capture_reads(lambda: None), capture_source_reads():
        forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
        before = len(decodes)
        original = forecasts._source_fingerprints
        with monkeypatch.context() as patch:
            if change == 'object':
                patch.setattr(forecasts, '_source_fingerprints', lambda *a, **k: original(*a, **k))
            else:
                def unexpected(*args, **kwargs):
                    raise AssertionError('unknown loaded implementation executed by cache')
                patch.setattr(original, '__code__', unexpected.__code__)
            forecasts.origin_source_files(capture)
        assert len(decodes) > before


def test_prior_forecast_without_optional_inventory_exports_stays_supported(monkeypatch):
    import household_score_report_reuse as reuse
    import native_thermal_forecast as forecasts
    original = forecasts.validate_serving_capture
    monkeypatch.setattr(reuse, 'PRIOR_CAPTURE_SOURCE_SHA256', reuse.CAPTURE_SOURCE_SHA256)
    monkeypatch.setattr(reuse, 'CAPTURE_SOURCE_SHA256', '0'*64)
    for name in ('origin_source_files', '_source_fingerprints', '_segmented_helpers'):
        monkeypatch.delattr(forecasts, name)
    with reuse._capture_reads(lambda: None):
        assert not hasattr(forecasts, 'origin_source_files')
    assert forecasts.validate_serving_capture is original


@pytest.mark.parametrize('failure', [TimeoutError, KeyboardInterrupt])
def test_segmented_inventory_restores_scoped_adapters_on_failure(tmp_path, serving_model, monkeypatch, failure):
    import household_score_report_reuse as reuse
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    original_files = forecasts.origin_source_files
    original_validate = forecasts.validate_serving_capture
    with pytest.raises(failure):
        with reuse._capture_reads(lambda: None), capture_source_reads():
            forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
            with reuse._capture_reads(lambda: None):
                forecasts.origin_source_files(capture)
            raise failure()
    assert forecasts.origin_source_files is original_files
    assert forecasts.validate_serving_capture is original_validate


@pytest.mark.parametrize('damage', ['grid', 'trajectory'])
def test_shared_inventory_does_not_validate_changed_capture_inputs(tmp_path, serving_model, monkeypatch, damage):
    import household_score_report_reuse as reuse
    from thermal_model.replay_budget import capture_source_reads
    forecasts, model, capture = segmented(tmp_path, serving_model, monkeypatch)
    with reuse._capture_reads(lambda: None), capture_source_reads():
        forecasts.validate_serving_capture(capture, model, expected_capture_sha256=capture['capture_sha256'])
        changed = deepcopy(capture)
        if damage == 'grid':
            changed['inputs']['origin_temperatures']['roles']['air']['grid'][-1][1]['temperatureF'] += 1
        else:
            changed['output']['trajectory'][0]['air_f'] += 1
        changed['capture_sha256'] = forecasts.digest(changed, 'capture_sha256')
        with pytest.raises(ValueError):
            forecasts.validate_serving_capture(changed, model, expected_capture_sha256=changed['capture_sha256'])
