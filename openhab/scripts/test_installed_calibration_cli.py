"""Guarded raw calibration command; routing ports are not release evidence."""
import importlib
from copy import deepcopy
import json
import os
from pathlib import Path
import pytest


def module():return importlib.import_module('thermal_installed_calibrate')


@pytest.fixture
def settings(tmp_path,monkeypatch):
    tmp_path.chmod(0o700)
    for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT'):monkeypatch.setenv(key,os.environ.get(key,'0'))
    out=tmp_path/'out';out.mkdir(mode=0o700)
    base=tmp_path/'base';base.mkdir(mode=0o700);runtime=tmp_path/'runtime';runtime.mkdir(mode=0o700)
    candidate=tmp_path/'candidate';candidate.write_text('{}');candidate.chmod(0o600)
    sources=tmp_path/'sources';sources.write_text('[{"raw_score_sources_path":"/private/original"}]');sources.chmod(0o600)
    lock=tmp_path/'lock';lock.touch(mode=0o600)
    from hashlib import sha256
    value=dict(schema='earthship-installed-shade-calibration-config/v1',base_candidate_path=str(candidate),
        base_runtime_bundle_path=str(base),runtime_bundle_path=str(runtime),base_runtime_sha256='a'*64,runtime_sha256='b'*64,
        raw_sources_path=str(sources),raw_sources_sha256=sha256(sources.read_bytes()).hexdigest(),
        calibration_start='2026-01-01T00:00:00Z',calibration_end='2026-02-01T00:00:00Z',regimes=['winter'],
        output_directory=str(out),shared_lock=str(lock))
    path=tmp_path/'config';path.write_text(json.dumps(value));path.chmod(0o600)
    return path,value


def test_default_calibration_command_only_checks_closed_private_settings(settings,monkeypatch,capsys):
    cli=module();path,value=settings
    monkeypatch.setattr(cli,'run_calibration',lambda *a,**kw:pytest.fail('check-only reached calibration'))
    assert cli.main(['--config',str(path)])==0
    assert json.loads(capsys.readouterr().out)==dict(status='configuration_verified',calibration_executed=False,release_authorized=False)
    assert list(Path(value['output_directory']).iterdir())==[]


@pytest.mark.parametrize('damage',['extra','legacy_source','public','relative','future'])
def test_calibration_config_refuses_invalid_or_unpinned_sources(settings,damage):
    cli=module();path,value=settings
    if damage=='extra':value['active']=True
    elif damage=='legacy_source':Path(value['raw_sources_path']).write_text('[]')
    elif damage=='public':Path(value['raw_sources_path']).chmod(0o644)
    elif damage=='relative':value['base_candidate_path']='relative'
    else:value['calibration_end']='2999-01-01T00:00:00Z'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):cli.load_settings(path)


def test_calibration_resource_refusal_precedes_source_reads(settings,monkeypatch,capsys):
    cli=module();path,_=settings
    def refuse():raise ValueError('synthetic resource refusal')
    monkeypatch.setattr(cli,'_resource_preflight',refuse)
    monkeypatch.setattr(cli,'load_settings',lambda *_:pytest.fail('configuration read after resource refusal'))
    assert cli.main(['--config',str(path),'--calibrate'])==1
    assert json.loads(capsys.readouterr().out)['status']=='withheld'


def test_calibration_runs_under_existing_shared_lock_and_disables_fit(settings,monkeypatch,capsys):
    cli=module();path,value=settings;events=[]
    monkeypatch.setattr(cli,'_resource_preflight',lambda:events.append('guard'))
    def run(actual,*,guard):
        guard();assert actual==value and events==['guard']
        assert os.environ['EARTHSHIP_QUALIFICATION_FIT']=='0' and os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']=='0'
        return dict(status='calibration_incomplete',calibration_executed=True,release_authorized=False)
    monkeypatch.setattr(cli,'run_calibration',run)
    assert cli.main(['--config',str(path),'--calibrate'])==0
    assert json.loads(capsys.readouterr().out)['status']=='calibration_incomplete'


def test_calibration_worker_checks_held_lock_before_any_private_source_read(settings,monkeypatch):
    from thermal_model import runtime_bundle
    cli=module();_,value=settings
    def no_source(*a,**kw):pytest.fail('private read before held-lock check')
    monkeypatch.setattr(runtime_bundle,'_owned_bytes',no_source)
    def refused():raise ValueError('lock unavailable')
    with pytest.raises(ValueError,match='lock unavailable'):cli.run_calibration(value,guard=refused)


@pytest.fixture
def worker_ports(settings,monkeypatch):
    """Typed API routing ports only; this is not an original-source cohort."""
    from thermal_model import runtime_bundle,origin_capture,training_inputs,installed_shade_artifact as base
    from thermal_model import installed_shade_calibration as calibration,installed_shade_calibrated_artifact as candidates
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    cli=module();_,value=settings;value=dict(value)
    runtime=dict(source_manifest={key:'c'*64 for key in RAW_RUNTIME_PATHS})
    archive=dict(runtime=runtime,revision_paths=sorted(RAW_RUNTIME_PATHS))
    value['base_runtime_sha256']=base._digest(runtime);value['runtime_sha256']=base._digest(runtime)
    monkeypatch.setattr(runtime_bundle,'read_runtime_bundle',lambda _:deepcopy(archive))
    monkeypatch.setattr(origin_capture,'build_runtime_binding',lambda *a:runtime)
    bundle=dict(artifact=dict(source_snapshot_sha256='d'*64),fit_evidence=dict(fit_gates_passed=True))
    monkeypatch.setattr(base,'read_candidate_bundle',lambda *a,**kw:bundle)
    monkeypatch.setattr(training_inputs,'read_training_inputs_v2',lambda _:dict(synthetic=True))
    record=dict(schema='earthship-installed-shade-calibration/v2',calibration_sha256='c'*64,summary=dict(complete=False))
    def build(**kw):
        assert kw['original_pairs']==[dict(raw_score_sources_path='/private/original')]
        assert kw['expected_runtime_revision']==value['base_runtime_sha256']
        return dict(record)
    monkeypatch.setattr(calibration,'build_raw_calibration',build)
    path=Path(value['output_directory'])/'calibration.json'
    def write(root,body,**kw):path.write_text(json.dumps(body));path.chmod(0o600);return path
    monkeypatch.setattr(calibration,'write_raw_calibration',write)
    monkeypatch.setattr(calibration,'read_raw_calibration',lambda *a,**kw:dict(record))
    artifact=dict(schema='earthship-installed-shade-candidate/v3',artifact_sha256='e'*64)
    monkeypatch.setattr(candidates,'build_raw_calibrated_candidate',lambda **kw:artifact)
    candidate=Path(value['output_directory'])/'candidate.json'
    def write_candidate(root,body,**kw):candidate.write_text(json.dumps(body));candidate.chmod(0o600);return candidate
    monkeypatch.setattr(candidates,'write_raw_calibrated_candidate',write_candidate)
    monkeypatch.setattr(candidates,'read_raw_calibrated_candidate',lambda *a,**kw:dict(artifact=artifact))
    return cli,value,record,candidate,archive


@pytest.mark.parametrize('complete',[False,True])
def test_raw_calibration_only_freezes_when_support_complete_and_retains_execution_receipt(worker_ports,complete):
    cli,value,record,candidate,_=worker_ports;record['summary']['complete']=complete
    result=cli.run_calibration(value,guard=lambda:None)
    assert result['status']==('calibrated_development_candidate' if complete else 'calibration_incomplete')
    assert candidate.exists() is complete and result['release_authorized'] is False and result['production_installed'] is False
    receipt=json.loads(Path(result['receipt_path']).read_text())
    assert receipt['schema']=='earthship-installed-shade-calibration-build-receipt/v1'
    assert receipt['raw_sources_sha256']==value['raw_sources_sha256']
    assert receipt['command_source']['utf8']==Path(cli.__file__).read_text()
    assert receipt['production_installed'] is False


@pytest.mark.parametrize('damage',['index','runtime'])
def test_changed_original_sources_refuse_freezing_without_candidate_or_execution_receipt(worker_ports,monkeypatch,damage):
    from thermal_model import installed_shade_calibration as calibration
    cli,value,record,candidate,archive=worker_ports;record['summary']['complete']=True
    build=calibration.build_raw_calibration
    def change(**kw):
        body=build(**kw)
        if damage=='index':Path(value['raw_sources_path']).write_text('[]')
        else:archive['runtime']['source_manifest']['thermal_intel.py']='f'*64
        return body
    monkeypatch.setattr(calibration,'build_raw_calibration',change)
    with pytest.raises(ValueError):cli.run_calibration(value,guard=lambda:None)
    assert not candidate.exists() and not list(Path(value['output_directory']).glob('*.installed-shade-calibration-build-v1.json'))

from test_installed_shade_raw_calibration import retained_raw_case,collection,issued,release_case,candidate


def test_command_refuses_original_small_history_fit_before_calibration_or_freezing(retained_raw_case,candidate,settings,monkeypatch):
    from thermal_model import installed_shade_artifact as base,origin_capture,runtime_bundle
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    calibration,source_values,_,root,_=retained_raw_case;cli=module();_,value=settings;value=dict(value)
    assert candidate[0]['fit_evidence']['fit_gates_passed'] is False
    base_path=base.write_candidate_bundle(root,candidate[0],candidate[1],
        expected_runtime_revision=source_values['expected_runtime_revision'],assessed_at=source_values['created_at'])
    value['base_candidate_path']=str(base_path);value['base_runtime_sha256']=base._digest(candidate[2])
    runtime=deepcopy(candidate[2])
    for name in RAW_RUNTIME_PATHS-runtime['source_manifest'].keys():runtime['source_manifest'][name]='7'*64
    value['runtime_sha256']=base._digest(runtime)
    archive=dict(runtime=runtime,revision_paths=sorted(RAW_RUNTIME_PATHS))
    base_archive=dict(runtime=candidate[2],revision_paths=sorted(candidate[2]['source_manifest']))
    monkeypatch.setattr(runtime_bundle,'read_runtime_bundle',lambda path:deepcopy(base_archive if path==Path(value['base_runtime_bundle_path']) else archive))
    monkeypatch.setattr(origin_capture,'build_runtime_binding',lambda *a:runtime)
    monkeypatch.setattr(cli,'_clock',lambda:source_values['created_at'])
    sources=Path(value['raw_sources_path']);sources.write_text(json.dumps(source_values['original_pairs']))
    from hashlib import sha256
    value['raw_sources_sha256']=sha256(sources.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='source-qualified base fit required'):cli.run_calibration(value,guard=lambda:None)
    assert list(Path(value['output_directory']).iterdir())==[]


def test_default_check_does_not_import_numerical_modules(settings):
    import subprocess,sys
    path,_=settings
    script="""import sys
class RefuseNumericalImports:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('numpy','scipy'):
            raise AssertionError('numerical import before resource preflight')
sys.meta_path.insert(0,RefuseNumericalImports())
import thermal_installed_calibrate as cli
raise SystemExit(cli.main(['--config',sys.argv[1]]))
"""
    result=subprocess.run([sys.executable,'-c',script,str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['status']=='configuration_verified'


def test_command_budget_reaches_final_candidate_atomic_write(worker_ports,monkeypatch):
    from thermal_model import installed_shade_artifact as base,installed_shade_calibrated_artifact as candidates
    cli,value,record,_,_=worker_ports;record['summary']['complete']=True;clock=[0.]
    monkeypatch.setattr(cli,'monotonic',lambda:clock[0])
    original=base._write_private
    def late(*args):original(*args);clock[0]=86.
    monkeypatch.setattr(base,'_write_private',late)
    def persist(root,artifact,**kw):return base._persist(root,artifact,artifact['artifact_sha256'],'.installed-shade-candidate-v3.json')
    monkeypatch.setattr(candidates,'write_raw_calibrated_candidate',persist)
    with pytest.raises(ValueError):cli.run_calibration(value,guard=lambda:None)
    assert not list(Path(value['output_directory']).glob('*.installed-shade-candidate-v3.json'))
    assert not list(Path(value['output_directory']).glob('*.installed-shade-calibration-build-v1.json'))
