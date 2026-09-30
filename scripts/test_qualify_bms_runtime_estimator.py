import importlib.util
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    'bms_estimator_qualification', Path(__file__).with_name('qualify-bms-runtime-estimator.py'))
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


def test_clone_policy_requires_owned_networkless_bounded_fixture():
    good = {'Config': {'Labels': {q.LABEL: 'test'}}, 'AppArmorProfile': 'docker-default',
            'HostConfig': {'NetworkMode': 'none', 'Privileged': False,
                           'ReadonlyRootfs': True, 'Memory': 2147483648,
                           'MemorySwap': 2147483648, 'NanoCpus': 2000000000}}
    q.check_clone(good, 'test')
    for key, value in [('NetworkMode', 'host'), ('Privileged', True),
                       ('Binds', ['/etc/openhab:/openhab/conf']), ('Devices', [{}]),
                       ('PortBindings', {'8080/tcp': [{}]}), ('MemorySwap', -1)]:
        bad = {**good, 'HostConfig': {**good['HostConfig'], key: value}}
        with pytest.raises(RuntimeError):
            q.check_clone(bad, 'test')
    with pytest.raises(RuntimeError):
        q.check_clone(good, 'another-owner')


def test_rest_write_scope_excludes_every_equipment_and_foreign_rule():
    for method, path in [('PUT', '/items/BMS_SOC_Evidence_JSON/state'),
                         ('POST', '/rules'), ('POST', '/rules/' + q.UID + '/runnow'),
                         ('DELETE', '/rules/' + q.UID)]:
        q.check_request(method, path)
    for method, path in [('POST', '/items/ShurefloPump_Power'),
                         ('PUT', '/items/BMS_SOC/state'),
                         ('POST', '/rules/hex_southoutlet_cycle/runnow'),
                         ('DELETE', '/rules/other'), ('PUT', '/things/other'),
                         ('GET', 'http://127.0.0.1:8080/rest/items')]:
        with pytest.raises(RuntimeError):
            q.check_request(method, path)


def test_receipts_are_synthetic_native_observations_with_unchanged_ttls():
    receipts = q.receipts(1800000000000, -300)
    assert set(receipts) == set(q.EVIDENCE)
    runtime = receipts['BMS_Runtime_Input_Evidence_JSON']
    current = runtime['fields']['battery.dc_current_ca']
    assert current['value'] == -300
    assert current['validUntil'] - current['observedAt'] == 90000
    assert receipts['Inverter_AC_Evidence_JSON']['fields']['inverter.ac_output_w']['validUntil'] - runtime['recordedAt'] == 30000


def test_readback_accepts_only_empty_default_action_inputs():
    rule = {'triggers': [], 'actions': [{'id': 'a', 'type': 'script.ScriptAction',
                                        'configuration': {'script': 'exact', 'type': 'application/javascript'}}]}
    action = rule['actions'][0]
    assert q.same_definition(rule, {**rule, 'actions': [{**action, 'inputs': {}}]})
    for change in [{'inputs': {'event': 'other.output'}},
                   {'configuration': {'script': 'changed', 'type': 'application/javascript'}},
                   {'enabled': False}]:
        assert not q.same_definition(rule, {**rule, 'actions': [{**action, **change}]})
    assert not q.same_definition(rule, {**rule, 'triggers': [{'id': 'extra'}]})


def test_numeric_readback_requires_exact_value_not_decimal_rendering():
    assert q.number_is('500', 500)
    assert q.number_is('500.0', 500)
    assert q.number_is('0.0', 0)
    for value in ['NULL', 'UNDEF', 'nan', 'inf', '499', '500 W']:
        assert not q.number_is(value, 500)
