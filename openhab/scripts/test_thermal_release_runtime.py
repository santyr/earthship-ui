"""Release qualification must be available in the deployable runtime alone."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('module', ['graduation_decision', 'policy_registration', 'graduation_evidence', 'recent_cycles'])
def test_release_evaluator_imports_without_repository_tools(tmp_path, module):
    runtime = Path(__file__).resolve().parent
    environment = dict(os.environ, PYTHONPATH=str(runtime))
    result = subprocess.run([sys.executable, '-c', f'import thermal_model.{module}'],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_tooling_imports_share_runtime_implementation():
    import thermal_graduation_decision
    import thermal_policy_registration
    import thermal_graduation_evidence
    import thermal_recent_cycles
    from thermal_model import graduation_decision, policy_registration, graduation_evidence, recent_cycles
    assert thermal_graduation_decision is graduation_decision
    assert thermal_policy_registration is policy_registration
    assert thermal_graduation_evidence is graduation_evidence
    assert thermal_recent_cycles is recent_cycles


def test_release_cli_is_explicit_and_has_no_active_override():
    import thermal_intel
    args = thermal_intel._build_parser().parse_args(['release', '--evidence-inputs', '/private/inputs.json'])
    assert args.publish is False
    assert args.evidence_inputs == Path('/private/inputs.json')
    with pytest.raises(SystemExit):
        thermal_intel._build_parser().parse_args(['release', '--evidence-inputs', '/private/inputs.json', '--active'])


def release_case(tmp_path, monkeypatch):
    from copy import deepcopy
    from datetime import timedelta
    import json
    import thermal_intel
    from test_thermal_release import inputs, shift, NOW
    from test_thermal_origin_capture import capture_inputs
    from thermal_model.forcing_capture import _canonical
    from types import SimpleNamespace
    data = inputs(monkeypatch)
    original = capture_inputs()
    proof = shift(json.loads(_canonical(original['origin_temperatures'])))
    current = shift(json.loads(_canonical(original['current'])))
    report = data['qualification_loader'](NOW)
    monkeypatch.setattr(thermal_intel.forecast_intel, 'load_site_settings', lambda: None)
    def observed(at, *, origin_observer=None):
        assert origin_observer is not None
        origin_observer(deepcopy(proof))
        return deepcopy(current)
    monkeypatch.setattr(thermal_intel, '_current_states', observed)
    monkeypatch.setattr(thermal_intel.forecast_intel, 'fetch_forecast', lambda: {})
    monkeypatch.setattr(thermal_intel, '_forecast_rows', lambda *_: [{'at': NOW, 'mode': 'warm'}])
    def predict(**kwargs):
        kwargs['artifact_observer'](original['artifact'])
        return deepcopy(data['shadow'])
    monkeypatch.setattr(thermal_intel, 'run_shadow', predict)
    monkeypatch.setattr(thermal_intel, '_release_runtime_binding', lambda: deepcopy(report['runtime']['runtime']))
    from thermal_model import graduation_decision
    def evaluate(at):
        from hashlib import sha256
        result = deepcopy(report)
        result['assessed_at'] = at.isoformat()
        result['report_sha256'] = sha256(_canonical({key: value for key, value in result.items() if key != 'report_sha256'})).hexdigest()
        return result
    monkeypatch.setattr(graduation_decision, 'load_qualification_inputs', lambda _: evaluate)
    args = SimpleNamespace(evidence_inputs=tmp_path/'inputs.json', output=tmp_path/'release.json', publish=True)
    return thermal_intel, args, data, NOW


def test_release_command_uses_native_identity_and_fresh_evaluator(tmp_path, monkeypatch):
    import json
    thermal, args, data, now = release_case(tmp_path, monkeypatch)
    sent = []
    result = thermal._release(args, now, put_state=lambda *values: sent.append(values),
        decision_clock=lambda: now, qualification_clock=lambda: now)
    assert result == 0 and len(sent) == 1
    payload = json.loads(sent[0][1])
    assert payload == json.loads(args.output.read_text())
    assert payload['status'] == 'forecast_active' and payload['version'] == 2
    assert payload['release']['artifactSha256'] == data['artifact_sha256']
    assert payload['release']['sensorEpochs'] == data['sensor_epochs']


@pytest.mark.parametrize('failure', ['source', 'missing_origin', 'runtime_drift', 'expired_during_qualification'])
def test_release_command_failure_publishes_unavailable(tmp_path, monkeypatch, failure):
    from copy import deepcopy
    from datetime import timedelta
    import json
    thermal, args, data, now = release_case(tmp_path, monkeypatch)
    from thermal_model import graduation_decision
    if failure == 'source':
        def refused(_): raise ValueError('missing original evidence')
        monkeypatch.setattr(graduation_decision, 'load_qualification_inputs', refused)
    elif failure == 'missing_origin':
        monkeypatch.setattr(thermal, '_current_states', lambda *_args, **_kwargs: {})
    elif failure == 'runtime_drift':
        calls = []
        runtime = thermal._release_runtime_binding()
        def changed():
            calls.append(True)
            result = deepcopy(runtime)
            if len(calls) > 1: result['code_revision'] = '0'*64
            return result
        monkeypatch.setattr(thermal, '_release_runtime_binding', changed)
    clocks = iter([now, now+timedelta(minutes=21)] if failure == 'expired_during_qualification' else [now, now])
    sent = []
    result = thermal._release(args, now, put_state=lambda *values: sent.append(values),
        decision_clock=lambda: now, qualification_clock=lambda: next(clocks))
    assert result == 1 and len(sent) == 1
    assert json.loads(sent[0][1])['status'] == 'unavailable'
    assert json.loads(args.output.read_text())['forecast']['trajectory'] == []


def test_release_preview_never_calls_transport(tmp_path, monkeypatch):
    import json
    thermal, args, _, now = release_case(tmp_path, monkeypatch)
    args.publish = False
    def prohibited(*_):
        raise AssertionError('preview must not publish')
    assert thermal._release(args, now, put_state=prohibited,
        decision_clock=lambda: now, qualification_clock=lambda: now) == 0
    assert json.loads(args.output.read_text())['status'] == 'forecast_active'


@pytest.mark.parametrize('dependency', ['thermal_model/release.py', 'thermal_model/graduation_decision.py'])
def test_release_runtime_binding_changes_with_executed_qualification_source(tmp_path, monkeypatch, dependency):
    import shutil
    import thermal_intel
    source = Path(thermal_intel.__file__).resolve().parent
    for relative in thermal_intel._release_runtime_paths():
        target = tmp_path/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/relative, target)
        target.chmod(0o600)
    monkeypatch.setattr(thermal_intel, '__file__', str(tmp_path/'thermal_intel.py'))
    original = thermal_intel._release_runtime_binding()
    changed = tmp_path/dependency
    changed.write_bytes(changed.read_bytes()+b'\n# runtime identity regression\n')
    assert thermal_intel._release_runtime_binding() != original
