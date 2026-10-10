"""Guarded threshold derivation; synthetic routing never proves release readiness."""
import importlib
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_installed_calibration_cli import settings as calibration_settings
from test_installed_shade_raw_registration import candidate,retained_raw_case,collection,issued,release_case
from thermal_model.installed_shade_qualification import _score_packets as real_score_packets


def module():return importlib.import_module('thermal_installed_register')


@pytest.fixture
def settings(calibration_settings):
    path,old=calibration_settings
    value={key:old[key] for key in ('runtime_bundle_path','runtime_sha256','raw_sources_path','raw_sources_sha256','regimes','output_directory','shared_lock')}
    value.update(schema='earthship-installed-shade-registration-config/v1',candidate_path=old['base_candidate_path'],candidate_sha256='c'*64,
        intervals=dict(development_start='2025-01-01T00:00:00Z',development_end='2025-02-01T00:00:00Z',
        holdout_start='2999-01-01T00:00:00Z',holdout_end='2999-02-01T00:00:00Z',prospective_start='2999-01-01T00:00:00Z',prospective_end=None))
    path.write_text(json.dumps(value));return path,value


def test_default_registration_only_checks_owned_configuration(settings,monkeypatch,capsys):
    cli=module();path,_=settings
    monkeypatch.setattr(cli,'run_registration',lambda *a,**kw:pytest.fail('check-only sealed policy'))
    assert cli.main(['--config',str(path)])==0
    assert json.loads(capsys.readouterr().out)==dict(status='configuration_verified',registration_executed=False,release_authorized=False)


@pytest.mark.parametrize('damage',['thresholds','late_holdout','scalar_sources','public_source','unbound_candidate'])
def test_registration_configuration_refuses_unsafe_inputs(settings,damage):
    cli=module();path,value=settings
    if damage=='thresholds':value['thresholds']={'max_mae_f':99}
    elif damage=='late_holdout':value['intervals']['holdout_start']='2026-01-01T00:00:00Z'
    elif damage=='scalar_sources':
        source=Path(value['raw_sources_path']);source.write_text('[{"persistence_error_f":1}]');value['raw_sources_sha256']=sha256(source.read_bytes()).hexdigest()
    elif damage=='public_source':Path(value['raw_sources_path']).chmod(0o644)
    else:value['candidate_sha256']=''
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):cli.load_settings(path)


def test_registration_resource_preflight_runs_before_config(settings,monkeypatch,capsys):
    cli=module();path,_=settings
    def refuse():raise ValueError('resource refusal')
    monkeypatch.setattr(cli,'_resource_preflight',refuse)
    monkeypatch.setattr(cli,'load_settings',lambda *_:pytest.fail('read after resource refusal'))
    assert cli.main(['--config',str(path),'--register'])==1
    assert json.loads(capsys.readouterr().out)['status']=='withheld'


def test_registration_shared_lock_and_fit_flags_restore(settings,monkeypatch,capsys):
    cli=module();path,value=settings
    for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT'):monkeypatch.setenv(key,'1')
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    def run(actual,*,guard):
        guard();assert actual==value
        assert all(os.environ[key]=='0' for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT'))
        return dict(status='policy_registered',release_authorized=False)
    monkeypatch.setattr(cli,'run_registration',run)
    assert cli.main(['--config',str(path),'--register'])==0
    assert all(os.environ[key]=='1' for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT'))
    assert json.loads(capsys.readouterr().out)['release_authorized'] is False


def test_default_registration_does_not_import_numerical_libraries(settings):
    path,_=settings
    code="""import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in ('numpy','scipy'):raise RuntimeError('numerical import refused')
sys.meta_path.insert(0,Block())
import thermal_installed_register as cli
raise SystemExit(cli.main(['--config',sys.argv[1]]))
"""
    result=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr+result.stdout


def test_registration_guard_precedes_source_access(settings,monkeypatch):
    cli=module();_,value=settings
    def refuse():raise ValueError('lost lock')
    with pytest.raises(ValueError,match='lost lock'):cli.run_registration(value,guard=refuse)


@pytest.fixture
def worker_ports(settings,monkeypatch):
    """Complete synthetic baseline cohort; actual policy math and seal storage."""
    from test_installed_shade_qualification import numerical_policy
    from thermal_model import runtime_bundle,origin_capture,installed_shade_calibrated_artifact as candidates
    from thermal_model import installed_shade_qualification as qualification,policy_registration as registration
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    from thermal_model.installed_shade_artifact import _digest
    cli=module();_,value=settings;value=deepcopy(value);policy=numerical_policy()
    value['intervals']=policy['intervals'];value['regimes']=policy['regimes']
    clock={'at':datetime.fromisoformat(policy['declared_at']),'seconds':0.}
    monkeypatch.setattr(cli,'_clock',lambda:clock['at']);monkeypatch.setattr(cli,'monotonic',lambda:clock['seconds'])
    monkeypatch.setattr(registration,'_clock',lambda:clock['at'])
    runtime=dict(source_manifest={name:'d'*64 for name in RAW_RUNTIME_PATHS})
    archive=dict(runtime=runtime,revision_paths=sorted(RAW_RUNTIME_PATHS));value['runtime_sha256']=_digest(runtime)
    monkeypatch.setattr(runtime_bundle,'read_runtime_bundle',lambda *_:deepcopy(archive))
    monkeypatch.setattr(origin_capture,'build_runtime_binding',lambda *a:deepcopy(runtime))
    artifact={key:policy['candidate'][key] for key in ('artifact_sha256','trained_through','created_at','sensor_epochs')}
    artifact.update(schema='earthship-installed-shade-candidate/v3',runtime=runtime,base_candidate=dict(dynamics=dict(coefficients={str(i):1 for i in range(10)})))
    value['candidate_sha256']=artifact['artifact_sha256']
    loaded=dict(artifact=artifact,fit_evidence=dict(fit_gates_passed=True),calibration=dict(summary=dict(complete=True)))
    monkeypatch.setattr(candidates,'read_raw_calibrated_candidate',lambda *a,**kw:deepcopy(loaded))
    refs=[dict(raw_score_sources_path=str(Path(value['raw_sources_path']).parent/(f'{i:064x}.installed-shade-score-sources-v2.json'))) for i in range(len(policy['development']))]
    source=Path(value['raw_sources_path']);source.write_text(json.dumps(refs));value['raw_sources_sha256']=sha256(source.read_bytes()).hexdigest()
    rows=[dict(row,sensor_epochs=policy['candidate']['sensor_epochs']) for row in policy['development']]
    bindings=[dict(original_capture_sha256=f'{i//4:064x}',raw_score_sources_sha256=f'{i:064x}',native_binding_sha256='e'*64) for i in range(len(rows))]
    monkeypatch.setattr(qualification,'_score_packets',lambda *a,**kw:dict(raw_native_score_sources=True,rows=deepcopy(rows),bindings=deepcopy(bindings)))
    return cli,value,clock,loaded,rows,qualification,registration


def test_registration_worker_derives_and_seals_without_release_authority(worker_ports):
    cli,value,clock,loaded,rows,qualification,registration=worker_ports
    result=cli.run_registration(value,guard=lambda:None)
    sealed=registration.read_raw_calibrated_installed_shade_registered_policy(Path(result['registration_path']))
    assert result['status']=='policy_registered' and result['release_authorized'] is False and result['production_installed'] is False
    assert sealed['policy']['thresholds']['24']['max_mae_f']==2
    assert sealed['policy']['candidate']['artifact_sha256']==value['candidate_sha256']
    assert sealed['policy']['declared_at']==clock['at'].isoformat()
    receipt=json.loads(Path(result['receipt_path']).read_text())
    assert receipt['command_source']['utf8']==Path(cli.__file__).read_text()
    assert receipt['registration_sha256']==sealed['registration_sha256']


@pytest.mark.parametrize('damage',['weak_candidate','unfit','incomplete','wrong_epoch','wrong_digest','index_drift','runtime_drift','deadline'])
def test_registration_worker_refuses_damaged_original_inputs_before_seal(worker_ports,monkeypatch,damage):
    cli,value,clock,loaded,rows,qualification,registration=worker_ports
    if damage=='weak_candidate':loaded['artifact']['schema']='earthship-installed-shade-candidate/v2'
    elif damage=='unfit':loaded['fit_evidence']['fit_gates_passed']=False
    elif damage=='incomplete':loaded['calibration']['summary']['complete']=False
    elif damage=='wrong_epoch':rows[0]['sensor_epochs']={}
    elif damage=='wrong_digest':value['candidate_sha256']='f'*64
    else:
        previous=qualification._score_packets
        def changed(*a,**kw):
            scored=previous(*a,**kw)
            if damage=='index_drift':Path(value['raw_sources_path']).write_text('[]')
            elif damage=='runtime_drift':loaded['artifact']['runtime']['changed']=True
            else:clock['seconds']=86.
            return scored
        monkeypatch.setattr(qualification,'_score_packets',changed)
    with pytest.raises(ValueError):cli.run_registration(value,guard=lambda:None)
    assert list(Path(value['output_directory']).iterdir())==[]


def test_registration_holdout_starting_during_private_write_prevents_seal(worker_ports,monkeypatch):
    cli,value,clock,loaded,rows,qualification,registration=worker_ports
    from thermal_model import runtime_bundle
    previous=runtime_bundle._write_private
    def late(*a,**kw):previous(*a,**kw);clock['at']=datetime.fromisoformat(value['intervals']['holdout_start'])
    monkeypatch.setattr(runtime_bundle,'_write_private',late)
    with pytest.raises(ValueError):cli.run_registration(value,guard=lambda:None)
    assert list(Path(value['output_directory']).iterdir())==[]


def test_registration_worker_refuses_deleted_original_query(worker_ports,retained_raw_case,monkeypatch):
    cli,value,clock,loaded,rows,qualification,registration=worker_ports
    _,original,backend,_,_=retained_raw_case
    source=Path(value['raw_sources_path']);source.write_text(json.dumps(original['original_pairs']))
    value['raw_sources_sha256']=sha256(source.read_bytes()).hexdigest()
    attempted=[]
    def actual_replay(*args,**kwargs):
        attempted.append(True);return real_score_packets(*args,**kwargs)
    monkeypatch.setattr(qualification,'_score_packets',actual_replay)
    Path(backend.native_source_paths[-1]).unlink()
    with pytest.raises((ValueError,OSError)):cli.run_registration(value,guard=lambda:None)
    assert attempted, 'worker refused before original query replay'
    assert list(Path(value['output_directory']).iterdir())==[]


def test_registration_source_guard_crossing_holdout_prevents_atomic_seal(worker_ports,monkeypatch):
    cli,value,clock,loaded,rows,qualification,registration=worker_ports
    from thermal_model import origin_capture
    previous=origin_capture._source_bytes;crossed=[]
    def late(*args,**kwargs):
        raw=previous(*args,**kwargs)
        if list(Path(value['output_directory']).iterdir()):
            crossed.append(True);clock['at']=datetime.fromisoformat(value['intervals']['holdout_start'])
        return raw
    monkeypatch.setattr(origin_capture,'_source_bytes',late)
    with pytest.raises(ValueError):cli.run_registration(value,guard=lambda:None)
    assert crossed and list(Path(value['output_directory']).iterdir())==[]
