"""Explicit original per-metric archive receipts; legacy selection unchanged."""
from datetime import timedelta
import pytest
from test_thermal_forecast_history import ORIGIN, issue, Connection
from thermal_model import forecast_history as history


def source():
    return [(issued,captured+timedelta(seconds=index%4),at,metric,value)
            for index,(issued,captured,at,metric,value) in enumerate(issue(ORIGIN-timedelta(hours=2),ORIGIN-timedelta(hours=1)))]


def test_retained_receipts_reproduce_exact_archive_selection_and_digest():
    rows=source();original=history.select_origin_forecast(rows,origin=ORIGIN,horizon_hours=1)
    retained=history.select_origin_forecast_with_receipts(rows,origin=ORIGIN,horizon_hours=1)
    assert retained['schema']=='earthship-thermal-archived-forecast/v2'
    assert retained['rows_sha256']==original['rows_sha256'] and retained['rows']==original['rows']
    assert len(retained['metric_receipts'])==12
    assert 'schema' not in original and 'metric_receipts' not in original
    assert history.verify_origin_forecast_receipts(retained)==retained


@pytest.mark.parametrize('damage',['selected_value','receipt_value','receipt_clock','receipt_missing','archive_digest'])
def test_receipt_selected_rows_and_archive_digest_cannot_diverge(damage):
    record=history.select_origin_forecast_with_receipts(source(),origin=ORIGIN,horizon_hours=1)
    if damage=='selected_value':record['rows'][0]['tempF']+=1
    elif damage=='receipt_value':record['metric_receipts'][0][4]+=1
    elif damage=='receipt_clock':record['metric_receipts'][0][1]+=timedelta(seconds=1)
    elif damage=='receipt_missing':record['metric_receipts'].pop()
    else:record['rows_sha256']='f'*64
    with pytest.raises(ValueError):history.verify_origin_forecast_receipts(record)


def test_retained_reader_keeps_original_readonly_sql_bounds_and_closure():
    connection=Connection(source())
    record=history.fetch_origin_forecast_with_receipts(lambda:connection,origin=ORIGIN,horizon_hours=1)
    assert connection.readonly and connection.closed
    assert record['schema']=='earthship-thermal-archived-forecast/v2'
    assert connection.cur.calls[-1][1][3]==ORIGIN
