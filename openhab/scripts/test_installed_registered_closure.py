"""Registration must run with exactly the declared retained numerical sources."""
from pathlib import Path
import subprocess
import sys


def test_registered_publication_uses_only_declared_runtime_contents(tmp_path):
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    source=Path(__file__).parent;root=tmp_path/'sources';root.mkdir()
    assert len(RAW_RUNTIME_PATHS)==64
    assert 'thermal_model/installed_shade_score_registration.py' not in RAW_RUNTIME_PATHS
    assert 'thermal_model/installed_shade_score_jobs.py' not in RAW_RUNTIME_PATHS
    for name in RAW_RUNTIME_PATHS:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((source/name).read_bytes())
    code=r'''
import json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
import thermal_installed_intel as cli
from thermal_model import installed_shade_live_inputs as inputs,installed_shade_live as live,installed_shade_published_origin as captures
root=Path(sys.argv[2]);root.mkdir(mode=0o700)
def save(name,value):
    path=root/name;path.write_text(json.dumps(value));path.chmod(0o600);return path
record=dict(numeric_capture=dict(issued_at='2026-11-01T18:00:00+00:00',candidate=dict(artifact_sha256='a'*64),runtime=dict(test='routing'),source_epochs=dict(air='air',mass='mass',outdoor='outdoor')))
origin=save('original.installed-shade-origin-v13.json',record)
queues={str(h):str(save(str(h)+'.json',dict(schema='earthship-installed-score-jobs/v4',jobs=[]))) for h in (1,6,12,24)}
registration=save('registry.json',dict(schema='earthship-installed-score-registration/v1',candidate=None,queues=queues))
settings=dict(release_inputs_path=root/'refs',evidence_directory=root)
inputs.load_compressed_live_settings=lambda _:settings
inputs.CompressedSourceLiveBackend=lambda *a,**kw:object()
live.run_compressed_live_cycle=lambda **kw:dict(status='published',delivery_verified=True,capture_path=str(origin))
captures.read_compressed_calibrated_publication_capture=lambda _:record
args=SimpleNamespace(contract_version=3,config=root/'config',publish=True,bootstrap_shadow=False,score_registration=registration)
assert cli._live(args)==0,'registered publisher could not run from its declared source closure'
updated=json.loads(registration.read_text())
assert updated['candidate']['artifact_sha256']=='a'*64
assert all(len(json.loads(Path(p).read_text())['jobs'])==1 for p in updated['queues'].values())
assert 'thermal_model.installed_shade_score_jobs' not in sys.modules
assert 'thermal_model.installed_shade_score_registration' not in sys.modules
'''
    result=subprocess.run([sys.executable,'-I','-c',code,str(root),str(tmp_path/'private')],cwd=tmp_path,capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stdout+result.stderr
