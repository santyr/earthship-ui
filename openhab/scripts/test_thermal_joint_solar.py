"""Versioned four-regime solar identification; synthetic, never live labels."""
from dataclasses import replace
from datetime import datetime, timezone

import numpy as np
import pytest

from thermal_model.airflow import fit_airflow_seed, fit_airflow_seed_with_evidence, predict_airflow_step
from thermal_model.dynamics import _fit, _solar_terms as legacy_terms
from thermal_model.joint_solar import SOLAR_NAMES, solar_terms
from test_thermal_airflow import forcing, make_synthetic_samples, seed

NOON = datetime(2026, 8, 13, 18, tzinfo=timezone.utc)


@pytest.mark.parametrize('indoor,outdoor,index', [(0., 0., 0), (1., 0., 1), (0., 1., 2), (1., 1., 3)])
def test_each_binary_shade_state_has_one_independent_solar_regime(indoor, outdoor, index):
    terms = solar_terms(forcing(at=NOON, radiation_wm2=500.,
        indoor_shade_closed=indoor, outdoor_shade_present=outdoor))
    assert terms[index] > 0
    assert sum(terms) == terms[index]
    assert all(value == 0 for i, value in enumerate(terms) if i != index)


@pytest.mark.parametrize('shade', ['indoor_shade_closed', 'outdoor_shade_present'])
@pytest.mark.parametrize('value', [None, True, float('nan'), -0.1, 1.1])
def test_unknown_or_invalid_shade_fraction_is_not_a_closed_or_open_state(shade, value):
    with pytest.raises(ValueError, match='shade fractions'):
        solar_terms(forcing(at=NOON, radiation_wm2=500., **{shade: value}))


@pytest.mark.parametrize('reverse_single_gains', [False, True])
def test_partial_positions_are_monotone_without_ranking_single_shades(reverse_single_gains):
    model = seed()
    if reverse_single_gains:
        def swap(coefficients):
            return {**coefficients, 'solar_indoor_closed': coefficients['solar_outdoor'],
                    'solar_outdoor': coefficients['solar_indoor_closed']}
        model = replace(model, air_coefficients=swap(model.air_coefficients),
                        mass_coefficients=swap(model.mass_coefficients))
    fractions = np.linspace(0, 1, 5)
    for indoor in fractions:
        for outdoor in fractions:
            row = forcing(at=NOON, radiation_wm2=500., indoor_shade_closed=float(indoor),
                          outdoor_shade_present=float(outdoor))
            assert sum(solar_terms(row)) == pytest.approx(sum(solar_terms(forcing(at=NOON, radiation_wm2=500.))))
            here = predict_airflow_step(model, row)
            for field in ('indoor_shade_closed', 'outdoor_shade_present'):
                if row[field] < 1:
                    more_closed = predict_airflow_step(model, {**row, field: row[field]+.25})
                    assert more_closed[0] <= here[0]
                    assert more_closed[1] <= here[1]


def test_constrained_fit_does_not_choose_an_overheating_combined_shade_gain():
    coefficients = _fit(np.eye(4), [.010, .003, .001, .006],
        ([0.]*4, [.02]*4), SOLAR_NAMES, ordered_solar=True)
    assert coefficients['solar_both_closed'] <= min(coefficients[name]
        for name in ('solar_indoor_closed', 'solar_outdoor'))


def test_joint_gain_cannot_be_identified_from_combined_only_shade_labels():
    with pytest.raises(ValueError, match='independently identified single-shade'):
        fit_airflow_seed_with_evidence(make_synthetic_samples(paired_shades=True),
                                      allow_inactive_action_forcing=True)


def test_air_mass_and_glazing_recover_all_four_identified_regimes():
    glazing = {'intercept': 20., 'air': .5, 'outdoor': .2,
        'solar_unshaded': .001, 'solar_indoor_closed': .0005,
        'solar_outdoor': .0004, 'solar_both_closed': .0002}
    model = replace(seed(), glazing_observation_coefficients=glazing)
    fitted = fit_airflow_seed(make_synthetic_samples(model=model))
    assert fitted.glazing_observation_coefficients == pytest.approx(glazing, abs=1e-8)


def test_legacy_three_regime_semantics_are_not_reinterpreted():
    row = forcing(at=NOON, radiation_wm2=500., indoor_shade_closed=1., outdoor_shade_present=1.)
    assert len(legacy_terms(row)) == 3 and legacy_terms(row)[1] > 0
    assert len(solar_terms(row)) == 4 and solar_terms(row)[1] == 0 and solar_terms(row)[3] > 0
