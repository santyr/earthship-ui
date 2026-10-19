"""Exact source and release guards for tomorrow's forecast values."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'forecast_tomorrow_migration', ROOT / 'scripts/migrate-forecast-tomorrow-items.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_staged_source_exactly_matches_batch_without_links():
    source = migration.migration.SOURCE.read_text()
    for name in migration.migration.NAMES:
        assert source.count('Number ' + name + ' ') == 1
    assert source.count('\nNumber ') == len(migration.migration.NAMES)
    assert source.count('["forecast-intel"]') == len(migration.migration.NAMES)
    assert 'channel=' not in source


def test_old_cutover_cannot_apply_changed_unqualified_source():
    assert migration.RELEASE_READY is False
    assert migration.migration.ITEM_TYPE == 'Number'
    assert migration.migration.TIMER == 'forecast-intel.timer'


def test_prepared_tomorrow_batch_has_no_unsupported_probability():
    import json
    assert set(migration.migration.NAMES) == {'Forecast_Tomorrow_High', 'Forecast_Tomorrow_Low'}
    resources=json.loads((ROOT/'openhab/file-config/ownership.json').read_text())['resources']
    items={row['id']:row for row in resources if row['kind']=='item'}
    assert 'Forecast_Tomorrow_PrecipProb' not in items
    for name in migration.migration.NAMES:
        assert items[name]['migration']=='prepared'
        assert items[name]['state_writer']=='weathernext-publish.service'


def test_jdbc_adapter_does_not_index_the_removed_third_item():
    # Execute argument construction only. No JDBC, containers or recovery run.
    import runpy
    from types import SimpleNamespace
    from unittest.mock import patch
    calls=[]
    adapter=SimpleNamespace(main=lambda **kwargs:calls.append(kwargs))
    def selected_spec(name,path):
        module=adapter if Path(path).name=='qualify-forecast-json-jdbc.py' else migration
        return SimpleNamespace(module=module,loader=SimpleNamespace(exec_module=lambda value:None))
    with patch('importlib.util.spec_from_file_location',side_effect=selected_spec),patch('importlib.util.module_from_spec',side_effect=lambda spec:spec.module):
        runpy.run_path(str(ROOT/'scripts/qualify-forecast-tomorrow-jdbc.py'),run_name='__main__')
    assert len(calls)==1
    assert calls[0]['items']=={'Forecast_Tomorrow_High':'72.7','Forecast_Tomorrow_Low':'43.9'}


def test_all_retained_forecast_owners_name_the_prepared_google_worker():
    import json
    from weather_learning.production_runtime import ITEM_TYPES
    resources=json.loads((ROOT/'openhab/file-config/ownership.json').read_text())['resources']
    items={row['id']:row for row in resources if row['kind']=='item'}
    assert all(items[name]['migration']=='prepared' and
               items[name]['state_writer']=='weathernext-publish.service' for name in ITEM_TYPES)
