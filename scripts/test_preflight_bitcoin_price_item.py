"""Pure exact-source and numeric guards for Bitcoin price preflight."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('bitcoin_price_preflight',
    Path(__file__).with_name('preflight-bitcoin-price-item.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_price_source_and_identity_are_pinned():
    assert module.ITEM == 'BTC_USD_Price'
    assert module.CHANNEL == 'exec:command:BTC_Price:output'
    assert module.SOURCE.read_text().count(
        'Number BTC_USD_Price "Bitcoin Price [%.0f USD]" (BTC_Price) '
        '{ channel="exec:command:BTC_Price:output" }') == 1


def test_numeric_state_guard_refuses_unknown_or_nonfinite():
    assert module.finite_number('84242')
    assert not module.finite_number('UNDEF')
    assert not module.finite_number('NaN')
    assert not module.finite_number('Infinity')
