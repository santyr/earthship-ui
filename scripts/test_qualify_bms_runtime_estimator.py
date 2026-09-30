import importlib.util
import ast
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_actual_nested_rest_adapter_forbids_writes_during_natural_wait():
    # Compile the actual closure body with synthetic dependencies. No Docker
    # or host request is made; this checks the gate before dispatch, not just
    # a copy of its predicate or a source substring.
    tree=ast.parse(Path(q.__file__).read_text())
    main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    rest=next(node for node in ast.walk(main) if isinstance(node,ast.FunctionDef) and node.name=='rest')
    calls=[]
    def run(args, header):
        calls.append(args)
        assert args[:4]==['docker','exec','-i','synthetic-fixture']
        assert header==b'synthetic-only'
        return b'{}\n200'
    namespace={'scheduled_only':True,'check_request':q.check_request,'UID':q.UID,
               'container':'synthetic-fixture','header':b'synthetic-only','json':json,
               'runtime':SimpleNamespace(run=run)}
    exec(compile(ast.Module(body=[rest],type_ignores=[]),q.__file__,'exec'),namespace)
    invoke=namespace['rest']
    for method,path,body in [('POST','/rules',{'uid':q.UID}),
                            ('POST','/rules/'+q.UID+'/runnow',{}),
                            ('DELETE','/rules/'+q.UID,None),
                            ('PUT','/items/BMS_SOC_Evidence_JSON/state','synthetic')]:
        with pytest.raises(RuntimeError,match='during natural cron wait'):
            invoke(method,path,body)
    assert calls==[]
    assert invoke('GET','/items/BMS_Runtime_Basis')==(200,{})
    namespace['scheduled_only']=False
    assert invoke('POST','/rules/'+q.UID+'/runnow',{})==(200,{})
    assert len(calls)==2


@pytest.mark.parametrize('post_status',[200,409])
def test_actual_executor_waits_for_idle_before_runnow(post_status):
    tree=ast.parse(Path(q.__file__).read_text())
    main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
    execute=next(node for node in ast.walk(main) if isinstance(node,ast.FunctionDef) and node.name=='execute')
    statuses=iter(['INITIALIZING','IDLE'])
    calls=[]
    def rest(method,path,body=None):
        calls.append((method,path))
        if method=='GET':return 200,{'status':{'status':next(statuses)}}
        assert method=='POST' and body=={}
        return post_status,None
    def wait(check,seconds):
        assert seconds==120
        assert check() is False
        assert calls==[('GET','/rules/'+q.UID)]
        assert check() is True
    sleeps=[]
    namespace={'rest':rest,'UID':q.UID,'fixture':SimpleNamespace(wait_for=wait),
               'time':SimpleNamespace(sleep=sleeps.append)}
    exec(compile(ast.Module(body=[execute],type_ignores=[]),q.__file__,'exec'),namespace)
    if post_status==200:
        namespace['execute']()
        assert sleeps==[1]
    else:
        with pytest.raises(RuntimeError,match='HTTP 409'):namespace['execute']()
        assert sleeps==[]
    assert calls==[('GET','/rules/'+q.UID)]*2+[('POST','/rules/'+q.UID+'/runnow')]
