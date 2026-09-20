from datetime import timedelta
import math
import pytest
import thermal_intel
from thermal_model.dataset import build_samples
from test_thermal_dataset import START, END, fixture_series, fully_labeled_events


@pytest.mark.parametrize('invalid', ['UNDEF', 'NULL', 'bad', None, ''])
def test_jdbc_retains_timestamped_invalid_state(monkeypatch, invalid):
    invalid_at = START + timedelta(minutes=5)
    points = [(START, '72 °F'), (invalid_at, invalid), (START + timedelta(minutes=15), '73 °F')]
    monkeypatch.setattr(thermal_intel.forecast_intel, 'oh_get', lambda _: {
        'data': [{'time': at.timestamp() * 1000, 'state': value} for at, value in points]})
    result = thermal_intel._jdbc_series('temperature', START, END)
    assert len(result) == 3
    assert result[1][0] == invalid_at and math.isnan(result[1][1])
    assert result[0] == (START, 72.0) and result[2][1] == 73.0


@pytest.mark.parametrize('invalid', ['UNDEF', None, True])
def test_invalid_core_state_blocks_interpolation_until_real_recovery(invalid):
    rows = fixture_series()
    rows['mass'] = [(START, 72), (START + timedelta(minutes=5), invalid),
                    *rows['mass'][3:]]
    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    times = {sample.at for sample in samples}
    assert START + timedelta(minutes=5) not in times
    assert START + timedelta(minutes=10) not in times
    assert START + timedelta(minutes=15) in times


def test_explicit_invalid_tail_stops_hold_forward():
    rows = fixture_series()
    rows['mass'] = [(START, 72), (START + timedelta(minutes=5), 'UNDEF')]
    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    assert samples and all(sample.at == START for sample in samples)


def test_jdbc_invalid_boundary_reaches_dataset(monkeypatch):
    points = [(START, '72'), (START + timedelta(minutes=5), 'UNDEF'),
              (START + timedelta(minutes=15), '72')]
    monkeypatch.setattr(thermal_intel.forecast_intel, 'oh_get', lambda _: {
        'data': [{'time': at.timestamp() * 1000, 'state': value} for at, value in points]})
    rows = fixture_series()
    rows['mass'] = thermal_intel._jdbc_series('temperature', START, END)
    samples = build_samples(rows, fully_labeled_events(), [], START, END)
    times = {sample.at for sample in samples}
    assert START + timedelta(minutes=5) not in times
    assert START + timedelta(minutes=10) not in times
    assert START + timedelta(minutes=15) in times
