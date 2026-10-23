"""Current-power baselines retain original sources without qualifying a forecast."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import importlib
import pytest
from household.codec import canonical,loads
from household.control_contracts import instant
from test_household_energy_source_pipeline import make
from test_household_model_snapshot import source_at
from household.power_snapshot import compile_power_inputs


def metric(at,**changes):
    raw=canonical(dict(version=1,sources=[dict(canonical_name='battery.dc_power_w',item_name='DCData_Native_Power',
        canonical_unit='W',raw_unit='W',scale=1.,sign='positive_charging')])).decode()
    return dict(schema='earthship-household-battery-metric-source/v1',source_identity='Solar_PV/config/metric-sources.json',
        raw=raw,sha256=sha256(raw.encode()).hexdigest(),available_at=at.isoformat(),**changes)


def fixture(tmp_path,monkeypatch,*,watts=-500,old=False,skew=None,bank_raw="default",missing_power=False):
    def source(at):
        original=source_at(at);v=deepcopy(original['inputs']);bundle=v['bundle'];row=bundle['power_sources'][0]
        bundle['base_inputs']['sources'][0]['source_identity']='BMS_SOC_Evidence_JSON'
        raw=loads(row['raw']);raw['fields']['battery.dc_power_w']['watts']=watts
        row['raw']=canonical(raw).decode();row['expected_sha256']=sha256(row['raw'].encode()).hexdigest()
        if old:bundle['power_policy']['max_age_seconds']['battery_power_w']=1
        if skew is not None:bundle['power_policy']['max_skew_seconds']=skew
        if missing_power:
            bundle['power_sources']=[row for row in bundle['power_sources'] if row['kind']!='power']
            bundle['power_policy']['max_age_seconds'].pop('battery_power_w')
        return compile_power_inputs(bundle,managed=v['managed'],ownership=v['ownership'],code_revision=v['code_revision'],runtime_manifest=original['runtime_manifest'])
    snap,_,_,_=make(tmp_path,monkeypatch,source=source,bank_raw=bank_raw);at=instant(snap.to_dict()['as_of'])
    return snap,metric(at-timedelta(seconds=1)),instant(snap.to_dict()['created_at'])


def project(snap,source,now,hours=24):
    module=importlib.import_module('household.energy_persistence')
    return module.project_persistence(snapshot=snap,metric_source=source,horizon_hours=hours,now=now)


@pytest.mark.parametrize('hours',[6,12,24])
def test_nominal_discharge_uses_hourly_net_power_and_original_common_clock(tmp_path,monkeypatch,hours):
    snap,source,now=fixture(tmp_path,monkeypatch);out=project(snap,source,now,hours)
    assert out['reason'] is None,out['reason']
    assert out['status']=='projected_nominal_baseline' and len(out['trajectory'])==hours+1
    assert out['nominal_bank_kwh']==20.48 and out['battery_power_w']==-500
    first,third=out['trajectory'][0],out['trajectory'][3]
    assert third['nominal_energy_kwh']-first['nominal_energy_kwh']==pytest.approx(-1.5)
    assert third['nominal_soc_pct']-first['nominal_soc_pct']==pytest.approx(-7.32421875)
    assert instant(third['at'])==instant(snap.to_dict()['as_of'])+timedelta(hours=3)
    assert out['physical_calibration_qualified'] is False and out['automatic_actuation'] is False
    assert out['forecast_forcing_qualified'] is False and out['confidence']=='unavailable'
    assert out['metric_source_sha256']==sha256(canonical(source)).hexdigest()


@pytest.mark.parametrize('watts,want_soc,overflow',[(32767,100.,'above_capacity_nominal_kwh'),(-32767,0.,'below_zero_nominal_kwh')])
def test_saturation_preserves_out_of_range_nominal_energy_without_claiming_physical_supply(tmp_path,monkeypatch,watts,want_soc,overflow):
    snap,source,now=fixture(tmp_path,monkeypatch,watts=watts);out=project(snap,source,now,6)
    assert out['trajectory'][1]['nominal_soc_pct']==want_soc
    assert out['trajectory'][1][overflow]>0
    assert all(0<=row['nominal_soc_pct']<=100 for row in out['trajectory'])


def test_zero_power_holds_state_and_results_are_independent_copies(tmp_path,monkeypatch):
    snap,source,now=fixture(tmp_path,monkeypatch,watts=0);out=project(snap,source,now)
    assert all(row['nominal_soc_pct']==snap.to_dict()['domains']['energy']['battery_soc']['value'] for row in out['trajectory'])
    out['trajectory'][0]['nominal_soc_pct']=0
    assert project(snap,source,now)['trajectory'][0]['nominal_soc_pct']!=0


@pytest.mark.parametrize('hours',[True,0,1,48])
def test_unsupported_horizon_refuses(tmp_path,monkeypatch,hours):
    snap,source,now=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):project(snap,source,now,hours)


@pytest.mark.parametrize('damage',['hash','future','identity','duplicate_json'])
def test_changed_or_ambiguous_metric_original_refuses(tmp_path,monkeypatch,damage):
    snap,source,now=fixture(tmp_path,monkeypatch)
    if damage=='hash':source['sha256']='f'*64
    elif damage=='future':source['available_at']=(now+timedelta(seconds=1)).isoformat()
    elif damage=='identity':source['source_identity']='unrelated'
    else:
        source['raw']='{"version":1,"sources":[],"sources":[]}'
        source['sha256']=sha256(source['raw'].encode()).hexdigest()
    with pytest.raises(ValueError):project(snap,source,now)


@pytest.mark.parametrize('damage',['missing','sign','unit','old_power','expired'])
def test_missing_unsupported_or_stale_source_withholds_only_baseline(tmp_path,monkeypatch,damage):
    snap,source,now=fixture(tmp_path,monkeypatch,old=damage=='old_power')
    if damage=='missing':source=None
    elif damage in ('sign','unit'):
        body=loads(source['raw']);body['sources'][0]['sign' if damage=='sign' else 'canonical_unit']='unsupported'
        source['raw']=canonical(body).decode();source['sha256']=sha256(source['raw'].encode()).hexdigest()
    elif damage=='expired':now+=timedelta(seconds=121)
    out=project(snap,source,now)
    assert out['status']=='unavailable' and out['trajectory']==[]
    assert out['physical_calibration_qualified'] is False and out['automatic_actuation'] is False


def test_frozen_projection_needs_no_files_database_or_network(tmp_path,monkeypatch):
    snap,source,now=fixture(tmp_path,monkeypatch);out=project(snap,source,now)
    import builtins,psycopg2,urllib.request
    def forbidden(*a,**kw):pytest.fail('I/O at pure energy baseline boundary')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden);monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    assert project(snap,source,now)==out


def pipeline_fixture(tmp_path,monkeypatch,*,missing=False):
    from household.measured_weather import prepare_measured_weather
    from household.measured_weather_snapshot import bind_measured_weather_snapshot
    from test_household_measured_weather import sources
    from test_household_model_pipeline import run
    from household_pipeline import pipeline_runtime_manifest
    snap,source,now=fixture(tmp_path,monkeypatch);at=instant(snap.to_dict()['as_of'])
    runtime=pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
    v=snap.source_receipt['inputs']
    power=compile_power_inputs(v['bundle'],managed=v['managed'],ownership=v['ownership'],code_revision=v['code_revision'],runtime_manifest=runtime)
    measured=prepare_measured_weather(sources=sources(at),as_of=at,created_at=at)
    snapshot=bind_measured_weather_snapshot(source_receipt=power,source_runtime_manifest=runtime,weather_context=snap.weather,
        energy_configuration=snap.energy_configuration,measured_weather=measured,code_revision='e'*40)
    thermal=snapshot.weather.prepared
    old=run(snapshot,thermal,runtime_manifest=runtime)
    new=run(snapshot,thermal,runtime_manifest=runtime,energy_persistence_source=None if missing else source)
    return old,new,runtime,thermal


@pytest.mark.parametrize('missing',[False,True])
def test_versioned_pipeline_retains_daily_math_and_replays_conditional_baseline(tmp_path,monkeypatch,missing):
    from household.pipeline import replay_pipeline
    old,new,runtime,thermal=pipeline_fixture(tmp_path,monkeypatch,missing=missing)
    assert old['schema']=='earthship-household-model-plan-receipt/v5'
    assert new['schema']=='earthship-household-model-plan-receipt/v6'
    assert new['output']['projections']['energy']==old['output']['projections']['energy']
    assert new['output']['projections']['thermal']==old['output']['projections']['thermal']
    out=new['output']['projections']['energy_persistence']
    assert out['status']==('unavailable' if missing else 'projected_nominal_baseline')
    assert new['output']['plan_receipt']['plan']['reserve_checks']['baseline_floor_soc'] is None
    assert replay_pipeline(new,runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])==new
    assert replay_pipeline(old,runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])==old


def test_private_cli_and_observer_replay_new_baseline_source_closure(tmp_path,monkeypatch,capsys):
    import household_pipeline,household_observation
    from household_outcomes import original_plan_runtime,outcome_runtime_manifest
    _,record,runtime,thermal=pipeline_fixture(tmp_path,monkeypatch)
    path=tmp_path/'new-pipeline.json';path.write_bytes(canonical(record));path.chmod(0o600)
    assert household_pipeline.main(['--receipt',str(path)])==0
    assert loads(capsys.readouterr().out)==record
    assert original_plan_runtime(record,actual=outcome_runtime_manifest())==runtime
    target=tmp_path/'cache.json'
    result=household_observation.materialize(path,target,clock=lambda:instant(record['inputs']['now']),publication_guard=lambda:None)
    assert result['status']=='observation_written'
    assert loads(target.read_bytes())['receipt_sha256']==record['receipt_sha256']


def test_resealed_baseline_output_or_source_change_cannot_survive_replay(tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    from household.codec import identity
    _,record,runtime,thermal=pipeline_fixture(tmp_path,monkeypatch)
    for kind in ('output','source'):
        bad=deepcopy(record)
        if kind=='output':bad['output']['projections']['energy_persistence']['trajectory'][1]['nominal_soc_pct']=99
        else:bad['inputs']['energy_persistence_source']['sha256']='f'*64
        bad['receipt_sha256']=identity({k:v for k,v in bad.items() if k!='receipt_sha256'})
        with pytest.raises(ValueError):replay_pipeline(bad,runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])


def test_real_cycle_version_binds_preissue_metric_original(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from household_cycle import derive_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch);issue=instant(capture['issued_at']);source=metric(issue-timedelta(seconds=2))
    args['originals'].update(schema='earthship-household-cycle-sources/v5',daily_energy_source=None,owner_source=None,policy_source=None,energy_persistence_source=source)
    record=derive_cycle(**args)
    assert record['schema']=='earthship-household-model-plan-receipt/v7'
    assert record['inputs']['energy_persistence_source']==source
    assert record['output']['projections']['thermal']['output']==capture['output']
    args['originals']['energy_persistence_source']['available_at']=issue.isoformat()
    with pytest.raises(ValueError):derive_cycle(**args)


def test_collector_retains_fixed_metric_original_and_refuses_midcycle_change(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    from local_measurement_test_support import NOW
    raw=metric(NOW)['raw']
    collector,_,calls,_,now=collector_fixture(tmp_path,monkeypatch,metric_raw=raw)
    out=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert out['schema']=='earthship-household-cycle-sources/v8'
    assert out['energy_persistence_source']['raw']==raw
    assert out['energy_persistence_source']['available_at']==now.isoformat()
    reader=collector.owner_reader
    def changed(*args,**kwargs):
        value=reader(*args,**kwargs)
        (tmp_path/'metric-sources.json').write_text(raw+' ')
        return value
    collector.owner_reader=changed
    with pytest.raises(ValueError):collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)


def test_optional_bad_metric_configuration_preserves_other_source_domains(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch,metric_raw='{"sources":[],"sources":[]}')
    out=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert out['energy_persistence_source'] is None
    assert out['power_receipt']['automatic_actuation'] is False and out['energy_configuration'] is not None


def test_skewed_individually_valid_inputs_do_not_form_a_baseline(tmp_path,monkeypatch):
    snap,source,now=fixture(tmp_path,monkeypatch,skew=1)
    assert snap.to_dict()['domains']['energy']['battery_power_w']['value']==-500
    out=project(snap,source,now)
    assert out['status']=='unavailable' and out['reason']=='source_skew'


def test_declared_bank_window_must_cover_entire_baseline_horizon(tmp_path,monkeypatch):
    from test_household_energy_configuration import BANK
    bank=deepcopy(BANK)
    from test_native_thermal_forecast import ISSUE
    from zoneinfo import ZoneInfo
    end=(ISSUE.astimezone(ZoneInfo('America/Denver')).date()+timedelta(days=1)).isoformat()
    next(row for row in bank['epochs'] if row['current_analytics'])['end_local_date_exclusive']=end
    snap,source,now=fixture(tmp_path,monkeypatch,bank_raw=canonical(bank).decode())
    assert project(snap,source,now,6)['status']=='projected_nominal_baseline'
    out=project(snap,source,now,24)
    assert out['status']=='unavailable' and out['reason']=='bank_window_does_not_cover_horizon'


def test_missing_nominal_capacity_stays_unknown(tmp_path,monkeypatch):
    snap,source,now=fixture(tmp_path,monkeypatch,bank_raw=None)
    out=project(snap,source,now)
    assert out['status']=='unavailable' and out['reason']=='nominal_capacity_unavailable'


def test_new_pipeline_cannot_omit_its_baseline_runtime_dependency(tmp_path,monkeypatch):
    from household_pipeline import verify_source_closure
    _,record,runtime,_=pipeline_fixture(tmp_path,monkeypatch)
    record['runtime_manifest'].pop('openhab/scripts/household/energy_persistence.py')
    with pytest.raises(ValueError):verify_source_closure(record,runtime)


def test_absent_power_source_without_age_policy_withholds_only_baseline(tmp_path,monkeypatch):
    snap,source,now=fixture(tmp_path,monkeypatch,missing_power=True)
    assert 'battery_power_w' not in snap.to_dict()['temporal_policy']['max_age_seconds']
    out=project(snap,source,now)
    assert out['status']=='unavailable' and out['reason']=='required_source_unavailable'
    assert out['trajectory']==[] and out['automatic_actuation'] is False
