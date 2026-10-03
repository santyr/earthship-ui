from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pytest

SOURCE = Path(__file__).with_name('audit-thermal-shadow-publications.py')
SPEC = importlib.util.spec_from_file_location('thermal_publication_audit', SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
from thermal_model.forcing_capture import capture_shadow_inputs
ISSUE = datetime(2026, 9, 20, 1, 25, tzinfo=timezone.utc)
TARGET = datetime(2026, 9, 21, 1, 0, tzinfo=timezone.utc)


def test_cli_selects_explicit_coherent_runtime_without_live_queries():
    runtime = SOURCE.resolve().parents[1] / 'openhab/scripts'
    result = subprocess.run([sys.executable, str(SOURCE), '--runtime-root',
                             str(runtime), '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert '--runtime-root RUNTIME_ROOT' in result.stdout
    missing = subprocess.run([sys.executable, str(SOURCE), '--runtime-root',
                              str(runtime / 'missing'), '--help'],
                             capture_output=True, text=True)
    assert missing.returncode != 0
    assert 'runtime root required' in missing.stderr


def published():
    trajectory = [{'at': (ISSUE.replace(minute=0) + timedelta(hours=i)).isoformat(),
                   'hallwayF': 72.0, 'lowF': 69.0, 'highF': 75.0}
                  for i in range(1, 73)]
    return {'status': 'shadow', 'generatedAt': ISSUE.isoformat(),
            'provenance': {'currentAgeMinutes': {'air': 1, 'mass': 2}},
            'current': {'hallwayF': 68.0},
            'forecast': {'trajectory': trajectory},
            'model': {'codeRevision': 'a' * 40,
                      'createdAt': (ISSUE - timedelta(days=1)).isoformat(),
                      'trainedThrough': (ISSUE - timedelta(days=1)).isoformat()},
            'confidence': {'grade': 'low'}}


def row(value=None):
    return {'time': int((ISSUE + timedelta(seconds=3)).timestamp() * 1000),
            'state': json.dumps(value or published())}


def receipt(target):
    return {'temperatureF': 70, 'receivedAt': target - timedelta(seconds=30),
            'storedAt': target - timedelta(seconds=20),
            'validUntil': target + timedelta(seconds=90),
            'streamEpoch': '864142d5-99ee-4b7a-b5fc-e6a96e7274d8',
            'snapshotSha256': 'b' * 64}


def recent_grid(targets, original_issue):
    assert all(at < original_issue for at in targets)
    return [(at, {**receipt(at), 'temperatureF': 70 if index == 0 else 73})
            for index, at in enumerate(targets)]


def test_recent_cycles_require_capture_before_any_evidence_read():
    with pytest.raises(ValueError, match='recent-cycle comparator requires exact forcing capture'):
        audit.score([row()], now=TARGET + timedelta(hours=1), outcome_reader=receipt,
                    recent_cycle_reader=lambda *_: pytest.fail('unexpected read'))
    with pytest.raises(ValueError, match='recent-cycle comparator requires exact forcing capture'):
        audit.score_horizons([row()], now=TARGET + timedelta(hours=1), horizons=(6,),
            outcome_grid_reader=lambda *_: pytest.fail('unexpected read'),
            recent_cycle_reader=lambda *_: pytest.fail('unexpected read'))


def test_recent_cycles_add_matched_cohorts_without_changing_original_metrics():
    forcing = {'sha256': {'artifact': 'a' * 64}}
    options = dict(now=TARGET + timedelta(hours=1), outcome_reader=receipt,
                   capture_reader=lambda _: forcing, horizon_hours=6, include_pairs=True,
                   target_artifact_id='a' * 64)
    original = audit.score([row()], **options)
    result = audit.score([row()], recent_cycle_reader=recent_grid, **options)
    for key in original:
        if key != 'pairs': assert result[key] == original[key]
    detail = result['pairs'][0]['recent_cycle_baseline']
    assert detail['status'] == 'available' and detail['prediction_f'] == 71
    assert detail['signed_error_f'] == 1
    cohort = result['recent_cycle_baseline']['groups']['nonoverlap:artifact:' + 'a'*64]
    assert cohort['n'] == 1 and cohort['model_mae_f'] == 2
    assert cohort['persistence_mae_f'] == 2 and cohort['recent_cycle_mae_f'] == 1
    assert cohort['paired_recent_cycle_wins'] == 1
    assert result['advisory_graduation_claimed'] is False


def test_recent_cycles_missing_history_does_not_remove_valid_model_outcomes():
    result = audit.score([row()], now=TARGET + timedelta(hours=1), outcome_reader=receipt,
        capture_reader=lambda _: {'sha256': {'artifact': 'a'*64}}, horizon_hours=6,
        recent_cycle_reader=lambda targets, assessed: [(at, None) for at in targets])
    assert result['counts']['scored'] == 1 and result['groups']['overall']['n'] == 1
    assert result['recent_cycle_baseline']['counts'] == {'insufficient_qualified_history': 1}
    assert result['recent_cycle_baseline']['groups']['overall'] == {'n': 0}


def test_recent_cycle_multi_horizon_matches_individual_scores():
    options = dict(now=TARGET + timedelta(hours=1), include_pairs=True,
        capture_reader=lambda _: {'sha256': {'artifact': 'a'*64}},
        target_artifact_id='a'*64, recent_cycle_reader=recent_grid)
    result = audit.score_horizons([row()], horizons=(1, 6),
        outcome_grid_reader=lambda targets, assessed: [(at, receipt(at)) for at in targets], **options)
    for horizon in (1, 6):
        assert result['results'][str(horizon)] == audit.score([row()], horizon_hours=horizon,
                                                            outcome_reader=receipt, **options)


def test_recent_cycle_cli_caches_only_exact_original_issue_targets(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(audit.oh, 'get', lambda _: {'data': [row(), row()]})
    monkeypatch.setattr(audit, 'capture_for_publication', lambda _: {
        'sha256': {'artifact': 'a'*64},
        'forecast_rows': [dict(point, tempF=75) for point in published()['forecast']['trajectory']]})
    def collected(request, **_kwargs):
        calls.append(request)
        return [(at, receipt(at)) for at in request['targets']]
    monkeypatch.setattr(audit, 'collect', collected)
    with patch.object(sys, 'argv', ['audit', '--since', '2026-09-20T00:00:00Z',
        '--until', '2026-09-20T03:00:00Z', '--assessed-at', '2026-09-21T03:00:00Z',
        '--horizons', '1', '6', '--require-capture', '--recent-cycles']):
        audit.main()
    result = json.loads(capsys.readouterr().out)
    historical = [call for call in calls if call['assessed_at'] == ISSUE]
    assert len(historical) == 14  # Seven first-horizon pairs, seven new second-horizon targets.
    assert sum(len(call['targets']) for call in historical) == 21
    assert all(at < ISSUE for call in historical for at in call['targets'])
    assert result['recent_cycle_read_counts'] == {'batches': 14, 'targets': 21}
    assert result['results']['6']['recent_cycle_baseline']['groups']['overall']['n'] == 2


def test_recent_cycle_cli_refuses_missing_capture_option_before_live_reads(monkeypatch):
    monkeypatch.setattr(audit.oh, 'get', lambda *_: pytest.fail('unexpected REST read'))
    with patch.object(sys, 'argv', ['audit', '--recent-cycles']):
        with pytest.raises(SystemExit): audit.main()


def test_recent_cycle_cli_does_not_share_historical_receipts_across_issue_clocks(monkeypatch, capsys):
    second_issue = ISSUE + timedelta(seconds=1)
    second = published()
    second['generatedAt'] = second_issue.isoformat()
    rows = [row(), {'time': int((second_issue + timedelta(seconds=3)).timestamp()*1000),
                    'state': json.dumps(second)}]
    calls = []
    monkeypatch.setattr(audit.oh, 'get', lambda _: {'data': rows})
    monkeypatch.setattr(audit, 'capture_for_publication', lambda _: {
        'sha256': {'artifact': 'a'*64},
        'forecast_rows': [dict(point, tempF=75) for point in published()['forecast']['trajectory']]})
    def collected(request, **_kwargs):
        calls.append(request)
        return [(at, receipt(at)) for at in request['targets']]
    monkeypatch.setattr(audit, 'collect', collected)
    with patch.object(sys, 'argv', ['audit', '--since', '2026-09-20T00:00:00Z',
        '--until', '2026-09-20T03:00:00Z', '--assessed-at', '2026-09-21T03:00:00Z',
        '--horizons', '6', '--require-capture', '--recent-cycles']):
        audit.main()
    result = json.loads(capsys.readouterr().out)
    assert result['recent_cycle_read_counts'] == {'batches': 14, 'targets': 28}
    for issue in (ISSUE, second_issue):
        historical = [call for call in calls if call['assessed_at'] == issue]
        assert len(historical) == 7
        assert all(at < issue for call in historical for at in call['targets'])


def test_recent_cycle_cli_bounds_mature_pairs_before_capture_or_temperature(monkeypatch):
    rows = []
    for index in range(97):
        publication = published()
        publication['generatedAt'] = (ISSUE + timedelta(seconds=index)).isoformat()
        rows.append({'state': json.dumps(publication),
                     'time': int((ISSUE + timedelta(seconds=index+3)).timestamp()*1000)})
    monkeypatch.setattr(audit.oh, 'get', lambda _: {'data': rows})
    monkeypatch.setattr(audit, 'collect', lambda *_args, **_kw: pytest.fail('unexpected temperature read'))
    monkeypatch.setattr(audit, 'capture_for_publication', lambda *_: pytest.fail('unexpected capture read'))
    with patch.object(sys, 'argv', ['audit', '--since', '2026-09-20T00:00:00Z',
        '--until', '2026-09-20T03:00:00Z', '--assessed-at', '2026-09-21T03:00:00Z',
        '--horizon-hours', '6', '--require-capture', '--recent-cycles']):
        with pytest.raises(ValueError, match='exceeds 96 mature pairs'): audit.main()


def test_multi_horizon_preserves_each_original_score_with_shared_reads():
    now = TARGET + timedelta(days=3)
    rows = [row(), row()]
    captures = []
    reads = []
    forcing = {'forecast_rows': published()['forecast']['trajectory'],
               'sha256': {'artifact': 'a' * 64}}
    forcing = {**forcing, 'forecast_rows': [dict(point, tempF=75)
                                           for point in forcing['forecast_rows']]}
    def captured(publication):
        captures.append(publication)
        return forcing
    def grid(stream):
        def read(targets, assessed_at):
            reads.append((stream, targets, assessed_at))
            return [(target, receipt(target)) for target in targets]
        return read
    result = audit.score_horizons(rows, now=now, horizons=(1, 6, 12),
        outcome_grid_reader=grid('indoor'), outdoor_grid_reader=grid('outdoor'),
        capture_reader=captured, include_pairs=True, target_artifact_id='a' * 64)
    assert len(captures) == 1
    assert len(reads) == 2
    assert all(call[2] == now for call in reads)
    assert result['read_counts'] == {'indoor_batches': 1, 'outdoor_batches': 1,
        'indoor_targets': 3, 'outdoor_targets': 3, 'capture_verifications': 1}
    for horizon in (1, 6, 12):
        expected = audit.score(rows, now=now, horizon_hours=horizon,
            outcome_reader=receipt, outdoor_reader=receipt,
            capture_reader=lambda _: forcing, include_pairs=True,
            target_artifact_id='a' * 64)
        assert result['results'][str(horizon)] == expected


def test_multi_horizon_never_reads_future_missing_capture_or_unqualified_indoor():
    future_now = ISSUE + timedelta(minutes=10)
    def forbidden(*args):
        raise AssertionError('unexpected evidence read')
    result = audit.score_horizons([row()], now=future_now, horizons=(1, 24),
        outcome_grid_reader=forbidden, capture_reader=forbidden,
        outdoor_grid_reader=forbidden)
    assert result['read_counts']['indoor_batches'] == 0
    assert result['read_counts']['capture_verifications'] == 0
    result = audit.score_horizons([row()], now=TARGET + timedelta(minutes=10),
        horizons=(24,), outcome_grid_reader=forbidden,
        capture_reader=lambda _: None, outdoor_grid_reader=forbidden)
    assert result['results']['24']['counts'] == {'forcing_capture_missing': 1}
    result = audit.score_horizons([row()], now=TARGET + timedelta(minutes=10),
        horizons=(24,), outcome_grid_reader=lambda targets, now: [(t, None) for t in targets],
        capture_reader=lambda _: {'forecast_rows': [{'at': TARGET.isoformat(), 'tempF': 75}]},
        outdoor_grid_reader=forbidden)
    assert result['read_counts']['outdoor_batches'] == 0
    assert result['results']['24']['counts']['qualified_outcome_unavailable'] == 1


@pytest.mark.parametrize('horizons', [(), (1, 1), (3,), (True,), (1.0,), '1', None])
def test_multi_horizon_rejects_invalid_horizons_before_evidence(horizons):
    with pytest.raises(ValueError, match='unique supported horizons'):
        audit.score_horizons([row()], now=TARGET, horizons=horizons,
                             outcome_grid_reader=lambda *args: pytest.fail('read'))


@pytest.mark.parametrize('bad', ['short', 'reordered', 'wrong_target', 'invalid_receipt'])
def test_multi_horizon_refuses_incomplete_or_changed_grid(bad):
    def read(targets, assessed_at):
        values = [(t, receipt(t)) for t in targets]
        if bad == 'short': return values[:-1]
        if bad == 'reordered': return list(reversed(values))
        if bad == 'wrong_target': return [(t + timedelta(seconds=1), value) for t, value in values]
        return [(t, {**value, 'storedAt': t + timedelta(seconds=1)}) for t, value in values]
    with pytest.raises(ValueError):
        audit.score_horizons([row()], now=TARGET + timedelta(days=1), horizons=(1, 6),
                             outcome_grid_reader=read)


def test_multi_horizon_batches_at_existing_day_and_target_bounds():
    now = TARGET + timedelta(days=32)
    rows = []
    for day in range(3):
        value = published()
        delta = timedelta(days=day)
        value['generatedAt'] = (ISSUE + delta).isoformat()
        for point in value['forecast']['trajectory']:
            point['at'] = (datetime.fromisoformat(point['at']) + delta).isoformat()
        rows.append({'time': int((ISSUE+delta+timedelta(seconds=3)).timestamp()*1000),
                     'state': json.dumps(value)})
    calls = []
    def read(targets, assessed_at):
        calls.append(targets)
        return [(t, receipt(t)) for t in targets]
    result = audit.score_horizons(rows, now=now, horizons=(1, 6, 12, 24, 48),
                                 outcome_grid_reader=read)
    assert len(calls) > 1
    assert all(len(targets) <= 289 and targets[-1]-targets[0] <= timedelta(days=1)
               for targets in calls)
    assert all(a < b for targets in calls for a, b in zip(targets, targets[1:]))
    assert result['read_counts']['indoor_targets'] == len({t for targets in calls for t in targets})
    for horizon in (1, 6, 12, 24, 48):
        assert result['results'][str(horizon)] == audit.score(
            rows, now=now, horizon_hours=horizon, outcome_reader=receipt)


def test_multi_horizon_enforces_289_target_limit_and_publication_bound():
    rows = []
    for index in range(350):
        value = published()
        delta = timedelta(seconds=30*index)
        value['generatedAt'] = (ISSUE+delta).isoformat()
        for point in value['forecast']['trajectory']:
            point['at'] = (datetime.fromisoformat(point['at'])+delta).isoformat()
        rows.append({'time': int((ISSUE+delta+timedelta(seconds=3)).timestamp()*1000),
                     'state': json.dumps(value)})
    sizes = []
    def read(targets, assessed_at):
        sizes.append(len(targets))
        return [(t, receipt(t)) for t in targets]
    result = audit.score_horizons(rows, now=TARGET+timedelta(days=1), horizons=(24,),
                                 outcome_grid_reader=read)
    assert sizes == [289, 61]
    assert result['results']['24']['counts']['scored'] == 350
    with pytest.raises(ValueError, match='bounded publication rows'):
        audit.score_horizons([row()]*1001, now=TARGET, horizons=(24,),
                             outcome_grid_reader=lambda *args: pytest.fail('read'))


@pytest.mark.parametrize('options', [
    {'include_pairs': True}, {'target_artifact_id': 'a'*64},
    {'target_artifact_id': 'a'*12, 'capture_reader': lambda _: None},
    {'outdoor_grid_reader': lambda *args: pytest.fail('read')},
])
def test_multi_horizon_validates_options_before_any_capture_or_grid(options):
    with pytest.raises(ValueError):
        audit.score_horizons([row()], now=TARGET, horizons=(24,),
                             outcome_grid_reader=lambda *args: pytest.fail('read'), **options)


def test_multi_horizon_missing_outdoor_receipts_preserve_indoor_score():
    forcing = {'forecast_rows': [{'at': TARGET.isoformat(), 'tempF': 75}]}
    result = audit.score_horizons([row()], now=TARGET+timedelta(minutes=10), horizons=(24,),
        outcome_grid_reader=lambda targets, now: [(t, receipt(t)) for t in targets],
        outdoor_grid_reader=lambda targets, now: [(t, None) for t in targets],
        capture_reader=lambda _: forcing)
    assert result['results']['24'] == audit.score([row()], now=TARGET+timedelta(minutes=10),
        outcome_reader=receipt, outdoor_reader=lambda _: None, capture_reader=lambda _: forcing)


def test_multi_horizon_legacy_cli_result_and_explicit_batch_cli(monkeypatch, capsys):
    monkeypatch.setattr(audit.oh, 'get', lambda _: {'data': [row()]})
    calls = []
    def collect(request, **kwargs):
        calls.append(request)
        return [(target, receipt(target)) for target in request['targets']]
    monkeypatch.setattr(audit, 'collect', collect)
    with patch.object(sys, 'argv', ['audit', '--since', '2026-09-20T00:00:00Z',
                                  '--until', '2026-09-20T03:00:00Z', '--horizon-hours', '1']):
        audit.main()
    legacy = json.loads(capsys.readouterr().out)
    assert legacy['horizon_hours'] == 1 and 'results' not in legacy
    calls.clear()
    with patch.object(sys, 'argv', ['audit', '--since', '2026-09-20T00:00:00Z',
                                  '--until', '2026-09-20T03:00:00Z', '--horizons', '1', '6']):
        audit.main()
    multi = json.loads(capsys.readouterr().out)
    assert set(multi['results']) == {'1', '6'}
    assert len(calls) == 1
    assert multi['results']['1']['groups'] == legacy['groups']
    assert multi['results']['1']['operational_readiness_blockers'] == legacy['operational_readiness_blockers']


def test_fixed_assessment_reproduces_scores_and_bounds_all_reads(monkeypatch, capsys):
    assessed = ISSUE.replace(hour=8, minute=0)
    queries, reads = [], []
    def get(query):
        queries.append(query)
        return {'data': [row()]}
    def collect(request, **kwargs):
        reads.append(request)
        return [(target, receipt(target)) for target in request['targets']]
    monkeypatch.setattr(audit.oh, 'get', get)
    monkeypatch.setattr(audit, 'collect', collect)
    argv = ['audit', '--since', '2026-09-20T00:00:00Z', '--horizons', '1', '6',
            '--assessed-at', assessed.isoformat()]
    with patch.object(sys, 'argv', argv):
        audit.main()
    first = json.loads(capsys.readouterr().out)
    with patch.object(sys, 'argv', argv):
        audit.main()
    assert json.loads(capsys.readouterr().out) == first
    assert first['assessed_at'] == assessed.isoformat()
    assert all(request['assessed_at'] == assessed for request in reads)
    from urllib.parse import parse_qs, urlsplit
    assert all(parse_qs(urlsplit(query).query)['endtime'] == [assessed.isoformat()] for query in queries)


@pytest.mark.parametrize('assessed,until', [
    ('2099-01-01T00:00:00Z', None),
    ('2026-09-20T08:00:00', None),
    ('2026-09-20T08:00:00Z', '2026-09-20T09:00:00Z'),
    ('2026-09-20T00:00:00Z', None),
])
def test_invalid_assessment_refuses_before_any_external_read(monkeypatch, assessed, until):
    calls = []
    monkeypatch.setattr(audit.oh, 'get', lambda request: calls.append(request))
    monkeypatch.setattr(audit, 'collect', lambda *args, **kwargs: calls.append(args))
    argv = ['audit', '--since', '2026-09-20T00:00:00Z', '--assessed-at', assessed]
    if until:
        argv += ['--until', until]
    with patch.object(sys, 'argv', argv), pytest.raises(ValueError):
        audit.main()
    assert calls == []


def test_fixed_assessment_does_not_mature_a_future_outcome(monkeypatch, capsys):
    monkeypatch.setattr(audit.oh, 'get', lambda _: {'data': [row()]})
    reads = []
    monkeypatch.setattr(audit, 'collect', lambda *args, **kwargs: reads.append(args))
    with patch.object(sys, 'argv', ['audit', '--since', '2026-09-20T00:00:00Z',
            '--assessed-at', '2026-09-20T03:00:00Z', '--horizons', '6', '24']):
        audit.main()
    result = json.loads(capsys.readouterr().out)
    assert reads == []
    assert all(value['counts'] == {'outcome_not_yet_due': 1} for value in result['results'].values())
    assert all(value['groups'] == {} for value in result['results'].values())


class PublicationAuditTests(unittest.TestCase):
    def test_nonoverlapping_group_excludes_shared_forecast_windows(self):
        def shifted(hours):
            value = published()
            shift = timedelta(hours=hours)
            value['generatedAt'] = (ISSUE + shift).isoformat()
            for point in value['forecast']['trajectory']:
                point['at'] = (datetime.fromisoformat(point['at']) + shift).isoformat()
            return {'time': int((ISSUE + shift + timedelta(seconds=3)).timestamp() * 1000),
                    'state': json.dumps(value)}

        result = audit.score([shifted(0), shifted(12), shifted(24)],
                             now=TARGET + timedelta(days=3),
                             outcome_reader=receipt)
        self.assertEqual(result['groups']['overall']['n'], 3)
        self.assertEqual(result['groups']['nonoverlap:overall']['n'], 2)
        self.assertEqual(result['groups']['nonoverlap:revision:' + 'a' * 12]['n'], 2)
        self.assertEqual(len([key for key in result['groups']
                              if key.startswith('nonoverlap:model_metadata:')]), 1)
        self.assertEqual(result['nonoverlap_policy'],
                         'greedy_by_issue_time; next_issue_at_or_after_prior_target')
        self.assertFalse(result['advisory_graduation_claimed'])
        self.assertIn('exact_forcing_capture_not_required_for_this_run',
                      result['operational_readiness_blockers'])
        self.assertIn('target_artifact_not_selected', result['operational_readiness_blockers'])
        details = audit.score([shifted(0), shifted(12), shifted(24)],
                              now=TARGET + timedelta(days=3),
                              outcome_reader=receipt,
                              capture_reader=lambda _: {'forecast_rows': []},
                              include_pairs=True)['pairs']
        self.assertEqual([item['nonoverlap_selected'] for item in details],
                         [True, False, True])

    def test_paired_published_baseline_and_qualified_outcome(self):
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['groups']['overall']['model_mae_f'], 2.0)
        self.assertEqual(result['groups']['overall']['persistence_mae_f'], 2.0)
        self.assertEqual(result['groups']['overall']['paired_model_wins'], 0)
        self.assertEqual(result['groups']['overall']['paired_ties'], 1)
        self.assertEqual(result['groups']['overall']['paired_persistence_wins'], 0)
        self.assertEqual(result['groups']['overall']['interval_coverage'], 1.0)
        self.assertNotIn('target_confidence:low', result['counts'])
        self.assertIn('independent_operational_model_not_better_than_persistence',
                      result['operational_readiness_blockers'])
        self.assertIn('low_confidence_shadow_publications_scored',
                      result['operational_readiness_blockers'])
        self.assertNotIn('pairs', result)

    def test_better_captured_forecast_still_cannot_graduate_from_this_score(self):
        forecast = published()
        for point in forecast['forecast']['trajectory']:
            point['hallwayF'] = 70.0
        result = audit.score([row(forecast)], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt,
                             capture_reader=lambda _: {'forecast_rows': []})
        self.assertEqual(result['groups']['nonoverlap:overall']['model_mae_f'], 0.0)
        self.assertNotIn('independent_operational_model_not_better_than_persistence',
                         result['operational_readiness_blockers'])
        self.assertEqual(result['operational_readiness_blockers'][-2:], [
            'confirmed_action_outcomes_not_scored_here',
            'approved_operational_graduation_thresholds_not_supplied'])
        self.assertFalse(result['advisory_graduation_claimed'])

    def test_skill_blocker_uses_unrounded_paired_errors(self):
        forecast = published()
        for point in forecast['forecast']['trajectory']:
            point['hallwayF'] = 68.00001
            point['lowF'] = 67.0
        result = audit.score([row(forecast)], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt,
                             capture_reader=lambda _: {'forecast_rows': []})
        self.assertEqual(result['groups']['nonoverlap:overall']['model_mae_f'], 2.0)
        self.assertEqual(result['groups']['nonoverlap:overall']['persistence_mae_f'], 2.0)
        self.assertNotIn('independent_operational_model_not_better_than_persistence',
                         result['operational_readiness_blockers'])

    def test_future_target_and_stale_initial_are_excluded(self):
        pair, reason = audit.select_pair(row(), now=TARGET + timedelta(minutes=1))
        self.assertIsNone(pair)
        self.assertEqual(reason, 'outcome_not_yet_due')
        stale = published(); stale['provenance']['currentAgeMinutes']['air'] = 6
        self.assertEqual(audit.select_pair(row(stale), now=TARGET + timedelta(minutes=10))[1],
                         'stale_initial')

    def test_short_horizon_uses_its_own_mature_target(self):
        short_target = datetime(2026, 9, 20, 2, tzinfo=timezone.utc)
        pair, reason = audit.select_pair(row(), now=short_target + timedelta(minutes=6),
                                         horizon_hours=1)
        self.assertIsNone(reason)
        self.assertEqual(pair['target'], short_target)
        self.assertEqual(audit.select_pair(row(), now=short_target + timedelta(minutes=1),
                                           horizon_hours=1)[1], 'outcome_not_yet_due')
        scored = audit.score([row()], now=short_target + timedelta(minutes=6),
                             outcome_reader=receipt, horizon_hours=1)
        self.assertEqual(scored['horizon_hours'], 1)
        self.assertEqual(scored['counts']['scored'], 1)

    def test_unsupported_horizon_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'supported horizon'):
            audit.select_pair(row(), now=TARGET + timedelta(minutes=10), horizon_hours=3)

    def test_exact_captured_weather_is_compared_with_qualified_outdoor(self):
        captured = {'forecast_rows': [{'at': TARGET.isoformat(), 'tempF': 75.0}]}
        outdoor = lambda target: {**receipt(target), 'temperatureF': 72.0}
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt, capture_reader=lambda _: captured,
                             outdoor_reader=outdoor, include_pairs=True)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['weather']['n'], 1)
        self.assertEqual(result['weather']['outdoor_forecast_mae_f'], 3.0)
        self.assertEqual(result['weather']['paired_indoor_model_mae_f'], 2.0)
        self.assertEqual(result['pairs'], [{
            'issue_at': ISSUE.isoformat(), 'target_at': TARGET.isoformat(),
            'revision': 'a'*12,
            'model_metadata_id': result['pairs'][0]['model_metadata_id'],
            'artifact_sha256': None,
            'confidence': 'low', 'model_error_f': 2.0,
            'persistence_error_f': -2.0, 'interval_covered': True,
            'interval_width_f': 6.0, 'outdoor_forecast_error_f': 3.0,
            'nonoverlap_selected': True,
        }])

    def test_same_code_revision_different_artifacts_do_not_share_target_skill(self):
        first = published()
        later = published()
        shift = timedelta(hours=24)
        later['generatedAt'] = (ISSUE + shift).isoformat()
        later['model']['createdAt'] = (ISSUE + shift - timedelta(hours=1)).isoformat()
        later['model']['trainedThrough'] = later['model']['createdAt']
        later['confidence']['grade'] = 'high'
        for point in later['forecast']['trajectory']:
            point['at'] = (datetime.fromisoformat(point['at']) + shift).isoformat()
            point['hallwayF'] = 70.0
        rows = [row(first), {'time': int((ISSUE + shift + timedelta(seconds=3)).timestamp()*1000),
                             'state': json.dumps(later)}]
        first_metadata = audit.select_pair(rows[0], now=TARGET + timedelta(days=3))[0]['model_metadata_id']
        second_metadata = audit.select_pair(rows[1], now=TARGET + timedelta(days=3))[0]['model_metadata_id']
        self.assertNotEqual(first_metadata, second_metadata)
        first_id, second_id = '1'*64, '2'*64
        def captured(publication):
            digest = first_id if publication['model']['createdAt'] == first['model']['createdAt'] else second_id
            return {'forecast_rows': [], 'sha256': {'artifact': digest}}
        result = audit.score(rows, now=TARGET + timedelta(days=3), outcome_reader=receipt,
                             capture_reader=captured,
                             target_artifact_id=first_id)
        self.assertEqual(result['groups']['nonoverlap:revision:' + 'a'*12]['n'], 2)
        self.assertEqual(result['groups']['nonoverlap:artifact:' + first_id]['n'], 1)
        self.assertEqual(result['groups']['nonoverlap:artifact:' + second_id]['n'], 1)
        self.assertEqual(result['counts']['target_confidence:low'], 1)
        self.assertNotIn('target_confidence:high', result['counts'])
        self.assertEqual(result['groups']['nonoverlap:revision:' + 'a'*12]['paired_model_wins'], 1)
        self.assertEqual(result['groups']['nonoverlap:revision:' + 'a'*12]['paired_ties'], 1)
        self.assertIn('target_artifact_not_better_than_persistence',
                      result['operational_readiness_blockers'])
        self.assertNotIn('target_artifact_not_selected', result['operational_readiness_blockers'])
        better = audit.score(rows, now=TARGET + timedelta(days=3), outcome_reader=receipt,
                             capture_reader=captured,
                             target_artifact_id=second_id)
        self.assertEqual(better['counts']['target_confidence:high'], 1)
        self.assertNotIn('target_confidence:low', better['counts'])
        self.assertNotIn('target_artifact_not_better_than_persistence',
                         better['operational_readiness_blockers'])
        self.assertNotIn('low_confidence_shadow_publications_scored',
                         better['operational_readiness_blockers'])

    def test_target_artifact_must_have_mature_paired_evidence(self):
        missing_id = 'f' * 64
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt,
                             capture_reader=lambda _: {'forecast_rows': []},
                             target_artifact_id=missing_id)
        self.assertIn('no_independent_target_artifact_pairs',
                      result['operational_readiness_blockers'])
        with self.assertRaisesRegex(ValueError, 'requires exact forcing capture'):
            audit.score([row()], now=TARGET + timedelta(minutes=10),
                        outcome_reader=receipt, target_artifact_id=missing_id)
        with self.assertRaisesRegex(ValueError, 'full lowercase captured-artifact digest'):
            audit.score([row()], now=TARGET + timedelta(minutes=10),
                        outcome_reader=receipt, target_artifact_id='a' * 12)

    def test_pair_details_require_exact_capture(self):
        with self.assertRaisesRegex(ValueError, 'require exact forcing capture'):
            audit.score([row()], now=TARGET + timedelta(minutes=10),
                        outcome_reader=receipt, include_pairs=True)

    def test_missing_outdoor_target_does_not_invalidate_indoor_score(self):
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt,
                             capture_reader=lambda _: {'forecast_rows': []},
                             outdoor_reader=receipt)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['counts']['weather_forcing_target_unavailable'], 1)
        self.assertEqual(result['weather']['n'], 0)

    def test_unqualified_outdoor_does_not_invalidate_indoor_score(self):
        captured = {'forecast_rows': [{'at': TARGET.isoformat(), 'tempF': 75.0}]}
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=receipt, capture_reader=lambda _: captured,
                             outdoor_reader=lambda _: None)
        self.assertEqual(result['counts']['scored'], 1)
        self.assertEqual(result['counts']['qualified_outdoor_unavailable'], 1)
        self.assertEqual(result['weather']['n'], 0)

    def test_postdated_issue_is_refused(self):
        invalid = published(); invalid['generatedAt'] = (ISSUE + timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError, 'not available'):
            audit.select_pair(row(invalid), now=TARGET + timedelta(minutes=10))

    def test_missing_outcome_never_counts_as_zero_error(self):
        result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                             outcome_reader=lambda _: None)
        self.assertEqual(result['counts'], {'qualified_outcome_unavailable': 1})
        self.assertEqual(result['groups'], {})
        self.assertIn('no_independent_qualified_operational_pairs',
                      result['operational_readiness_blockers'])

    def test_capture_required_excludes_missing_and_verifies_exact_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            reader = lambda value: audit.capture_for_publication(value, directory)
            result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                                 outcome_reader=receipt, capture_reader=reader)
            self.assertEqual(result['counts'], {'forcing_capture_missing': 1})
            self.assertEqual(result['groups'], {})
            capture_shadow_inputs(
                directory, output=published(), snapshot={'hourly': {'time': []}},
                rows=[], current={}, inputs_available_at=ISSUE,
                published_at=ISSUE + timedelta(seconds=2),
            )
            result = audit.score([row()], now=TARGET + timedelta(minutes=10),
                                 outcome_reader=receipt, capture_reader=reader)
            self.assertEqual(result['counts']['forcing_capture_verified'], 1)
            self.assertEqual(result['counts']['scored'], 1)
            self.assertEqual(result['groups']['overall']['model_mae_f'], 2.0)
            self.assertNotIn('exact_forcing_capture_not_required_for_this_run',
                             result['operational_readiness_blockers'])
            self.assertIn('approved_operational_graduation_thresholds_not_supplied',
                          result['operational_readiness_blockers'])

    def test_capture_identity_cannot_match_changed_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            capture_shadow_inputs(
                directory, output=published(), snapshot={}, rows=[], current={},
                inputs_available_at=ISSUE, published_at=ISSUE + timedelta(seconds=2),
            )
            changed = published()
            changed['current']['hallwayF'] = 69.0
            self.assertIsNone(audit.capture_for_publication(changed, directory))


if __name__ == '__main__':
    unittest.main()
