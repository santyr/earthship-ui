from datetime import date, datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('sunset_experiment', Path(__file__).with_name('experiment-sunset-soc-drop.py'))
experiment = module_from_spec(spec); spec.loader.exec_module(experiment)


def test_sunset_selection_uses_only_original_available_same_day_context():
    sunset = datetime(2026, 9, 26, 0, 55, tzinfo=timezone.utc)
    origin = sunset+timedelta(hours=12)
    rows = [(sunset-timedelta(hours=12), sunset.isoformat()),
            (origin+timedelta(seconds=1), (sunset+timedelta(seconds=1)).isoformat())]
    assert experiment.sunset_at(rows, date(2026, 9, 25), origin) == rows[0][:1]+(sunset,)
    assert experiment.sunset_at(rows, date(2026, 9, 24), origin) is None
    with pytest.raises(ValueError): experiment.sunset_at(rows+rows, date(2026, 9, 25), origin)


def test_typed_postgresql_timestamp_preserves_offset_and_refuses_naive_value():
    sunset = datetime(2026, 9, 26, 0, 55, tzinfo=timezone.utc)
    persisted = sunset-timedelta(hours=12)
    assert experiment.sunset_at([(persisted, sunset)], date(2026, 9, 25), sunset) == (persisted, sunset)
    with pytest.raises(ValueError):
        experiment.sunset_at([(persisted, sunset.replace(tzinfo=None))], date(2026, 9, 25), sunset)


def test_counterfactual_preserves_dusk_cloud_penalty_and_rounding():
    record = {'dusk_soc_estimate_pct':78.411, 'tomorrow_cloud_drop_penalty_pct':2,
              'overnight_drop_final_pct':15.667, 'trough':63}
    assert experiment.counterfactual(record, [{'drop_pct':10}, {'drop_pct':12}, {'drop_pct':11}]) == (63, 65)
    assert record['trough'] == 63
    record['trough'] = 64
    with pytest.raises(ValueError): experiment.counterfactual(record, [{'drop_pct':11}]*3)


@pytest.mark.parametrize('drop', [-1, float('nan'), 101, True])
def test_bad_measured_drops_are_not_clamped_into_valid_training_inputs(drop):
    record = {'dusk_soc_estimate_pct':99, 'tomorrow_cloud_drop_penalty_pct':0,
              'overnight_drop_final_pct':15, 'trough':84}
    with pytest.raises(ValueError): experiment.counterfactual(record, [{'drop_pct':drop}]*3)
