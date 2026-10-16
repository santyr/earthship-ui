"""As-issued learned demand and storage are compared against original references."""
from datetime import timedelta
from copy import deepcopy
import importlib
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_household_solar_outcomes import context,originals
from test_household_profiled_forecast import supported_source
from test_household_ac_load_sources import raw


def case(tmp_path,monkeypatch,originals):
    _,old=context(tmp_path,monkeypatch,originals)
    import household_profiled_forecast as forecasts
    from household_ac_load_window import build_hour_source
    issue=instant(old['forecast_receipt']['output']['array_pv']['origin']);source,lr=supported_source(issue)
    forecast=forecasts.seal_profiled_forecast(energy_receipt=old['forecast_receipt'],plan_receipt=old['plan_receipt'],load_source=source,
        now=instant(old['forecast_receipt']['inputs']['assessed_at']),runtime_manifest=forecasts.profiled_runtime_manifest(),energy_runtime_manifest=old['forecast_runtime_manifest'],load_runtime_manifest=lr)
    rows=[(issue+timedelta(seconds=30*i),raw(issue+timedelta(seconds=30*i),i+1)) for i in range(120)]
    target=issue+timedelta(hours=1);now=old['assessed_at']
    hour=build_hour_source(rows=rows,start=issue,end=target,requested_at=now-timedelta(seconds=2),received_at=now-timedelta(seconds=1),item_id=613)
    api=importlib.import_module('household_profiled_outcomes')
    args=dict(profiled_receipt=forecast,energy_receipt=old['forecast_receipt'],plan_receipt=old['plan_receipt'],hour_sources={'1':hour},endpoint_sources=old['endpoint_sources'],assessed_at=now,
        runtime_manifest=api.outcome_runtime_manifest(),forecast_runtime_manifest=forecasts.profiled_runtime_manifest(),energy_runtime_manifest=old['forecast_runtime_manifest'],load_runtime_manifest=lr)
    return api,args


def test_identical_original_targets_compare_load_energy_and_all_storage_references(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals);before=canonical(args['profiled_receipt']);value=api.seal_profiled_outcomes(**args)
    load=value['output']['load_by_horizon']['1'];soc=value['output']['soc_by_horizon']['1']
    assert load['status']=='scored' and load['coverage']==1 and load['actual_known_ac_kwh']==pytest.approx(1)
    assert load['errors_kwh']['current_load']==pytest.approx(0,abs=1e-12) and load['errors_kwh']['profiled_load']==pytest.approx(args['profiled_receipt']['output']['load_forecast']['trajectory'][0]['ac_kwh']-1)
    assert soc['actual_soc_pct']==95 and soc['status']=='scored'
    assert set(soc['predictions_soc_pct'])=={'profiled_load_pv','constant_load_pv','constant_power','hold_soc'}
    assert soc['predictions_soc_pct']['profiled_load_pv']==args['profiled_receipt']['output']['profiled_storage']['trajectory'][0]['nominal_soc_pct']
    assert value['output']['load_by_horizon']['6']['status']=='not_mature' and value['output']['automatic_actuation'] is False
    assert canonical(args['profiled_receipt'])==before
    assert api.validate_score(value)==value
    assert api.replay_profiled_outcomes(value,**{k:v for k,v in args.items() if k not in {'hour_sources','endpoint_sources','assessed_at'}})==value


def test_missing_hour_is_excluded_while_SOC_can_still_be_scored(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals);args['hour_sources']={};value=api.seal_profiled_outcomes(**args)
    assert value['output']['load_by_horizon']['1']['status']=='pending_source'
    assert value['output']['load_by_horizon']['1']['errors_kwh'] is None
    assert value['output']['soc_by_horizon']['1']['status']=='scored'


def test_sparse_hour_is_not_zero_energy_or_a_complete_hour_accuracy_pair(tmp_path,monkeypatch,originals):
    api,args=case(tmp_path,monkeypatch,originals)
    from household_ac_load_window import build_hour_source
    source=args['hour_sources']['1'];start=instant(source['window_start']);end=instant(source['window_end'])
    args['hour_sources']['1']=build_hour_source(rows=[(start,raw(start))],start=start,end=end,requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=613)
    row=api.seal_profiled_outcomes(**args)['output']['load_by_horizon']['1']
    assert row['status']=='insufficient_coverage' and row['coverage']==30/3600 and row['actual_known_ac_kwh']==30/3600
    assert row['predictions_kwh'] is None and row['errors_kwh'] is None


@pytest.mark.parametrize('damage',['hour','errors','predictions','cohort','runtime'])
def test_original_or_resealed_derived_changes_refuse(tmp_path,monkeypatch,originals,damage):
    api,args=case(tmp_path,monkeypatch,originals);value=api.seal_profiled_outcomes(**args)
    if damage=='hour':value['inputs']['hour_sources']['1']['rows'][0][1]='changed original'
    elif damage=='errors':value['output']['load_by_horizon']['1']['errors_kwh']['current_load']=0.5
    elif damage=='predictions':value['output']['soc_by_horizon']['1']['predictions_soc_pct']['profiled_load_pv']=0
    elif damage=='cohort':value['output']['cohort']['load_policy_sha256']='f'*64
    else:value['runtime_manifest'][next(iter(value['runtime_manifest']))]='f'*64
    value['receipt_sha256']=identity({k:v for k,v in value.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api.replay_profiled_outcomes(value,**{k:v for k,v in args.items() if k not in {'hour_sources','endpoint_sources','assessed_at'}})


def test_full_compressed_outcome_CLI_replays_external_forecasts_and_plan(tmp_path,monkeypatch,originals,capsys):
    api,args=case(tmp_path,monkeypatch,originals);score=api.seal_profiled_outcomes(**args)
    import gzip,json
    receipt=tmp_path/'score.json.gz';receipt.write_bytes(gzip.compress(canonical(score),mtime=0));receipt.chmod(0o600)
    command=['--receipt',str(receipt)]
    for name,key in (('forecast','profiled_receipt'),('energy','energy_receipt'),('plan','plan_receipt')):
        path=tmp_path/(name+'.json');path.write_bytes(canonical(args[key]));path.chmod(0o600);command.extend(['--'+name,str(path)])
    assert api.main(command)==0 and json.loads(capsys.readouterr().out)==score
    receipt.write_bytes(gzip.compress(b'{}',mtime=0))
    assert api.main(command)==1 and 'replay refused' in capsys.readouterr().err
