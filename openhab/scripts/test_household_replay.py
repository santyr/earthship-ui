"""Frozen original inputs replay offline, with source and runtime drift refusal."""
import importlib
import json
from hashlib import sha256
from pathlib import Path
import subprocess,sys
import pytest
from test_forecast_pre_dusk import evidence,NOW
from test_household_capabilities import originals


def bundle():
    raw=evidence()
    return dict(schema='earthship-household-inputs/v1',as_of=NOW.isoformat(),created_at=NOW.isoformat(),
                policy=dict(requirements={'battery_display':['battery_soc'],'thermal_forecast':['air_temperature','mass_temperature','outdoor_temperature']},
                            max_age_seconds={'battery_soc':120},max_skew_seconds=60),
                sources=[dict(kind='battery_soc',source_role='battery_soc',source_identity='original-bms',
                              expected_epoch='00000000-0000-0000-0000-000000000001',expected_sha256=sha256(raw.encode()).hexdigest(),
                              persisted_at=NOW.isoformat(),raw=raw)])


def api():
    assert importlib.util.find_spec('household.replay') is not None,'offline foundation replay missing'
    return importlib.import_module('household.replay')


def build(document=None,runtime=None):
    managed,ownership=originals()
    return api().compile_inputs(bundle() if document is None else document,managed=managed,ownership=ownership,
                                code_revision='c'*40,runtime_manifest={'synthetic.py':'d'*64} if runtime is None else runtime)


def test_identical_originals_replay_to_identical_sealed_receipt():
    original=build();assert build()==original
    assert original['snapshot']['completeness']=={'battery_display':True,'thermal_forecast':False}
    assert original['automatic_actuation'] is False
    assert original['registry']['descriptiveOnly'] is True
    assert api().verify_replay(original,build())==original['receipt_sha256']


@pytest.mark.parametrize('damage',['source','policy','runtime','registry','extra','duplicate','size'])
def test_changed_source_or_context_cannot_reuse_original_receipt(damage):
    original=build();document=bundle();managed,ownership=originals();runtime={'synthetic.py':'d'*64}
    if damage=='source':document['sources'][0]['raw']+=' '
    elif damage=='policy':document['policy']['max_skew_seconds']=59
    elif damage=='runtime':runtime['synthetic.py']='e'*64
    elif damage=='registry':ownership['policy']='changed policy'
    elif damage=='extra':document['token_file']='/private/credential'
    elif damage=='duplicate':document['sources']*=2
    else:document['sources'][0]['raw']='x'*(1024*1024+1)
    with pytest.raises(ValueError):
        result=api().compile_inputs(document,managed=managed,ownership=ownership,code_revision='c'*40,runtime_manifest=runtime)
        api().verify_replay(original,result)


def test_cli_reads_local_files_and_compares_original_without_writes(tmp_path):
    api();script=Path(__file__).with_name('household_snapshot.py')
    source=tmp_path/'inputs.json';source.write_text(json.dumps(bundle()));source.chmod(0o600)
    first=subprocess.run([sys.executable,str(script),'--input',str(source)],capture_output=True,text=True,timeout=20)
    assert first.returncode==0,first.stderr
    original=tmp_path/'receipt.json';original.write_text(first.stdout);original.chmod(0o600)
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result=subprocess.run([sys.executable,str(script),'--input',str(source),'--expect',str(original)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0 and json.loads(result.stdout)==json.loads(first.stdout)
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before
    document=bundle();document['authorization']='private-credential-must-not-be-echoed';source.write_text(json.dumps(document))
    refused=subprocess.run([sys.executable,str(script),'--input',str(source)],capture_output=True,text=True,timeout=20)
    assert refused.returncode!=0 and 'private-credential' not in refused.stdout+refused.stderr and 'Traceback' not in refused.stderr
