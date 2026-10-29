"""Browser bootstrap honors completed retirement, not the earlier Python phase."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from services.lorawan.tests.test_stack_ownership import owned_stack
from services.lorawan.tests.qualification_guard import Refused


@pytest.fixture
def browser_phase(owned_stack, monkeypatch, tmp_path):
    from services.lorawan.tests import stack_ownership as ownership
    from services.lorawan.tests import qualification_runtime as runtime
    from services.lorawan.tests import qualification_guard as guard
    ownership, containers, _, _, _, _ = owned_stack
    for row in containers:
        if row['Config']['Labels']['com.docker.compose.service'] in ('chirpstack', 'redis'):
            row['State'] = {'Running': False, 'Pid': 0}
    ids = {row['Config']['Labels']['com.docker.compose.service']: row['Id'] for row in containers}
    ids['simulator'] = f'{7:064x}'
    digest = 'a' * 64
    unit = 'earthship-sensor-guard-' + 'a' * 32 + '.service'
    envelope = {'mode': 'qualification', 'stack': {'containers': {name: {'Id': value} for name, value in ids.items()}},
                'controller': {'guardian_unit': unit}}
    receipt = {'manifest_sha256': digest, 'ids': ids, 'phase': 'armed', 'workload_phase': 'browser', 'pending': None}
    calls = []
    socket = object()
    monkeypatch.setenv('SENSOR_QUALIFICATION_MANIFEST', str(tmp_path / 'manifest.json'))
    monkeypatch.setenv('SENSOR_QUALIFICATION_SHA256', digest)

    class Lease:
        def __init__(self, path, pin, **kwargs):
            assert path == tmp_path / 'manifest.json' and pin == digest
            assert kwargs['root'] == tmp_path and kwargs['nonce'] == 'a' * 32

        def verify(self):
            calls.append('lease')
            return deepcopy(envelope)

    class Backend:
        def __init__(self, stack, **kwargs):
            assert stack == envelope['stack'] and kwargs['request'] is socket
            assert kwargs['cgroup_empty'] is runtime.docker_cgroup_empty

        def browser_ready(self):
            calls.append('retirement-proof')

    def read(path):
        assert str(path) == '/run/' + unit.removesuffix('.service') + '/receipt.json'
        calls.append('receipt')
        return deepcopy(receipt)

    monkeypatch.setattr(runtime, 'Lease', Lease)
    monkeypatch.setattr(runtime, 'DockerSocket', lambda: socket)
    monkeypatch.setattr(runtime, 'DockerBackend', Backend)
    monkeypatch.setattr(guard, 'read_private', read)
    return SimpleNamespace(ownership=ownership, envelope=envelope, receipt=receipt, calls=calls, guard=guard)


def test_retired_stack_passes_browser_bootstrap_but_not_python_bootstrap(browser_phase):
    state = browser_phase
    state.ownership.main(['--browser'])
    assert state.calls == ['lease', 'receipt', 'retirement-proof', 'lease', 'receipt']
    with pytest.raises(state.ownership.IsolationError):
        state.ownership.main([])


@pytest.mark.parametrize('change', ['python', 'browser-ready', 'cleanup', 'pending', 'digest', 'ids', 'mode'])
def test_browser_phase_must_be_complete_before_retirement_proof(browser_phase, change):
    state = browser_phase
    if change in ('python', 'browser-ready'):
        state.receipt['workload_phase'] = change
    elif change == 'cleanup':
        state.receipt['phase'] = 'cleanup'
    elif change == 'pending':
        state.receipt['pending'] = {'operation': 'stop'}
    elif change == 'digest':
        state.receipt['manifest_sha256'] = 'b' * 64
    elif change == 'ids':
        state.receipt['ids'] = {**state.receipt['ids'], 'redis': 'f' * 64}
    else:
        state.envelope['mode'] = 'lifecycle-proof'
    with pytest.raises(Refused):
        state.ownership.assert_browser_stack()
    assert 'retirement-proof' not in state.calls


def test_phase_change_during_proof_refuses_browser_start(browser_phase, monkeypatch):
    state = browser_phase
    original = state.guard.read_private
    reads = []

    def read(path):
        result = original(path)
        reads.append(True)
        if len(reads) == 2:
            result['phase'] = 'cleanup'
        return result

    monkeypatch.setattr(state.guard, 'read_private', read)
    with pytest.raises(Refused, match='changed during preflight'):
        state.ownership.assert_browser_stack()
