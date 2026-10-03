from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

sys.path[:0] = [str(Path(__file__).resolve().parent),
               str(Path(__file__).resolve().parents[1] / 'openhab/scripts')]
from thermal_recent_cycles import compare, shifted_clock

ISSUE = datetime(2026, 10, 3, 13, 39, 5, 222543, tzinfo=timezone.utc)
TARGET = datetime(2026, 10, 3, 20, tzinfo=timezone.utc)


def receipt(at, value=70):
    return {'temperatureF': value, 'receivedAt': at - timedelta(seconds=30),
            'storedAt': at - timedelta(seconds=20), 'validUntil': at + timedelta(seconds=90),
            'streamEpoch': '864142d5-99ee-4b7a-b5fc-e6a96e7274d8', 'snapshotSha256': 'b' * 64}


def test_seven_latest_cycles_exact_issue_cutoff_and_median_not_future_outcomes():
    calls = []
    def read(targets, assessed):
        calls.append((targets, assessed))
        lag = (ISSUE.date() - targets[0].date()).days
        assert assessed == ISSUE and all(at < ISSUE for at in targets)
        return [(at, receipt(at, 70 if at.hour == ISSUE.hour else 70 + lag)) for at in targets]
    result = compare(issue=ISSUE, target=TARGET, current_f=68, grid_reader=read)
    assert result['prediction_f'] == 72 and result['status'] == 'available'
    assert result['qualified_cycles'] == 7 and result['selected_lag_days'] == list(range(1, 8))
    assert len(calls) == 7 and all(len(targets) == 2 for targets, _ in calls)
    assert compare(issue=ISSUE, target=TARGET, current_f=68, grid_reader=read) == result


def test_missing_cycles_extend_search_without_shortening_seven_cycle_requirement():
    def read(targets, assessed):
        lag = (ISSUE.date() - targets[0].date()).days
        return [(at, None if lag in (1, 3) else receipt(at)) for at in targets]
    result = compare(issue=ISSUE, target=TARGET, current_f=68, grid_reader=read)
    assert result['selected_lag_days'] == [2, 4, 5, 6, 7, 8, 9]
    assert result['exclusions'] == {'qualified_cycle_unavailable': 2}
    calls = []
    result = compare(issue=ISSUE, target=TARGET, current_f=68,
        grid_reader=lambda targets, assessed: (calls.append(targets) or [(at, None) for at in targets]))
    assert len(calls) == 31 and result['qualified_cycles'] == 0
    assert result['prediction_f'] is None and result['status'] == 'insufficient_qualified_history'


@pytest.mark.parametrize('damage', ['short', 'reordered', 'target', 'late_commit', 'expired', 'identity', 'number'])
def test_bad_grid_or_native_receipt_aborts(damage):
    def read(targets, assessed):
        rows = [(at, receipt(at)) for at in targets]
        if damage == 'short': return rows[:-1]
        if damage == 'reordered': return list(reversed(rows))
        if damage == 'target': rows[0] = (targets[0] + timedelta(seconds=1), rows[0][1])
        if damage == 'late_commit': rows[0][1]['storedAt'] = targets[0] + timedelta(seconds=1)
        if damage == 'expired': rows[0][1]['validUntil'] = targets[0]
        if damage == 'identity': rows[0][1]['snapshotSha256'] = 'bad'
        if damage == 'number': rows[0][1]['temperatureF'] = True
        return rows
    with pytest.raises(ValueError):
        compare(issue=ISSUE, target=TARGET, current_f=68, grid_reader=read)


def test_48_hour_cycle_excludes_targets_not_before_issue_and_honors_reader_span():
    target = ISSUE + timedelta(hours=48)
    calls = []
    def read(targets, assessed):
        calls.append(targets)
        assert targets[-1] < assessed and targets[-1] - targets[0] <= timedelta(days=1)
        return [(at, receipt(at)) for at in targets]
    result = compare(issue=ISSUE, target=target, current_f=68, grid_reader=read)
    assert result['selected_lag_days'] == list(range(3, 10))
    assert result['exclusions']['not_strictly_historical'] == 2
    assert len(calls) == 14 and all(len(chunk) == 1 for chunk in calls)


def test_local_clocks_across_dst_offsets_and_reject_ambiguous_or_nonexistent():
    # 01:30 on Nov 1 is ambiguous; 02:30 on March 8 does not exist in Denver.
    assert shifted_clock(datetime(2026, 11, 2, 8, 30, tzinfo=timezone.utc), 1) is None
    assert shifted_clock(datetime(2026, 3, 9, 8, 30, tzinfo=timezone.utc), 1) is None
    # Unique wall clocks are retained even when the historical UTC offset differs.
    assert shifted_clock(datetime(2026, 11, 2, 19, tzinfo=timezone.utc), 2) == datetime(2026, 10, 31, 18, tzinfo=timezone.utc)


def test_dst_elapsed_duration_mismatch_is_not_a_comparable_cycle():
    issue = datetime(2026, 11, 2, 7, tzinfo=timezone.utc)
    target = issue + timedelta(hours=6)
    result = compare(issue=issue, target=target, current_f=68,
        grid_reader=lambda targets, assessed: [(at, receipt(at)) for at in targets])
    assert result['selected_lag_days'] == list(range(2, 9))
    assert result['exclusions'] == {'elapsed_duration_mismatch': 1}


@pytest.mark.parametrize('issue,target,current', [
    (ISSUE.replace(tzinfo=None), TARGET, 68), (ISSUE, ISSUE, 68),
    (ISSUE, ISSUE + timedelta(hours=50), 68), (ISSUE, TARGET, float('nan')),
    (ISSUE, TARGET, True)])
def test_invalid_requests_rejected_before_reader(issue, target, current):
    with pytest.raises(ValueError):
        compare(issue=issue, target=target, current_f=current,
                grid_reader=lambda *_: pytest.fail('unexpected read'))


def test_extrapolated_prediction_is_withheld_not_clamped():
    result = compare(issue=ISSUE, target=TARGET, current_f=140,
        grid_reader=lambda targets, assessed: [(at, receipt(at, -40 if at.hour == ISSUE.hour else 140)) for at in targets])
    assert result['status'] == 'prediction_out_of_bounds' and result['prediction_f'] is None
