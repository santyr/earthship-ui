"""Receipt-family handoff/owned-file installation; no real unit manager calls."""
from pathlib import Path
import json
import pytest
from test_native_serving_selection import stage
from test_household_cycle_deploy import write


def fixture(tmp_path,monkeypatch):
    deploy,args,settings,helper,libraries,pin=stage(tmp_path,monkeypatch)
    import household_native_family as family,household_native_handoff as handoff
    output=tmp_path/'family';family.prepare(args['stage'],libraries,output,guard=lambda:None,deployment_sha256=pin)
    dispatch=json.loads(args['score_dispatch_path'].read_bytes());previous=Path(dispatch['legacy']['stage']);config=Path(dispatch['legacy']['config'])
    root=args['service_file'].parent
    old_forecast=(previous/'service.conf').read_bytes();old_score=handoff._score_override(previous,config)
    write(root/'thermal-provisional-forecast.service.d/zzzz-household-cycle.conf',old_forecast)
    write(root/'thermal-provisional-score.service.d/zzzz-household-score.conf',old_score)
    for name in ('thermal-provisional-forecast.service.d','thermal-provisional-score.service.d'):(root/name).chmod(0o700)
    caps='\n'.join(k+'='+('60' if k=='TimeoutStartSec' else v) for k,v in deploy.LIMITS.items())
    write(root/'thermal-provisional-score.service',('[Service]\n'+caps+'\n').encode(),0o644)
    write(root/'thermal-provisional-forecast.timer',b'[Timer]\nOnCalendar=*-*-* *:04/5:45 UTC\n',0o644)
    write(root/'thermal-provisional-score.timer',('[Timer]\n'+''.join('OnCalendar=*-*-* *:'+v+'/5:10 UTC\n' for v in ('00','01','02','03'))).encode(),0o644)
    def definition(path):return {'FragmentPath':str(path),'DropInPaths':' '.join(str(p) for p in (root/(path.name+'.d')).glob('*.conf'))}
    monkeypatch.setattr(handoff,'_unit_definition',definition)
    def state(path):
        raw=old_forecast if path.name=='thermal-provisional-forecast.service' else old_score
        command=[line[10:] for line in raw.decode().splitlines() if line.startswith('ExecStart=') and line!='ExecStart='][0]
        return dict(deploy.EFFECTIVE_LIMITS,ExecStart=command,ActiveState='inactive',MainPID='0')
    monkeypatch.setattr(deploy,'_service_state',state)
    return deploy,handoff,args,previous,output,tmp_path/'handoff',pin,old_forecast,old_score


def test_handoff_retains_legacy_score_selection_and_pinned_family_forecast(tmp_path,monkeypatch):
    deploy,handoff,args,previous,family,output,pin,old_forecast,old_score=fixture(tmp_path,monkeypatch)
    handoff.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=output,guard=lambda:None)
    record=handoff.verify(output,guard=lambda:None)
    assert record['deployment_sha256']==pin
    assert record['model_verification']['receipt']['sha256']==args['model_receipt_sha256']
    assert record['score_dispatch']['sha256']==args['score_dispatch_sha256']
    desired=record['changes']['forecast']['desired']['path']
    assert desired==str(family/'forecast.conf') and ('--deployment-sha256 '+pin).encode() in Path(desired).read_bytes()
    assert '--deployment-sha256' not in (args['stage']/'service.conf').read_text()


def test_receipt_file_installation_keeps_all_five_owned_changes_and_no_reload(tmp_path,monkeypatch):
    deploy,handoff,args,previous,family,output,pin,old_forecast,old_score=fixture(tmp_path,monkeypatch)
    handoff.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=output,guard=lambda:None)
    import household_native_install as install
    result=install._install_files(output,guard=lambda:None)
    assert result['file_count']==5 and result['unit_manager_reloaded'] is False and result['service_restarted'] is False
    actual=args['service_file'].parent/'thermal-provisional-forecast.service.d/zzzz-household-cycle.conf'
    assert actual.read_bytes()==(family/'forecast.conf').read_bytes()


def test_receipt_partial_file_install_restores_original_owned_overrides(tmp_path,monkeypatch):
    deploy,handoff,args,previous,family,output,pin,old_forecast,old_score=fixture(tmp_path,monkeypatch)
    handoff.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=output,guard=lambda:None)
    import household_native_install as install
    original=deploy._replace_owned;calls=[]
    def fail_second(target,expected,replacement):
        calls.append(target)
        if len(calls)==2:raise ValueError('fixture partial replacement refusal')
        return original(target,expected,replacement)
    monkeypatch.setattr(deploy,'_replace_owned',fail_second)
    with pytest.raises(ValueError,match='fixture partial replacement refusal'):install._install_files(output,guard=lambda:None)
    root=args['service_file'].parent
    assert (root/'thermal-provisional-forecast.service.d/zzzz-household-cycle.conf').read_bytes()==old_forecast
    assert (root/'thermal-provisional-score.service.d/zzzz-household-score.conf').read_bytes()==old_score
    assert not (root/'thermal-native-geometry-prepare.service').exists()


@pytest.mark.parametrize('joint',[False,True])
def test_runtime_migration_handoff_preserves_old_contract_but_accepts_joint_receipt_family(tmp_path,monkeypatch,joint):
    deploy,handoff,args,previous,family,output,pin,_,_=fixture(tmp_path,monkeypatch)
    settings=json.loads(args['forecast_config'].read_bytes());candidate_path=Path(settings['candidate_path'])
    original_bytes=deploy._bytes;original_verify=deploy.verify_stage
    def owned_bytes(path,**kwargs):
        raw=original_bytes(path,**kwargs)
        if Path(path)==candidate_path:
            model=json.loads(raw);model['runtime']['base_runtime']['code_revision']='c'*64
            if joint:
                model['schema']='earthship-provisional-thermal-candidate/v3'
                model['fit']={'schema':'earthship-native-solar-provisional-fit/v2','model_rule':'earthship-native-joint-shade-dynamics/v3'}
            return json.dumps(model).encode()
        return raw
    def verified_stage(path,**kwargs):
        record=original_verify(path,**kwargs)
        if Path(path)==args['stage']:
            record['protected_runtime_sources']={**record['protected_runtime_sources'],'new-versioned-selector.py':'d'*64}
        return record
    # Package/admission is covered separately. Here supply already verified
    # differing runtime headers to exercise the complete handoff boundary.
    monkeypatch.setattr(deploy,'verify_stage',verified_stage)
    # Restrict the substituted bytes to the direct candidate reads in handoff.
    import inspect
    def scoped_bytes(path,**kwargs):
        if inspect.currentframe().f_back.f_code.co_name=='_assemble':return owned_bytes(path,**kwargs)
        return original_bytes(path,**kwargs)
    monkeypatch.setattr(deploy,'_bytes',scoped_bytes)
    if not joint:
        with pytest.raises(ValueError):handoff.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=output,guard=lambda:None)
    else:
        handoff.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=output,guard=lambda:None)
        assert handoff.verify(output,guard=lambda:None)['automatic_actuation'] is False
