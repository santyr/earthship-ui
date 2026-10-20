"""Advertised verification gates discover real tests and cover shared changes."""
from pathlib import Path
import csv
import ast
import fnmatch
import os
import re
import subprocess
import sys
import pytest

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
    files=sorted(path for path in (ROOT/'openhab/scripts').glob('test_*postgres.py')
        if 'advisory_db_fixture' in path.read_text())
    special=ROOT/'openhab/scripts/test_bms_aux_producer_consumer_postgres.py'
    assert special in files
    for workflow in ['ci.yml','forecast-ml-hardening.yml','household-receipt-integrity.yml']:
        lines=[line.split('PYTHONPATH:',1)[1].strip() for line in
            (ROOT/'.github/workflows'/workflow).read_text().splitlines()
            if 'PYTHONPATH:' in line and '.ci/solar-pv/analytics/src' in line]
        assert lines,workflow
        for declared in lines:
            declared=declared.replace('${{ github.workspace }}',str(ROOT))
            assert str(ROOT/'.ci/solar-pv/analytics/tests') in declared.split(':'),workflow
    workflow=(ROOT/'.github/workflows/ci.yml').read_text()
    assert 'ref: 24d2e8984810cb596fe9792768510a356786f709' in workflow
    assert 'ref: 7b70117bcfb9599a12d0325771ed1103f083fa5c' in workflow
    assert 'path: .ci/solar-pv-bms-aux' in workflow
    for folder,selected in [('solar-pv',[path for path in files if path!=special]),('solar-pv-bms-aux',[special])]:
        declared=':'.join(str(path) for path in [ROOT/'openhab/scripts',
            ROOT/'.ci'/folder/'analytics/src',ROOT/'.ci'/folder/'analytics/tests'])
        result=subprocess.run([sys.executable,'-m','pytest','--collect-only','-q','-p','no:cacheprovider',
            *[str(path) for path in selected]],cwd=ROOT,env={**os.environ,'PYTHONPATH':declared},
            capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stdout+result.stderr
        for path in selected:assert path.name+'::' in result.stdout,result.stdout+result.stderr
        assert 'skipped' not in result.stdout,result.stdout


def shard_shell():
    lines=(ROOT/'.github/workflows/ci.yml').read_text().splitlines()
    step=lines.index('      - name: Existing OpenHAB Python tests (disjoint file partition)')
    start=lines.index('        run: |',step)+1
    script=[]
    for line in lines[start:]:
        if line and not line.startswith('          '):break
        script.append(line[10:] if line else '')
    return '\n'.join(script)


@pytest.mark.parametrize('general_exit,bms_exit',[(0,0),(3,0),(0,7)])
def test_shards_execute_every_file_once_with_separate_companion_profiles(tmp_path,general_exit,bms_exit):
    import json
    from hashlib import sha256
    special='openhab/scripts/test_bms_aux_producer_consumer_postgres.py'
    expected={p.relative_to(ROOT).as_posix() for p in (ROOT/'openhab/scripts').rglob('*.py')
        if p.name.startswith('test_') or p.name.endswith('_test.py')}
    seen=[]
    for shard in range(3):
        record=tmp_path/str(shard)
        prelude=r'''
python() {
  if [ "$1" = '-' ]; then "$A09_PYTHON" "$@"; return; fi
  "$A09_PYTHON" -c 'import json,os,sys;open(os.environ["A09_RECORD"],"a").write(json.dumps({"path":os.environ["PYTHONPATH"],"args":sys.argv[1:]})+"\n")' "$@"
  case "$PYTHONPATH" in *solar-pv-bms-aux*) return "$A09_BMS_EXIT";; *) return "$A09_GENERAL_EXIT";; esac
}
'''
        general=f'{ROOT}/openhab/scripts:{ROOT}/.ci/solar-pv/analytics/src:{ROOT}/.ci/solar-pv/analytics/tests'
        env={**os.environ,'TEST_SHARD':str(shard),'GITHUB_WORKSPACE':str(ROOT),'PYTHONPATH':general,
            'A09_PYTHON':sys.executable,'A09_RECORD':str(record),'A09_GENERAL_EXIT':str(general_exit),'A09_BMS_EXIT':str(bms_exit)}
        result=subprocess.run(['/bin/bash','-c',prelude+shard_shell()],cwd=ROOT,env=env,
            capture_output=True,text=True,timeout=10)
        calls=[json.loads(line) for line in record.read_text().splitlines()]
        owns_special=int(sha256(special.encode()).hexdigest(),16)%3==shard
        assert len(calls)==1+owns_special
        for call in calls:
            assert call['args'][:3]==['-m','pytest','-q']
            files=call['args'][3:];seen.extend(files)
            if files==[special]:
                assert call['path']==f'{ROOT}/openhab/scripts:{ROOT}/.ci/solar-pv-bms-aux/analytics/src:{ROOT}/.ci/solar-pv-bms-aux/analytics/tests'
            else:
                assert special not in files and call['path']==general
        assert result.returncode==(1 if general_exit or owns_special and bms_exit else 0),result.stdout+result.stderr
        assert f'general_pytest_exit={general_exit}' in result.stdout
        assert f'bms_aux_pytest_exit={bms_exit if owns_special else 0}' in result.stdout
    assert len(seen)==len(set(seen)) and set(seen)==expected


def test_actionlint_validates_workflows_and_rejects_job_level_runner_context(tmp_path):
    import shutil
    actionlint=shutil.which('actionlint')
    assert actionlint is not None,'install pinned actionlint v1.7.7 (CI installs it before completion tests)'
    workflows=sorted((ROOT/'.github/workflows').glob('*.yml'))
    result=subprocess.run([actionlint,'-color=false',*[str(path) for path in workflows]],
        cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    invalid=tmp_path/'invalid-job-context.yml'
    invalid.write_text("name: Invalid context regression\non: push\njobs:\n  check:\n    runs-on: ubuntu-latest\n    env:\n      CACHE: ${{ runner.temp }}/browsers\n    steps:\n      - run: echo qualified\n")
    rejected=subprocess.run([actionlint,'-color=false',str(invalid)],cwd=ROOT,
        capture_output=True,text=True,timeout=30)
    assert rejected.returncode!=0
    assert 'context "runner" is not allowed here' in rejected.stdout+rejected.stderr


def test_registered_scorer_fixture_preserves_later_qualification_fit(tmp_path):
    sentinel=tmp_path/'test_fit_environment_sentinel.py'
    sentinel.write_text("import os\ndef test_fit_gate_remains_enabled():\n    assert os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT') == '1'\n    assert os.environ.get('EARTHSHIP_QUALIFICATION_FIT') == '1'\n")
    env={**os.environ,'EARTHSHIP_REMOTE_QUALIFICATION_FIT':'1',
         'EARTHSHIP_QUALIFICATION_FIT':'1',
         'PYTHONPATH':str(ROOT/'openhab/scripts')+os.pathsep+os.environ.get('PYTHONPATH','')}
    callers=[]
    for path in sorted((ROOT/'openhab/scripts').glob('test_*.py')):
        source=path.read_text()
        if 'thermal_installed_score as cli' not in source:continue
        for node in ast.parse(source).body:
            if isinstance(node,ast.FunctionDef) and node.name.startswith('test_'):
                if any(isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute)
                       and call.func.attr=='main' and isinstance(call.func.value,ast.Name)
                       and call.func.value.id=='cli' for call in ast.walk(node)):
                    callers.append(str(path)+'::'+node.name)
    assert callers,'no in-process scorer CLI tests discovered'
    result=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        *callers,str(sentinel)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_hosted_qualification_fit_has_a_non_skippable_dedicated_gate(tmp_path):
    text=(ROOT/'.github/workflows/forecast-ml-hardening.yml').read_text()
    target='openhab/scripts/test_thermal_fit_evidence.py::test_real_qualification_fit_is_exercised_only_on_the_hosted_runner'
    assert '--deselect='+target in text
    dedicated=text.split('  qualification-fit:\n',1)[1]
    assert 'EARTHSHIP_REMOTE_QUALIFICATION_FIT: "1"' in dedicated
    lines=dedicated.splitlines()
    start=lines.index('      - name: Require one executed full qualification fit')
    start=lines.index('        run: |',start)+1
    script='\n'.join(line[10:] for line in lines[start:] if line.startswith('          '))
    assert target in script and '--junitxml=' in script
    for outcome in ('passed','skipped','absent'):
        # Use a structured XML generator so shell quoting cannot change the fixture.
        generator=tmp_path/'emit-result.py'
        generator.write_text("import os,pathlib,xml.etree.ElementTree as E\nr=E.Element('testsuites');s=E.SubElement(r,'testsuite')\nif os.environ['A18_OUTCOME']!='absent':\n c=E.SubElement(s,'testcase',name='test_real_qualification_fit_is_exercised_only_on_the_hosted_runner')\n if os.environ['A18_OUTCOME']=='skipped':E.SubElement(c,'skipped')\nE.ElementTree(r).write(pathlib.Path(os.environ['RUNNER_TEMP'])/'qualification-fit.xml')\n")
        prelude='python() { if [ "$1" = "-m" ]; then "$A18_PYTHON" "$A18_GENERATOR"; else "$A18_PYTHON" "$@"; fi; }\n'
        result=subprocess.run(['/bin/bash','-e','-c',prelude+script],cwd=ROOT,
            env={**os.environ,'A18_PYTHON':sys.executable,'A18_GENERATOR':str(generator),
                 'A18_OUTCOME':outcome,'RUNNER_TEMP':str(tmp_path)},
            capture_output=True,text=True,timeout=10)
        assert (result.returncode==0)==(outcome=='passed'),result.stdout+result.stderr
