#!/usr/bin/env python3
"""Score persisted shadow forecasts against qualified indoor outcomes, read-only.

Targets are the closest published hourly trajectory point within 30 minutes
of the selected issue+horizon mark. Results are overlapping observational pairs,
not independent days, causal action evidence, or a graduation decision.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_ROOT = ROOT / 'openhab/scripts'
_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument('--runtime-root', type=Path, default=DEFAULT_RUNTIME_ROOT)
_bootstrap_args, _ = _bootstrap.parse_known_args()
RUNTIME_ROOT = _bootstrap_args.runtime_root.resolve()
if (not RUNTIME_ROOT.is_dir()
        or not (RUNTIME_ROOT / 'thermal_temperature_runtime.py').is_file()
        or not (RUNTIME_ROOT / 'thermal_model/forcing_capture.py').is_file()):
    raise ValueError('complete thermal audit runtime root required')
sys.path.insert(0, str(RUNTIME_ROOT))
import openhab_sanity_check as oh  # noqa: E402
from thermal_temperature_runtime import collect  # noqa: E402
from thermal_model.temperature_history import _validate_receipt  # noqa: E402
from thermal_model.forcing_capture import (  # noqa: E402
    _canonical, _private_directory, verify_capture,
)

ITEM = 'Thermal_Model_JSON'
CONFIG = '/home/sat/.config/hex/weather-temperature-db.json'
POLICY = '/home/sat/.config/hex/weather-temperature-policy.json'
CAPTURE_ROOT = '/home/sat/.local/state/thermal-intel/forcing-captures'
SUPPORTED_HORIZONS = (1, 6, 12, 24, 48)


def capture_for_publication(publication, root=CAPTURE_ROOT):
    """Verify the exact private forcing archive for one persisted publication."""
    issued = aware(publication['generatedAt'])
    digest = sha256(_canonical(publication)).hexdigest()
    month = _private_directory(Path(root)) / issued.strftime('%Y-%m')
    try:
        _private_directory(month)
    except FileNotFoundError:
        return None
    path = month / (issued.strftime('%Y%m%dT%H%M%SZ') + '-' +
                    digest[:16] + '.json.gz')
    try:
        record = verify_capture(path)
    except FileNotFoundError:
        return None
    if record['sha256']['output'] != digest or record['output'] != publication:
        raise ValueError('forcing capture does not match persisted publication')
    return record


def aware(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware timestamp required')
    return value.astimezone(timezone.utc)


def finite_temperature(value):
    if type(value) not in (int, float) or not isfinite(value) or not -40 <= value <= 140:
        raise ValueError('finite bounded temperature required')
    return float(value)


def select_pair(row, *, now, horizon_hours=24):
    """Return a mature published pair or a reason; never use future outcomes."""
    if type(horizon_hours) is not int or horizon_hours not in SUPPORTED_HORIZONS:
        raise ValueError('supported horizon required')
    now = aware(now)
    if not isinstance(row, dict) or set(row) != {'time', 'state'} or type(row['time']) is not int:
        raise ValueError('unexpected persisted publication row')
    stored = datetime.fromtimestamp(row['time'] / 1000, timezone.utc)
    publication = json.loads(row['state'])
    issue = aware(publication['generatedAt'])
    if issue > stored or stored > now:
        raise ValueError('publication was not available at its recorded time')
    if publication['status'] != 'shadow':
        return None, 'not_shadow'
    ages = publication['provenance']['currentAgeMinutes']
    if not isinstance(ages, dict) or any(type(ages.get(name)) not in (int, float)
            or not isfinite(ages[name]) or not 0 <= ages[name] <= 5 for name in ('air', 'mass')):
        return None, 'stale_initial'
    current = finite_temperature(publication['current']['hallwayF'])
    trajectory = publication['forecast']['trajectory']
    if not isinstance(trajectory, list) or not trajectory:
        return None, 'trajectory_unavailable'
    candidates = []
    for point in trajectory:
        at = aware(point['at'])
        drift = abs((at - issue).total_seconds() - horizon_hours * 3600)
        if drift <= 1800:
            candidates.append((drift, at, point))
    if not candidates:
        return None, f'near{horizon_hours}h_target_unavailable'
    _, target, point = min(candidates, key=lambda entry: (entry[0], entry[1]))
    predicted = finite_temperature(point['hallwayF'])
    low, high = finite_temperature(point['lowF']), finite_temperature(point['highF'])
    if not low <= predicted <= high:
        raise ValueError('published prediction lies outside its interval')
    if target <= stored:
        raise ValueError('forecast target did not follow publication')
    if target > now - timedelta(minutes=5):
        return None, 'outcome_not_yet_due'
    model = publication['model']
    if aware(model['createdAt']) > issue or aware(model['trainedThrough']) > issue:
        raise ValueError('publication used a future model artifact')
    revision = model['codeRevision']
    if not isinstance(revision, str) or len(revision) < 12:
        raise ValueError('model revision missing')
    model_metadata_id = sha256(_canonical({
        'codeRevision': revision,
        'createdAt': model['createdAt'],
        'trainedThrough': model['trainedThrough'],
    })).hexdigest()
    return {'issue': issue, 'target': target, 'model_f': predicted,
            'interval_low_f': low, 'interval_high_f': high,
            'persistence_f': current, 'revision': revision,
            'model_metadata_id': model_metadata_id,
            'confidence': publication['confidence']['grade']}, None


def score(rows, *, now, outcome_reader, capture_reader=None, outdoor_reader=None,
          horizon_hours=24, include_pairs=False, target_artifact_id=None):
    if type(horizon_hours) is not int or horizon_hours not in SUPPORTED_HORIZONS:
        raise ValueError('supported horizon required')
    if outdoor_reader is not None and capture_reader is None:
        raise ValueError('outdoor diagnostic requires exact forcing capture')
    if type(include_pairs) is not bool or include_pairs and capture_reader is None:
        raise ValueError('pair diagnostics require exact forcing capture')
    if target_artifact_id is not None and (not isinstance(target_artifact_id, str)
            or len(target_artifact_id) != 64
            or any(character not in '0123456789abcdef' for character in target_artifact_id)):
        raise ValueError('full lowercase captured-artifact digest required')
    if target_artifact_id is not None and capture_reader is None:
        raise ValueError('target artifact requires exact forcing capture')
    counts = Counter()
    groups = defaultdict(list)
    weather_errors = []
    scored_windows = []
    pair_details = []
    for row in rows:
        pair, reason = select_pair(row, now=now, horizon_hours=horizon_hours)
        if reason:
            counts[reason] += 1
            continue
        capture = None
        if capture_reader is not None:
            capture = capture_reader(json.loads(row['state']))
            if capture is None:
                counts['forcing_capture_missing'] += 1
                continue
            counts['forcing_capture_verified'] += 1
        artifact_id = None
        if isinstance(capture, dict):
            digest = capture.get('sha256', {}).get('artifact')
            if (isinstance(digest, str) and len(digest) == 64
                    and all(character in '0123456789abcdef' for character in digest)):
                artifact_id = digest
        receipt = outcome_reader(pair['target'])
        if receipt is None:
            counts['qualified_outcome_unavailable'] += 1
            continue
        _validate_receipt(receipt, pair['target'])
        observed = float(receipt['temperatureF'])
        error = (pair['model_f'] - observed, pair['persistence_f'] - observed,
                 pair['interval_low_f'] <= observed <= pair['interval_high_f'],
                 pair['interval_high_f'] - pair['interval_low_f'])
        groups['overall'].append(error)
        groups['revision:' + pair['revision'][:12]].append(error)
        groups['model_metadata:' + pair['model_metadata_id']].append(error)
        if artifact_id is not None:
            groups['artifact:' + artifact_id].append(error)
        groups['issue_day:' + pair['issue'].date().isoformat()].append(error)
        scored_windows.append((pair['issue'], pair['target'], pair['revision'][:12],
                               pair['model_metadata_id'], artifact_id, error))
        detail = None
        if include_pairs:
            detail = {'issue_at': pair['issue'].isoformat(),
                      'target_at': pair['target'].isoformat(),
                      'revision': pair['revision'][:12],
                      'model_metadata_id': pair['model_metadata_id'],
                      'artifact_sha256': artifact_id,
                      'confidence': pair['confidence'],
                      'model_error_f': round(error[0], 3),
                      'persistence_error_f': round(error[1], 3),
                      'interval_covered': error[2],
                      'interval_width_f': round(error[3], 3),
                      'outdoor_forecast_error_f': None}
        if outdoor_reader is not None:
            forcing_rows = capture.get('forecast_rows')
            if not isinstance(forcing_rows, list):
                raise ValueError('forcing capture has no hourly rows')
            matching = [entry for entry in forcing_rows if isinstance(entry, dict)
                        and aware(entry.get('at')) == pair['target']]
            if len(matching) != 1:
                counts['weather_forcing_target_unavailable'] += 1
            else:
                outdoor_receipt = outdoor_reader(pair['target'])
                if outdoor_receipt is None:
                    counts['qualified_outdoor_unavailable'] += 1
                else:
                    _validate_receipt(outdoor_receipt, pair['target'])
                    forecast_outdoor = finite_temperature(matching[0].get('tempF'))
                    observed_outdoor = finite_temperature(outdoor_receipt['temperatureF'])
                    weather_error = forecast_outdoor - observed_outdoor
                    weather_errors.append((weather_error, error[0]))
                    if detail is not None:
                        detail['outdoor_forecast_error_f'] = round(weather_error, 3)
        if detail is not None:
            pair_details.append(detail)
        counts['scored'] += 1
        counts['confidence:' + str(pair['confidence'])] += 1
        if target_artifact_id is not None and artifact_id == target_artifact_id:
            counts['target_confidence:' + str(pair['confidence'])] += 1
    def non_overlapping(windows):
        """Greedily retain chronological forecast windows with no shared time."""
        selected = []
        previous_target = None
        for issue, target, revision, metadata_id, artifact_id, error in sorted(windows, key=lambda row: (row[0], row[1])):
            if previous_target is None or issue >= previous_target:
                selected.append((issue, target, revision, metadata_id, artifact_id, error))
                previous_target = target
        return selected

    selected_overall = non_overlapping(scored_windows)
    for _, _, revision, metadata_id, artifact_id, error in selected_overall:
        groups['nonoverlap:overall'].append(error)
    revisions = sorted({window[2] for window in scored_windows})
    for revision in revisions:
        for _, _, _, _, _, error in non_overlapping(
                [window for window in scored_windows if window[2] == revision]):
            groups['nonoverlap:revision:' + revision].append(error)
    metadata_ids = sorted({window[3] for window in scored_windows})
    for metadata_id in metadata_ids:
        for _, _, _, _, _, error in non_overlapping(
                [window for window in scored_windows if window[3] == metadata_id]):
            groups['nonoverlap:model_metadata:' + metadata_id].append(error)
    artifacts = sorted({window[4] for window in scored_windows if window[4] is not None})
    for artifact_id in artifacts:
        for _, _, _, _, _, error in non_overlapping(
                [window for window in scored_windows if window[4] == artifact_id]):
            groups['nonoverlap:artifact:' + artifact_id].append(error)
    def metrics(errors):
        n = len(errors)
        paired_differences = [abs(model) - abs(persistence)
                              for model, persistence, _, _ in errors]
        return {'n': n,
                'model_mae_f': round(sum(abs(x[0]) for x in errors) / n, 4),
                'persistence_mae_f': round(sum(abs(x[1]) for x in errors) / n, 4),
                'paired_mean_absolute_error_difference_f': round(
                    sum(paired_differences) / n, 4),
                'paired_model_wins': sum(value < 0 for value in paired_differences),
                'paired_ties': sum(value == 0 for value in paired_differences),
                'paired_persistence_wins': sum(value > 0 for value in paired_differences),
                'model_bias_f': round(sum(x[0] for x in errors) / n, 4),
                'persistence_bias_f': round(sum(x[1] for x in errors) / n, 4),
                'interval_coverage': round(sum(x[2] for x in errors) / n, 4),
                'mean_interval_width_f': round(sum(x[3] for x in errors) / n, 4)}
    result = {'scope': 'observational_shadow_publications_not_graduation',
            'horizon_hours': horizon_hours, 'target_artifact_id': target_artifact_id,
            'publication_rows': len(rows), 'counts': dict(sorted(counts.items())),
            'groups': {key: metrics(value) for key, value in sorted(groups.items())},
            'nonoverlap_policy': 'greedy_by_issue_time; next_issue_at_or_after_prior_target'}
    independent = groups.get('nonoverlap:overall', [])
    target_independent = groups.get('nonoverlap:artifact:' + target_artifact_id, []) \
        if target_artifact_id else []
    blockers = []
    if capture_reader is None:
        blockers.append('exact_forcing_capture_not_required_for_this_run')
    if target_artifact_id is None:
        if not independent:
            blockers.append('no_independent_qualified_operational_pairs')
        elif sum(abs(error[0]) for error in independent) >= sum(abs(error[1]) for error in independent):
            blockers.append('independent_operational_model_not_better_than_persistence')
        blockers.append('target_artifact_not_selected')
    elif not target_independent:
        blockers.append('no_independent_target_artifact_pairs')
    elif sum(abs(error[0]) for error in target_independent) >= sum(abs(error[1]) for error in target_independent):
        blockers.append('target_artifact_not_better_than_persistence')
    if (counts['target_confidence:low'] if target_artifact_id
            else counts['confidence:low']):
        blockers.append('low_confidence_shadow_publications_scored')
    # This observational scorer has no operator-confirmed action outcomes or
    # approved numerical release thresholds. A good MAE here alone is never
    # permission to change advisory authority.
    blockers.extend(('confirmed_action_outcomes_not_scored_here',
                     'approved_operational_graduation_thresholds_not_supplied'))
    result['advisory_graduation_claimed'] = False
    result['operational_readiness_blockers'] = blockers
    if include_pairs:
        selected = {(issue.isoformat(), target.isoformat(), revision, metadata_id, artifact_id)
                    for issue, target, revision, metadata_id, artifact_id, _ in selected_overall}
        for detail in pair_details:
            detail['nonoverlap_selected'] = (
                detail['issue_at'], detail['target_at'], detail['revision'],
                detail['model_metadata_id'], detail['artifact_sha256']) in selected
        result['pairs'] = sorted(pair_details, key=lambda detail: (
            detail['issue_at'], detail['target_at'], detail['revision'], detail['model_metadata_id']))
    if outdoor_reader is not None:
        n = len(weather_errors)
        result['weather'] = {'n': n}
        if n:
            result['weather'].update({
                'outdoor_forecast_mae_f': round(sum(abs(x[0]) for x in weather_errors) / n, 4),
                'outdoor_forecast_bias_f': round(sum(x[0] for x in weather_errors) / n, 4),
                'paired_indoor_model_mae_f': round(sum(abs(x[1]) for x in weather_errors) / n, 4),
            })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', default='2026-09-20T00:00:00+00:00')
    parser.add_argument('--until', default=None)
    parser.add_argument('--require-capture', action='store_true',
                        help='score only publications with an exact private forcing archive')
    parser.add_argument('--horizon-hours', type=int, choices=SUPPORTED_HORIZONS, default=24)
    parser.add_argument('--include-pairs', action='store_true',
                        help='bounded signed-error details; requires --require-capture')
    parser.add_argument('--artifact-id',
                        help='full SHA-256 digest of the captured validated artifact to assess separately')
    parser.add_argument('--runtime-root', type=Path, default=DEFAULT_RUNTIME_ROOT,
                        help='coherent thermal runtime source; use installed v4 for live v4 captures')
    args = parser.parse_args()
    if args.include_pairs and not args.require_capture:
        parser.error('--include-pairs requires --require-capture')
    if args.artifact_id and not args.require_capture:
        parser.error('--artifact-id requires --require-capture')
    now = datetime.now(timezone.utc)
    start = aware(args.since)
    end = aware(args.until) if args.until else now
    if not start < end <= now or end - start > timedelta(days=31):
        raise ValueError('bounded elapsed publication window required')
    query = urlencode({'serviceId': 'jdbc', 'starttime': start.isoformat(),
                       'endtime': end.isoformat()})
    rows = oh.get('/persistence/items/' + ITEM + '?' + query)['data']
    if len(rows) > 1000:
        raise ValueError('publication row bound exceeded')
    def qualified(stream, target):
        receipts = collect({'stream': stream, 'targets': [target], 'assessed_at': target},
                       config_path=CONFIG, policy_path=POLICY)
        if not isinstance(receipts, list) or len(receipts) != 1 or receipts[0][0] != target:
            raise ValueError('qualified outcome reader returned unexpected target')
        return receipts[0][1]
    result = score(rows, now=now,
                           outcome_reader=lambda target: qualified('indoor', target),
                           capture_reader=capture_for_publication if args.require_capture else None,
                           outdoor_reader=(lambda target: qualified('outdoor', target))
                           if args.require_capture else None,
                           horizon_hours=args.horizon_hours,
                           include_pairs=args.include_pairs,
                           target_artifact_id=args.artifact_id)
    result['verifier_runtime_root'] = str(RUNTIME_ROOT)
    result['verifier_source_sha256'] = {
        name: sha256((RUNTIME_ROOT / name).read_bytes()).hexdigest()
        for name in ('thermal_model/artifacts.py', 'thermal_model/forcing_capture.py',
                     'thermal_temperature_runtime.py')}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
