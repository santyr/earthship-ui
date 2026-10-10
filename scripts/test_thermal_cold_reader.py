"""Fresh-process checks of retained reader contracts; no fitting or household I/O."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig

import pytest

ROOT = Path(__file__).resolve().parents[1]


def fixture(tmp_path):
    tmp_path.chmod(0o700)
    runtime = tmp_path/'runtime'; runtime.mkdir(mode=0o700)
    package = runtime/'thermal_model'; package.mkdir(mode=0o700)
    modules = {
        '__init__.py': '',
        'artifacts.py': '''from types import SimpleNamespace
MODEL_SCHEMA = 'earthship-thermal-model/v4'
def _artifact_from_payload(value):
    if value['schema'] != MODEL_SCHEMA: raise ValueError('schema mismatch')
    return SimpleNamespace(**value)
def validate_artifact(value, **kwargs):
    if value.schema != MODEL_SCHEMA: raise ValueError('schema mismatch')
''',
        'schema.py': '''def validate_shadow_output(value):
    if value['version'] != 1 or value['status'] != 'shadow': raise ValueError('not shadow')
''',
        'forcing_capture.py': '''def _artifact_payload(artifact, output):
    if output['model']['codeRevision'] != artifact.code_revision: raise ValueError('wrong pair')
    return vars(artifact)
'''}
    sources = {}
    for name, text in modules.items():
        path = package/name; path.write_text(text); path.chmod(0o600)
        sources['thermal_model/'+name] = sha256(path.read_bytes()).hexdigest()
    artifact = tmp_path/'artifact.json'; artifact.write_text(json.dumps(dict(schema='earthship-thermal-model/v4', code_revision='a'*40))); artifact.chmod(0o600)
    output = tmp_path/'shadow.json'; output.write_text(json.dumps(dict(version=1, status='shadow', confidence=dict(grade='low'), model=dict(codeRevision='a'*40)))); output.chmod(0o600)
    executable = tmp_path/'python'; shutil.copyfile(Path(sys.executable).resolve(), executable); executable.chmod(0o700)
    profile = dict(schema='earthship-thermal-cold-reader/v1', runtime=str(runtime), sources=sources,
        artifact_schema='earthship-thermal-model/v4', interpreter_sha256=sha256(executable.read_bytes()).hexdigest(),
        artifact=dict(path=str(artifact), sha256=sha256(artifact.read_bytes()).hexdigest()),
        output=dict(path=str(output), sha256=sha256(output.read_bytes()).hexdigest()))
    path = tmp_path/'profile.json'; path.write_text(json.dumps(profile)); path.chmod(0o600)
    return path, profile, executable


def run(path, executable):
    environment = dict(PATH=os.defpath, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()['purelib'],
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    return subprocess.run([str(executable), str(ROOT/'scripts/verify-thermal-cold-reader.py'), '--profile', str(path)],
        env=environment, cwd=path.parent, text=True, capture_output=True, timeout=30)


def test_fresh_retained_v4_reader_preserves_original_contract(tmp_path):
    path, profile, executable = fixture(tmp_path)
    result = run(path, executable)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['artifact_schema'] == 'earthship-thermal-model/v4'
    assert receipt['cold_artifact_reader_verified'] is True
    assert receipt['production_qualified'] is False
    assert receipt['journal_qualified'] is False
    assert receipt['dependency_environment_retained'] is False
    assert not list((tmp_path/'runtime').rglob('__pycache__'))


@pytest.mark.parametrize('damage', ['source', 'artifact', 'output', 'schema', 'extra', 'permissions', 'interpreter'])
def test_changed_or_incompatible_cold_profile_refuses(tmp_path, damage):
    path, profile, executable = fixture(tmp_path)
    if damage == 'source': (tmp_path/'runtime/thermal_model/artifacts.py').write_text('raise AssertionError("must not execute changed code")')
    elif damage in ('artifact', 'output'): Path(profile[damage]['path']).write_text('{}')
    elif damage == 'schema': profile['artifact_schema'] = 'earthship-thermal-model/v5'
    elif damage == 'extra': (tmp_path/'runtime/extra.py').write_text('# unexpected')
    elif damage == 'permissions': Path(profile['artifact']['path']).chmod(0o644)
    elif damage == 'interpreter': profile['interpreter_sha256'] = '0'*64
    path.write_text(json.dumps(profile))
    result = run(path, executable)
    assert result.returncode == 2
    assert result.stdout == '' and 'refused' in result.stderr


def test_pinned_reader_attempt_to_connect_is_refused_offline(tmp_path):
    path, profile, executable = fixture(tmp_path)
    module = tmp_path/'runtime/thermal_model/artifacts.py'
    module.write_text("import socket\nsocket.create_connection(('127.0.0.1', 8080))\n"+module.read_text())
    profile['sources']['thermal_model/artifacts.py'] = sha256(module.read_bytes()).hexdigest()
    path.write_text(json.dumps(profile))
    result = run(path, executable)
    assert result.returncode == 2 and result.stdout == ''
    assert 'refused' in result.stderr


def test_warm_import_cannot_be_reported_as_cold(tmp_path):
    path, profile, executable = fixture(tmp_path)
    environment = dict(PATH=os.defpath, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()['purelib'],
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    program = 'import sys,runpy; sys.path.insert(0,sys.argv[1]); import thermal_model; sys.argv=[sys.argv[2],"--profile",sys.argv[3]]; runpy.run_path(sys.argv[0],run_name="__main__")'
    result = subprocess.run([str(executable), '-c', program, profile['runtime'],
        str(ROOT/'scripts/verify-thermal-cold-reader.py'), str(path)], env=environment,
        cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 2 and result.stdout == ''
