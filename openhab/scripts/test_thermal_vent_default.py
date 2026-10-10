"""Forecast-only closed-vent default, including the Mountain/DST boundary."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

import thermal_intel
from thermal_model import behavior, pipeline
from test_thermal_pipeline import AcceptedRegistry, accepted_artifact, current_states, NOW

UTC = timezone.utc
LOCAL = ZoneInfo('America/Denver')
CUTOFF = datetime(2026, 11, 1, 6, tzinfo=UTC)


def hourly(start, hours=48, *, mode='warm'):
    # Advance in UTC: November 1 contains two different local 01:00 hours.
    return [dict(at=start + timedelta(hours=i), tempF=60., radiationWm2=0.,
                 weatherCode=1, windMph=3., mode=mode) for i in range(hours + 1)]


def shadow_inputs(now):
    artifact = accepted_artifact()
    artifact.created_at = (now - timedelta(hours=2)).isoformat()
    artifact.trained_through = (now - timedelta(hours=3)).isoformat()
    current = current_states()
    for value in current.values():
        if isinstance(value, dict):
            value['at'] = now - timedelta(minutes=2)
    for value in current['observed']:
        value['at'] += now - NOW
    return artifact, current


def native(rows):
    grid = pipeline.interpolate_hourly_forecast(rows, start=rows[0]['at'], end=rows[-1]['at'])
    for row in grid:
        row.update(air_f=74., mass_f=72., air_baseline_f=74., mass_baseline_f=72.)
    return grid


def test_pre_november_publication_inputs_remain_unchanged():
    rows = hourly(datetime(2026, 10, 4, 12, tzinfo=UTC))
    assert thermal_intel._apply_vent_default(rows) == rows
    assert all('_ventClosedFrom' not in row for row in rows)


@pytest.mark.parametrize('now', [CUTOFF, datetime(2026, 12, 15, 12, tzinfo=UTC),
                                  datetime(2027, 7, 1, 12, tzinfo=UTC)])
def test_closed_default_persists_until_operator_changes_it(now):
    rows = thermal_intel._apply_vent_default(hourly(now))
    grid = native(rows)
    schedule = pipeline._expand_nightly_venting(behavior.baseline_schedule(accepted_artifact().behavior, grid), grid, LOCAL)
    assert schedule['mode'] == 'warm'
    assert schedule['ventOpenAt'] is None and schedule['ventCloseAt'] is None
    assert schedule['airflowSegments'] == ()
    assert all(row['vent_open'] == 0. for row in behavior._forcing_rows(grid, schedule))
    search = behavior.search_candidate_schedule(behavior=accepted_artifact().behavior,
                                               dynamics=accepted_artifact().dynamics, forecast=grid)
    assert search.candidate is None


def test_crossing_midnight_clips_only_venting_and_keeps_shade_and_mode():
    raw = hourly(CUTOFF - timedelta(hours=12))
    unmodified = native(raw)
    grid = native(thermal_intel._apply_vent_default(raw))
    old = pipeline._expand_nightly_venting(behavior.baseline_schedule(accepted_artifact().behavior, unmodified), unmodified, LOCAL)
    new = pipeline._expand_nightly_venting(behavior.baseline_schedule(accepted_artifact().behavior, grid), grid, LOCAL)
    assert new['ventCloseAt'].astimezone(UTC) == CUTOFF
    assert new['airflowSegments'] and all(segment['endAt'].astimezone(UTC) <= CUTOFF for segment in new['airflowSegments'])
    old_forcing = behavior._forcing_rows(unmodified, old)
    new_forcing = behavior._forcing_rows(grid, new)
    for before, after in zip(old_forcing, new_forcing):
        assert after['indoor_shade_closed'] == before['indoor_shade_closed']
        assert after['outdoor_shade_present'] == before['outdoor_shade_present']
        assert after['vent_open'] == (before['vent_open'] if after['at'] < CUTOFF else 0.)
    assert any(row['vent_open'] == 1. for row in new_forcing if row['at'] < CUTOFF)
    assert {row['mode'] for row in grid} == {'warm'}
    pipeline._validate_internal_schedule(new, horizon_start=grid[0]['at'], horizon_end=grid[-1]['at'])


def test_publication_discloses_assumption_without_changing_action_evidence():
    now = CUTOFF
    artifact, current = shadow_inputs(now)
    rows = thermal_intel._apply_vent_default(hourly(now))
    output = pipeline.run_shadow(registry=AcceptedRegistry(artifact), current=current, forecast=rows, now=now)
    assert output['status'] == 'shadow'
    assert output['schedule']['baseline'] == {'ventOpenAt': None, 'ventCloseAt': None}
    assert output['schedule']['candidate'] is None
    assert all(not any(marker.startswith('vent_') for marker in point['actions']) for point in output['forecast']['trajectory'])
    assert output['confidence']['actionLabels'] == 'reconstructed'
    assert output['provenance']['actions'] == 'historical_reconstruction'
    assert any('operator closed-vent default' in reason for reason in output['reasons'])


def test_old_capture_without_policy_still_uses_original_vent_schedule():
    # Replay must consume the captured inputs, never today's mutable default.
    grid = native(hourly(CUTOFF))
    schedule = behavior.baseline_schedule(accepted_artifact().behavior, grid)
    assert schedule['ventOpenAt'] is not None
    assert any(row['vent_open'] == 1. for row in behavior._forcing_rows(grid, schedule))


@pytest.mark.parametrize('policy', ['2026-11-01T00:00:00', 'bogus', 0])
def test_invalid_captured_policy_is_rejected(policy):
    rows = hourly(CUTOFF)
    for row in rows:
        row['_ventClosedFrom'] = policy
    with pytest.raises(ValueError):
        native(rows)


def test_conflicting_or_partially_missing_policy_is_rejected():
    rows = hourly(CUTOFF)
    for row in rows:
        row['_ventClosedFrom'] = CUTOFF.isoformat()
    rows[-1].pop('_ventClosedFrom')
    with pytest.raises(ValueError):
        native(rows)
    rows[-1]['_ventClosedFrom'] = (CUTOFF + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError):
        native(rows)


def test_publisher_captures_default_and_replay_ignores_later_policy_change(tmp_path, monkeypatch, capsys):
    from dataclasses import replace
    from types import SimpleNamespace
    from thermal_model.forcing_capture import verify_capture
    from test_thermal_artifacts import valid_artifact
    now = CUTOFF
    _, current = shadow_inputs(now)
    artifact = replace(valid_artifact(), created_at=(now-timedelta(hours=2)).isoformat())
    archive = tmp_path / 'captures'
    archive.mkdir(mode=0o700)
    rows = hourly(now)
    monkeypatch.setenv('THERMAL_SHADOW_CAPTURE_DIR', str(archive))
    monkeypatch.setattr(thermal_intel.forecast_intel, 'load_site_settings', lambda: {})
    monkeypatch.setattr(thermal_intel.forecast_intel, 'fetch_forecast', lambda: {})
    monkeypatch.setattr(thermal_intel, '_current_states', lambda at: current)
    monkeypatch.setattr(thermal_intel, '_forecast_rows', lambda snapshot, at: rows)
    monkeypatch.setattr(thermal_intel, 'ArtifactRegistry', lambda path: AcceptedRegistry(artifact))
    published = []
    assert thermal_intel._shadow(SimpleNamespace(output=tmp_path/'output.json', publish=True),
        now, put_state=lambda item, value: published.append((item, value)),
        published_clock=lambda: now+timedelta(seconds=1)) == 0
    import json
    record = verify_capture(next(archive.glob('*/*.json.gz')))
    assert record['forecast_rows'][0]['_ventClosedFrom'] == '2026-11-01T00:00:00-06:00'
    assert len(published) == 1 and json.loads(published[0][1]) == record['output']
    monkeypatch.setattr(thermal_intel, '_VENT_CLOSED_FROM', datetime(2028, 11, 1, tzinfo=LOCAL))
    replayed = pipeline.run_shadow(registry=AcceptedRegistry(artifact), current=record['current'],
                                  forecast=record['forecast_rows'], now=now)
    assert replayed == record['output']
    assert thermal_intel._apply_vent_default(rows) == rows


def test_winter_default_retains_original_shade_search_and_forcing():
    raw = hourly(CUTOFF, mode='winter')
    for row in raw:
        if 9 <= row['at'].astimezone(LOCAL).hour < 16:
            row['radiationWm2'] = 400.
    old_grid = native(raw)
    grid = native(thermal_intel._apply_vent_default(raw))
    artifact = accepted_artifact()
    old = behavior.baseline_schedule(artifact.behavior, old_grid)
    new = behavior.baseline_schedule(artifact.behavior, grid)
    assert behavior._forcing_rows(grid, new) == behavior._forcing_rows(old_grid, old)
    assert behavior.search_candidate_schedule(behavior=artifact.behavior, dynamics=artifact.dynamics,
        forecast=grid) == behavior.search_candidate_schedule(behavior=artifact.behavior,
        dynamics=artifact.dynamics, forecast=old_grid)


def test_horizon_starting_during_last_open_window_keeps_consistent_metadata():
    grid = native(thermal_intel._apply_vent_default(hourly(CUTOFF-timedelta(minutes=30))))
    schedule = pipeline._expand_nightly_venting(behavior.baseline_schedule(accepted_artifact().behavior, grid), grid, LOCAL)
    assert schedule['ventOpenAt'] == grid[0]['at']
    assert schedule['ventCloseAt'] == CUTOFF
    assert schedule['vent'] == 'open'
    assert schedule['ventFlow'] == 'baseline'
    assert schedule['ventForcing'] == 1.
    assert schedule['airflowSegments'] == ({'startAt': grid[0]['at'], 'endAt': CUTOFF, 'level': 'baseline'},)
