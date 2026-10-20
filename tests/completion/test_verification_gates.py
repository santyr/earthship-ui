"""Advertised verification gates discover real tests and cover shared changes."""
from pathlib import Path
import csv
import fnmatch
import os
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def listed(script):
    result=subprocess.run(['npm','run',script,'--','--list'],cwd=ROOT,
        capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr
    return set(re.findall(r'([A-Za-z0-9-]+\.spec\.js):\d+:\d+',result.stdout))


def event(workflow,name):
    text=(ROOT/'.github/workflows'/workflow).read_text()
    match=re.search(r'^  '+re.escape(name)+r':\s*\n(.*?)(?=^  [A-Za-z_]+:|^\S|\Z)',text,re.M|re.S)
    assert match is not None,f'{workflow} has no {name} gate'
    return match.group(1)


def test_geometry_command_discovers_real_console_layouts():
    assert listed('test:geometry')=={'home-runtime.spec.js','controls-layout.spec.js',
        'energy-layout.spec.js','weather-earthship-layout.spec.js','shades-layout.spec.js'}


def test_browser_commands_separate_fixture_and_sensor_dependencies():
    specs={path.name for path in (ROOT/'tests/e2e').glob('*.spec.js')}
    assert listed('test:e2e')==specs-{'sensors-layout.spec.js'}
    assert listed('test:e2e:sensors')=={'sensors-layout.spec.js'}


def test_qa_matrix_references_existing_test_evidence():
    missing=[]
    for row in csv.DictReader((ROOT/'docs/qa/ui-audit-matrix.csv').open()):
        for pattern in re.findall(r'tests/[^;\s]+',row['test_or_evidence']):
            if not list(ROOT.glob(pattern)):missing.append((row['id'],pattern))
    assert missing==[]


def test_sensor_gate_covers_main_release_and_shared_dependencies():
    push=event('sensors.yml','push')
    assert 'main' in push and 'release/**' in push
    assert 'paths:' not in push,'every release revision must run the sensor gate'
    assert 'published' in event('sensors.yml','release')
    paths=re.findall(r"^      - '([^']+)'",event('sensors.yml','pull_request'),re.M)
    for changed in ['src/App.svelte','src/routes.js','src/lib/openhab/store.js',
        'tests/e2e/fixture-test.js','tests/e2e/sensors-layout.spec.js',
        'openhab/scripts/household/snapshot.py','services/observations/registry.py',
        'package-lock.json','playwright.config.js','vite.config.js','requirements-test.txt']:
        assert any(fnmatch.fnmatch(changed,p) for p in paths),changed


def test_general_browser_gate_runs_in_main_and_pull_request_ci(tmp_path):
    event('ci.yml','pull_request');assert 'main' in event('ci.yml','push')
    text=(ROOT/'.github/workflows/ci.yml').read_text()
    assert 'playwright install --with-deps chromium' in text
    lines=text.splitlines();step=lines.index('      - name: General console browser fixtures without upstream network')
    start=lines.index('        run: |',step)+1
    script=[]
    for line in lines[start:]:
        if line and not line.startswith('          '):break
        script.append(line[10:] if line else '')
    # Execute the maintained shell with disposable launchers. No browser,
    # server, privilege change or network namespace is started by this test.
    for name,body in [('node','printf "NODE_ARG:%s\\n" "$@"'),('npm',':'),('ip',':')]:
        path=tmp_path/name;path.write_text('#!/bin/sh\n'+body+'\n');path.chmod(0o700)
    prelude='sudo() { printf "ISOLATION:%s\\n" "$1" "$2" "$3" "$4"; shift 4; "$@"; }\n'
    result=subprocess.run(['/bin/bash','-e','-c',prelude+'\n'.join(script)],cwd=tmp_path,
        env={**os.environ,'PATH':str(tmp_path)+':'+os.environ['PATH'],'GITHUB_WORKSPACE':str(ROOT)},
        capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stdout.splitlines()==[
        'ISOLATION:--preserve-env=PLAYWRIGHT_BROWSERS_PATH','ISOLATION:unshare',
        'ISOLATION:--net','ISOLATION:--','NODE_ARG:'+str(tmp_path/'npm'),
        'NODE_ARG:run','NODE_ARG:test:e2e','NODE_ARG:--','NODE_ARG:--workers=2']


def test_specialist_python_gates_follow_shared_sources_and_requirements():
    for workflow in ['forecast-ml-hardening.yml','household-receipt-integrity.yml']:
        assert 'main' in event(workflow,'push')
        paths=re.findall(r"^      - '([^']+)'",event(workflow,'pull_request'),re.M)
        for changed in ['openhab/scripts/household/planning.py','openhab/scripts/weather_learning/provider.py',
            'openhab/scripts/thermal_model/capture_guard.py','scripts/run-household-job.py','requirements-test.txt']:
            assert any(fnmatch.fnmatch(changed,p) for p in paths),(workflow,changed)


def test_native_postgres_families_collect_with_ci_declared_companion_support():
    import sys
    files=sorted(path for path in (ROOT/'openhab/scripts').glob('test_*postgres.py')
        if 'advisory_db_fixture' in path.read_text())
    assert files,'native PostgreSQL regression families must be discovered'
    for workflow in ['ci.yml','forecast-ml-hardening.yml','household-receipt-integrity.yml']:
        lines=[line.split('PYTHONPATH:',1)[1].strip() for line in
            (ROOT/'.github/workflows'/workflow).read_text().splitlines()
            if 'PYTHONPATH:' in line and '.ci/solar-pv/analytics/src' in line]
        assert lines,workflow
        for declared in lines:
            declared=declared.replace('${{ github.workspace }}',str(ROOT))
            assert str(ROOT/'.ci/solar-pv/analytics/tests') in declared.split(':'),workflow
    # Collection imports every native module without starting PostgreSQL. A
    # missing helper must fail this gate instead of silently skipping them.
    declared=lines[0].replace('${{ github.workspace }}',str(ROOT))
    result=subprocess.run([sys.executable,'-m','pytest','--collect-only','-q','-p','no:cacheprovider',
        *[str(path) for path in files]],cwd=ROOT,env={**os.environ,'PYTHONPATH':declared},
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    for path in files:assert path.name+'::' in result.stdout,result.stdout+result.stderr
    assert 'skipped' not in result.stdout,result.stdout
