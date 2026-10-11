"""Private replay CLI verifies actual dependency closure and sealed originals."""
import importlib,json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from household.codec import canonical,identity
from test_household_resources import original,scales,NOW,api


def cli():return importlib.import_module('household_resources')

def fixture(tmp_path):
    mod=cli();runtime=mod.resource_runtime_manifest();plan=original()
    # This fixture was originally created with exactly the full current closure.
    plan['runtime_manifest']=runtime
    plan['receipt_sha256']=identity({key:value for key,value in plan.items() if key!='receipt_sha256'})
    receipt=api().seal_resources(plan_receipt=plan,scales=scales(),orders=[],assessed_at=NOW,plan_runtime_manifest=runtime,analysis_runtime_manifest=runtime)
    path=tmp_path/'private.json';path.write_bytes(canonical(receipt));path.chmod(0o600)
    return mod,receipt,path,runtime


def test_private_cli_rederives_exact_receipt(tmp_path,capsys):
    mod,receipt,path,_=fixture(tmp_path)
    assert mod.main(['--receipt',str(path)])==0
    assert json.loads(capsys.readouterr().out)==receipt


@pytest.mark.parametrize('kind',['public','symlink','fifo'])
def test_cli_refuses_public_and_special_files(tmp_path,capsys,kind):
    mod,_,path,_=fixture(tmp_path)
    if kind=='public':path.chmod(0o644)
    elif kind=='symlink':link=tmp_path/'link';link.symlink_to(path);path=link
    else:path.unlink();os.mkfifo(path,0o600)
    assert mod.main(['--receipt',str(path)])==1
    result=capsys.readouterr();assert result.out=='' and 'invalid or changed original context' in result.err


def test_cli_refuses_incomplete_original_plan_closure(tmp_path,capsys):
    mod,receipt,path,runtime=fixture(tmp_path);plan=receipt['inputs']['plan_receipt'];plan['runtime_manifest'].pop('companion/earthship_energy/bms_evidence.py')
    plan['receipt_sha256']=identity({key:value for key,value in plan.items() if key!='receipt_sha256'})
    changed=api().seal_resources(plan_receipt=plan,scales=scales(),orders=[],assessed_at=NOW,plan_runtime_manifest=plan['runtime_manifest'],analysis_runtime_manifest=runtime)
    path.write_bytes(canonical(changed));assert mod.main(['--receipt',str(path)])==1
    assert capsys.readouterr().out==''


def test_cli_refuses_changed_runtime_before_output(tmp_path,capsys,monkeypatch):
    mod,_,path,runtime=fixture(tmp_path);calls=[]
    def manifest():
        calls.append(1)
        return runtime if len(calls)==1 else {**runtime,'openhab/scripts/household/resources.py':'f'*64}
    monkeypatch.setattr(mod,'resource_runtime_manifest',manifest)
    assert mod.main(['--receipt',str(path)])==1
    assert capsys.readouterr().out==''


def test_cli_refuses_future_assessment(tmp_path,capsys):
    mod,receipt,path,runtime=fixture(tmp_path)
    changed=api().seal_resources(plan_receipt=receipt['inputs']['plan_receipt'],scales=scales(),orders=[],assessed_at=datetime.now(timezone.utc)+timedelta(days=1),plan_runtime_manifest=runtime,analysis_runtime_manifest=runtime)
    path.write_bytes(canonical(changed));assert mod.main(['--receipt',str(path)])==1
    assert capsys.readouterr().out==''
