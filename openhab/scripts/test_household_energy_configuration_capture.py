"""Fixed bounded configuration reads preserve original bytes and source absence."""
import importlib,json,os
from datetime import timedelta
from pathlib import Path
import pytest
from test_household_energy_configuration import BANK,TOPOLOGY,AT


def api():return importlib.import_module('household.energy_configuration_capture')


def files(tmp_path,monkeypatch):
    paths={'bank_source':tmp_path/'system-epochs.json','load_topology_source':tmp_path/'ac-evidence.json'}
    for key,value in [('bank_source',BANK),('load_topology_source',TOPOLOGY)]:
        paths[key].write_text(json.dumps(value,indent=2));paths[key].chmod(0o664)
    monkeypatch.setattr(api(),'FIXED_PATHS',paths)
    return paths


def test_capture_retains_exact_owned_originals_and_permissions(tmp_path,monkeypatch):
    paths=files(tmp_path,monkeypatch);before={key:(p.read_bytes(),p.stat().st_mode) for key,p in paths.items()}
    context=api().collect_configuration(clock=lambda:AT,monotonic=lambda:0.)
    for key,p in paths.items():
        assert context.to_dict()[key]['raw'].encode()==before[key][0]
        assert p.stat().st_mode==before[key][1]
    assert context.to_dict()['as_of']==AT.isoformat() and context.to_dict()['created_at']==AT.isoformat()


@pytest.mark.parametrize('damage',['missing_bank','missing_topology','empty_bank','empty_topology','invalid_topology'])
def test_independent_missing_or_invalid_files_preserve_other_source(damage,tmp_path,monkeypatch):
    from household.energy_configuration import project_energy_configuration
    paths=files(tmp_path,monkeypatch)
    if damage=='missing_bank':paths['bank_source'].unlink()
    elif damage=='missing_topology':paths['load_topology_source'].unlink()
    elif damage=='empty_bank':paths['bank_source'].write_bytes(b'')
    elif damage=='empty_topology':paths['load_topology_source'].write_bytes(b'')
    else:paths['load_topology_source'].write_text('invalid JSON')
    context=api().collect_configuration(clock=lambda:AT,monotonic=lambda:0.);out=project_energy_configuration(context)
    key='bank' if damage in ('missing_bank','empty_bank') else 'load_topology'
    assert out[key]['status']=='unavailable'
    assert out['load_topology' if key=='bank' else 'bank']['status']!='unavailable'
    if damage=='empty_bank':assert context.to_dict()['bank_source']['raw']==''


@pytest.mark.parametrize('damage',['symlink','oversize','directory','invalid_utf8'])
def test_unsafe_or_unrepresentable_file_refuses_capture(damage,tmp_path,monkeypatch):
    paths=files(tmp_path,monkeypatch);p=paths['bank_source']
    if damage=='symlink':p.unlink();p.symlink_to(paths['load_topology_source'])
    elif damage=='oversize':p.write_bytes(b'x'*65537)
    elif damage=='directory':p.unlink();p.mkdir()
    else:p.write_bytes(b'\xff')
    with pytest.raises(ValueError):api().collect_configuration(clock=lambda:AT,monotonic=lambda:0.)


@pytest.mark.parametrize('damage',['replacement','content','missing_appears','permissions'])
def test_file_change_during_collection_cannot_be_sealed(damage,tmp_path,monkeypatch):
    paths=files(tmp_path,monkeypatch);p=paths['bank_source']
    if damage=='missing_appears':p.unlink()
    calls=0
    def clock():
        nonlocal calls
        calls+=1
        # First clock is collection start; second is bank availability, after
        # its initial read. The later identity/content read must catch this.
        if calls==2:
            if damage=='replacement':
                q=tmp_path/'replacement';q.write_text(json.dumps(BANK));q.chmod(0o664);os.replace(q,p)
            elif damage=='content':p.write_text('changed')
            elif damage=='missing_appears':p.write_text(json.dumps(BANK))
            else:p.chmod(0o600)
        return AT
    with pytest.raises(ValueError):api().collect_configuration(clock=clock,monotonic=lambda:0.)


def test_outer_collection_deadline_is_never_renewed(tmp_path,monkeypatch):
    files(tmp_path,monkeypatch);calls=0
    def remaining():
        nonlocal calls
        calls+=1
        return 0. if calls>=3 else 1.
    with pytest.raises(ValueError):api().collect_configuration(clock=lambda:AT,remaining=remaining)
    assert calls==3


def test_wall_clock_regression_is_refused(tmp_path,monkeypatch):
    files(tmp_path,monkeypatch);values=iter([AT,AT,AT,AT-timedelta(seconds=1)])
    with pytest.raises(ValueError):api().collect_configuration(clock=lambda:next(values),monotonic=lambda:0.)


def test_cli_configuration_only_preserves_original_v1_mode_requirements(tmp_path,monkeypatch,capsys):
    files(tmp_path,monkeypatch)
    import household_capture
    assert household_capture.main(['--configuration-only'])==0
    out=json.loads(capsys.readouterr().out)
    assert out['schema']=='earthship-household-energy-configuration/v1'
    with pytest.raises(SystemExit):household_capture.main([])


def test_external_deadline_cannot_disable_local_monotonic_limit(tmp_path,monkeypatch):
    files(tmp_path,monkeypatch);values=iter([0.,16.])
    with pytest.raises(ValueError):api().collect_configuration(clock=lambda:AT,monotonic=lambda:next(values),remaining=lambda:1.)
