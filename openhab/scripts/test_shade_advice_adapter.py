"""Reuse the established shade interval reader; do not invent native motion evidence."""
from datetime import timedelta
from local_measurement_test_support import NOW
from test_shade_position_observations import mapping
from household.advice.shade_state import ShadeHistory
import importlib,json


def test_joined_openhab_reports_use_original_acquisition_not_republication(tmp_path):
    adapter=importlib.import_module('household.advice.shade_adapter')
    at=NOW-timedelta(seconds=10)
    raw=json.dumps(dict(schema_version=1,source='motor_report',stale=False,reported_position=40,report_received_at=at.timestamp()))
    rows=[dict(stored_at=at,diagnostic_state=raw,availability=True,scalar_position='40'),
          dict(stored_at=NOW,diagnostic_state=raw,availability=True,scalar_position='40')]
    store=ShadeHistory(tmp_path/'shades.sqlite')
    adapter.ingest_joined_rows(store,mapping=mapping(),rows=rows,start=at,end=NOW+timedelta(seconds=1),as_of=NOW+timedelta(seconds=1))
    events=store.latest(now=NOW+timedelta(seconds=1));assert len(events)==1
    assert events[0]['position_open_pct']==60.
    assert events[0]['observed_at']==at.isoformat()
    assert events[0]['movement']=='unknown' and events[0]['origin']=='unknown'
