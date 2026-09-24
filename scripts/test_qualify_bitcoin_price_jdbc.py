"""Pure scope guards for Bitcoin price's isolated JDBC rehearsal."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('bitcoin_price_jdbc',
    Path(__file__).with_name('qualify-bitcoin-price-jdbc.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_isolated_price_fixture_uses_synthetic_numeric_and_group():
    assert module.ITEMS == {'BTC_USD_Price': '84242'}
    assert module.SOURCE.name == 'bitcoin-price.items'
    assert module.ISOLATED_GROUP[0] == 'items/bitcoin-group-test.items'
    assert module.ISOLATED_GROUP[1].startswith(b'Group BTC_Price ')


def test_numeric_state_comparison_accepts_jdbc_decimal_formatting():
    assert module.same_numeric_state('84242.0', '84242')
    assert module.same_numeric_state(84242.0, '84242')
    assert not module.same_numeric_state('84243', '84242')
    assert not module.same_numeric_state('UNDEF', '84242')
