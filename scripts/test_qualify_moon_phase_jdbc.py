from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('moon_jdbc', Path(__file__).with_name('qualify-moon-phase-jdbc.py'))
q = module_from_spec(spec)
spec.loader.exec_module(q)


def test_fraction_contract_rejects_percentage_scale_and_missing_evidence():
    assert q.same_state('0.42500', '0.425', 'Number:Dimensionless')
    for value in ['42.5', '42.5 %', '0.425 1', '42.5 °F', 'NaN', 'Infinity',
                  '-0.1', '1.01', '0.426', 'NULL', 'UNDEF', None]:
        assert not q.same_state(value, '0.425', 'Number:Dimensionless')


def test_existing_scalar_and_string_comparisons_remain_unchanged():
    assert q.same_state('42.50', '42.5', 'Number')
    assert not q.same_state('NaN', 'NaN', 'Number')
    assert q.same_state('WAXING_GIBBOUS', 'WAXING_GIBBOUS', 'String')
    assert not q.same_state('Waxing gibbous', 'WAXING_GIBBOUS', 'String')


def test_reuses_one_pair_for_only_the_exact_two_items_and_isolated_group(monkeypatch):
    seen = []
    illumination = {'name': 'Moon_MoonIllumination', 'type': 'Number:Dimensionless',
                    'label': 'Moon Illumination', 'editable': True, 'category': '',
                    'tags': ['Point'], 'groupNames': ['Moon'],
                    'metadata': q.provider.SEMANTICS, 'unitSymbol': 'one'}
    monkeypatch.setattr(q.rehearsal.oh, 'get', lambda _: illumination)
    monkeypatch.setattr(q.rehearsal, 'main', lambda **kwargs: seen.append(kwargs))
    q.main()
    assert len(seen) == 1
    assert set(seen[0]['items']) == set(q.provider.READINGS)
    assert seen[0]['types'] == {'Moon_MoonPhaseName': 'String',
                               'Moon_MoonIllumination': 'Number:Dimensionless'}
    assert seen[0]['setup_sources'] == (('items/moon-group-fixture.items', b'Group Moon\n'),)


def test_changed_live_unit_refuses_before_fixture_allocation(monkeypatch):
    monkeypatch.setattr(q.rehearsal.oh, 'get', lambda _: {'unitSymbol': '%'})
    monkeypatch.setattr(q.rehearsal, 'main', lambda **_: pytest.fail('fixture allocation'))
    with pytest.raises(ValueError, match='dimensionless contract'): q.main()


def test_source_drift_refuses_before_jdbc_fixture(monkeypatch):
    def refuse(): raise ValueError('source drift')
    monkeypatch.setattr(q.provider, 'checked_source', refuse)
    monkeypatch.setattr(q.rehearsal, 'main', lambda **_: pytest.fail('fixture allocation'))
    with pytest.raises(ValueError): q.main()
