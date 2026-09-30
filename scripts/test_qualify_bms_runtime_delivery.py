"""Offline receipt/fixture source guards; no containers or production requests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('runtime_delivery',
    Path(__file__).with_name('qualify-bms-runtime-delivery.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def receipt_fixture():
    receipts = []
    ttd = {'status': 'unavailable', 'reason': 'input_unavailable'}
    ttf = deepcopy(ttd)
    for seq in range(1, 19):
        if seq == 4: ttd = {'status': 'valid', 'reason': 'ok', 'observedAt': 104, 'value': 5510}
        if 6 <= seq <= 15:
            ttd = {'status': 'valid', 'reason': 'ok', 'observedAt': 100 + seq, 'value': m.READINGS[seq - 6]}
        if seq in (5, 16, 17):
            ttf = {'status': 'valid', 'reason': 'ok', 'observedAt': 100 + seq, 'value': 0}
        if seq == 18: ttd = {'status': 'unavailable', 'reason': 'source_unavailable'}
        receipts.append({'basis': 'native_runtime_inputs_v1', 'streamEpoch': 'synthetic', 'sequence': seq,
            'recordedAt': 100 + seq,
            'fields': {'battery.ttd_min': deepcopy(ttd), 'battery.ttf_min': deepcopy(ttf)}})
    result = {'synthetic': True, 'highRateWrites': 0, 'readings': m.READINGS, 'emitted': receipts}
    rows = [{'time': 1000 + n, 'state': json.dumps(receipt)} for n, receipt in enumerate(receipts)]
    return result, rows


def test_all_persisted_observations_and_fault_barrier_qualified():
    result, rows = receipt_fixture()
    verdict = m.validate(result, rows)
    assert verdict['receipts'] == 18 and verdict['runtime_readings'] == 10
    assert verdict['physical_sources_tested'] is False and verdict['production_writes'] == 0


@pytest.mark.parametrize('kind', ['row_loss', 'duplicate_stamp', 'payload_drift', 'sequence_gap',
                                 'missing_native_sample', 'lost_unchanged_ttf', 'not_synthetic'])
def test_partial_or_relabelled_delivery_refused(kind):
    result, rows = receipt_fixture()
    if kind == 'row_loss': rows.pop()
    elif kind == 'duplicate_stamp': rows[1]['time'] = rows[0]['time']
    elif kind == 'payload_drift': rows[0]['state'] = '{}'
    elif kind == 'sequence_gap': result['emitted'][1]['sequence'] = 99
    elif kind == 'missing_native_sample':
        result['emitted'][14]['fields']['battery.ttd_min'] = deepcopy(result['emitted'][13]['fields']['battery.ttd_min'])
        rows[14]['state'] = json.dumps(result['emitted'][14])
    elif kind == 'lost_unchanged_ttf':
        result['emitted'][16]['fields']['battery.ttf_min'] = deepcopy(result['emitted'][15]['fields']['battery.ttf_min'])
        rows[16]['state'] = json.dumps(result['emitted'][16])
    else: result['synthetic'] = False
    with pytest.raises(RuntimeError): m.validate(result, rows)


def test_probe_is_pinned_and_uses_real_event_factory_and_persistence():
    source = (m.ROOT / 'openhab/rules/bms-runtime-input-evidence.js').read_text()
    script = m.probe(source)
    assert source in script and 'Factory.createStateEvent' in script
    assert 'HEX_BMS_RUNTIME_ISOLATED' in script and 'Persistence.persist' in script
    assert 'sendCommand' not in script
    with pytest.raises(RuntimeError, match='hash drift'): m.probe(source + '\nchanged')
