"""Pure source guards for the isolated Bitcoin price Item/link rehearsal."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

spec = spec_from_file_location('bitcoin_price_provider',
    Path(__file__).with_name('qualify-bitcoin-price-provider.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_prepared_price_item_matches_live_identity_and_link():
    source = module.provider.SOURCE.read_text()
    assert module.provider.CHANNELS == {
        'BTC_USD_Price': 'exec:command:BTC_Price:output'}
    assert source.count('Number BTC_USD_Price "Bitcoin Price [%.0f USD]" (BTC_Price) '
                        '{ channel="exec:command:BTC_Price:output" }') == 1
    assert module.provider.GROUPS == {'BTC_USD_Price': ['BTC_Price']}
    assert module.provider.BINDING is None
    assert module.provider.FILE_LABELS == {'BTC_USD_Price': 'Bitcoin Price'}
    assert module.provider.FILE_PATTERNS == {'BTC_USD_Price': '%.0f USD'}
