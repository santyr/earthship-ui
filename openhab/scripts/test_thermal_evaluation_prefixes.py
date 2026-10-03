"""Training-prefix bookkeeping must not change fitting or evaluation evidence."""

from collections import Counter
from dataclasses import replace
from datetime import timedelta

import pytest

from thermal_model import evaluation
from thermal_model.dataset import RADIATION_PROVENANCE_LABELS, ThermalDataset
from test_thermal_evaluation import STEP, fixed_model, samples_45_days


class NaivePrefixes:
    """Independent reference for the original whole-history scan per fold."""

    def __init__(self, ordered, confirmed_action_rows, radiation_provenance_by_at):
        self.ordered = ordered
        self.confirmed = confirmed_action_rows
        self.radiation = radiation_provenance_by_at

    def action_provenance(self, sample):
        label = evaluation._provenance(sample)
        return "unknown" if label == "confirmed" and sample.at not in self.confirmed else label

    def before(self, origin_at):
        train = tuple(sample for sample in self.ordered if sample.at < origin_at)
        return (
            train,
            Counter(self.action_provenance(sample) for sample in train),
            Counter(self.radiation[sample.at] for sample in train),
        )


@pytest.fixture(scope="module")
def mixed_samples():
    # Include gaps and all provenance labels, including confidence=1 rows that
    # lack authoritative confirmation. Do not equate confidence with a label.
    rows = tuple(
        replace(row, action_confidence=(1., .8, .35, .15, 0.)[index % 5])
        for index, row in enumerate(samples_45_days())
        if index not in range(17 * 288, 17 * 288 + 7)
        and index not in range(28 * 288, 28 * 288 + 19)
    )
    return ThermalDataset(
        rows, start=rows[0].at, end=rows[-1].at + STEP,
        rejected_counts={}, auxiliary_exclusion_counts={},
        confirmed_action_rows=tuple(row.at for index, row in enumerate(rows)
                                    if index % 7 == 0),
        radiation_provenance_by_at={
            row.at: RADIATION_PROVENANCE_LABELS[index % len(RADIATION_PROVENANCE_LABELS)]
            for index, row in enumerate(rows)
        },
    )


def test_prefixes_match_naive_strict_cutoffs_and_detached_counts(mixed_samples):
    ordered = tuple(mixed_samples)
    args = (ordered, frozenset(mixed_samples.confirmed_action_rows),
            mixed_samples.radiation_provenance_by_at)
    actual = evaluation._TrainingPrefixes(*args)
    reference = NaivePrefixes(*args)
    first = actual.before(ordered[0].at)
    assert first == ((), Counter(), Counter())
    saved = actual.before(ordered[288].at)
    expected_saved = reference.before(ordered[288].at)
    for cutoff in (ordered[288].at, ordered[288].at + timedelta(seconds=1),
                   ordered[17 * 288].at, ordered[28 * 288].at,
                   ordered[-1].at, ordered[-1].at + STEP):
        result = actual.before(cutoff)
        assert result == reference.before(cutoff)
        assert all(row.at < cutoff for row in result[0])
    assert saved == expected_saved  # Later folds cannot mutate earlier evidence.
    saved[1].clear()
    saved[2].clear()
    assert actual.before(ordered[-1].at + STEP) == reference.before(ordered[-1].at + STEP)


def test_prefixes_count_each_training_row_once(mixed_samples, monkeypatch):
    calls = []
    original = evaluation._provenance

    def counting_provenance(row):
        calls.append(row.at)
        return original(row)

    monkeypatch.setattr(evaluation, "_provenance", counting_provenance)
    ordered = tuple(mixed_samples)
    prefixes = evaluation._TrainingPrefixes(
        ordered, frozenset(mixed_samples.confirmed_action_rows),
        mixed_samples.radiation_provenance_by_at,
    )
    for row in ordered[::288]:
        prefixes.before(row.at)
    prefixes.before(ordered[-1].at + STEP)
    assert calls == [row.at for row in ordered]


def test_prefixes_refuse_reverse_consumption(mixed_samples):
    ordered = tuple(mixed_samples)
    prefixes = evaluation._TrainingPrefixes(
        ordered, frozenset(mixed_samples.confirmed_action_rows),
        mixed_samples.radiation_provenance_by_at,
    )
    prefixes.before(ordered[20].at)
    with pytest.raises(ValueError, match="chronological"):
        prefixes.before(ordered[19].at)


def test_unscorable_origin_does_not_consume_training_provenance(monkeypatch):
    rows = samples_45_days()[:14 * 288 + 1]

    def unexpected_provenance(row):
        raise AssertionError("unscorable origin must not consume provenance")

    monkeypatch.setattr(evaluation, "_provenance", unexpected_provenance)
    report = evaluation.walk_forward_evaluate(rows, lambda train: fixed_model())
    assert report["folds"] == []


@pytest.mark.parametrize("refuse_fit", [False, True])
def test_complete_backtest_and_every_fit_input_match_reference(
    mixed_samples, monkeypatch, refuse_fit,
):
    def run():
        inputs = []

        def fit(train):
            inputs.append(train)
            if refuse_fit and len(inputs) % 3 == 0:
                raise ValueError("reference refusal")
            return fixed_model()

        return evaluation.walk_forward_evaluate(mixed_samples, fit), inputs

    actual_report, actual_inputs = run()
    monkeypatch.setattr(evaluation, "_TrainingPrefixes", NaivePrefixes)
    expected_report, expected_inputs = run()
    assert actual_report == expected_report
    assert actual_inputs == expected_inputs
    assert actual_report["folds"]
    for train, fold in zip(actual_inputs, actual_report["folds"]):
        assert len(train) == fold["training_row_count"]
        assert sum(fold["action_provenance"]["training"].values()) == len(train)
        assert sum(fold["radiation_provenance"]["training"].values()) == len(train)
