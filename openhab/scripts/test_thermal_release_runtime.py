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
    from test_thermal_origin_capture import private_interpreter
    private_interpreter(tmp_path, monkeypatch)
    original = thermal_intel._release_runtime_binding()
    changed = tmp_path/dependency
    changed.write_bytes(changed.read_bytes()+b'\n# runtime identity regression\n')
    assert thermal_intel._release_runtime_binding() != original
