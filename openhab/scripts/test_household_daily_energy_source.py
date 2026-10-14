"""Fresh daily arguments must retain their receipt and replay provenance."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import importlib
import json
import pytest
from household.codec import canonical
from household.energy_model import daily_energy_projection

NOW=datetime(2026,10,14,18,tzinfo=timezone.utc)


def source(at=NOW,*,resource=17.25):
    issued=at-timedelta(minutes=10);collected=at-timedelta(seconds=2)
    inputs=dict(resource_kwh=resource,direct_demand_kwh=5.1,soc_pct=78.,bank_kwh=20.48,
        eta_rt=.95,overnight_drops_pct=[12.,14.],tomorrow_cloud_pct=35.)
    output=daily_energy_projection(**inputs)
    day=at.astimezone(__import__('zoneinfo').ZoneInfo('America/Denver')).date().isoformat()
    receipt=dict(version=1,predictionDay=day,issuedAt=issued.isoformat(),pvTodayKwh=output['pv_pred'],
        curtailmentHoursToday=output['curtail'],overnightTroughSocPct=output['trough_pred'],
        energySocOrigin={'streamEpoch':'bms-test'},weatherInputSha256='c'*64)
    record=dict(temperature_issued_at=issued.isoformat(),household_energy_inputs=inputs,
        pv=output['pv_pred'],curtail=output['curtail'],trough=output['trough_pred'],
        soc_origin=receipt['energySocOrigin'],weather_origin={'sha256':'c'*64})
    raw=json.dumps(receipt)
    return dict(schema='earthship-household-daily-energy-source/v1',collected_at=collected.isoformat(),
        prediction_day=day,record=record,receipt_raw=raw,receipt_sha256=sha256(raw.encode()).hexdigest(),state_sha256='a'*64)


def api():return importlib.import_module('household.daily_energy_source')


def test_exact_daily_inputs_match_original_published_numbers():
    value=source();result=api().daily_inputs(value,as_of=NOW)
    assert result==value['record']['household_energy_inputs']
    result['overnight_drops_pct'].append(99)
    assert value['record']['household_energy_inputs']['overnight_drops_pct']==[12.,14.]


@pytest.mark.parametrize('damage',['stale','future_capture','future_issue','receipt_hash','prediction','state_input','origin','weather','nonfinite'])
def test_bad_or_wrong_day_source_is_not_a_current_energy_projection(damage):
    value=source()
    if damage=='stale':value=source(NOW-timedelta(days=1))
    elif damage=='future_capture':value['collected_at']=(NOW+timedelta(seconds=1)).isoformat()
    elif damage=='future_issue':value['record']['temperature_issued_at']=(NOW+timedelta(seconds=1)).isoformat()
    elif damage=='receipt_hash':value['receipt_sha256']='b'*64
    elif damage=='prediction':value['record']['trough']+=1
    elif damage=='state_input':value['record']['household_energy_inputs']['resource_kwh']=.1
    elif damage=='origin':value['record']['soc_origin']={'streamEpoch':'different'}
    elif damage=='weather':value['record']['weather_origin']['sha256']='d'*64
    else:value['record']['household_energy_inputs']['resource_kwh']=float('nan')
    with pytest.raises(ValueError):api().daily_inputs(value,as_of=NOW)


def test_cycle_prefers_fresh_daily_source_and_seals_it_for_replay(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from household.control_contracts import instant
    import household_cycle
    from household.pipeline import replay_pipeline
    args,capture=derived_fixture(tmp_path,monkeypatch)
    daily=source(instant(capture['issued_at']),resource=17.25)
    args['originals'].update(schema='earthship-household-cycle-sources/v2',daily_energy_source=daily)
    args['parameter_record']['record']['household_energy_inputs']['resource_kwh']=999.
    result=household_cycle.derive_cycle(**args)
    prepared=result['inputs']['energy_inputs']
    assert prepared['schema']=='earthship-household-prepared-energy/v3'
    assert prepared['daily_source']==daily
    assert prepared['numerical_inputs']['inputs']['resource_kwh']==17.25
    assert prepared['numerical_inputs']['inputs']['soc_pct']==result['inputs']['snapshot']['domains']['energy']['battery_soc']['value']
    assert result['output']['projections']['energy']['input_qualification']=='not_assessed'
    assert result['output']['automatic_actuation'] is False
    assert replay_pipeline(result,runtime_manifest=args['runtime_manifest'],thermal_runtime=args['thermal'].to_dict()['executing_runtime'])==result


def test_missing_daily_source_keeps_thermal_without_using_static_old_parameters(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    import household_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch)
    args['originals'].update(schema='earthship-household-cycle-sources/v2',daily_energy_source=None)
    result=household_cycle.derive_cycle(**args)
    assert result['inputs']['energy_inputs'] is None
    assert result['output']['projections']['energy'] is None
    assert result['output']['projections']['thermal']['output']==capture['output']


def test_live_collector_freezes_today_state_and_matching_owner_receipt(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    import household_cycle_sources as module
    collector,raw,calls,_,now=collector_fixture(tmp_path,monkeypatch)
    daily=source(now);state=tmp_path/'daily-state.json'
    state.write_bytes(canonical({'predictions':{daily['prediction_day']:daily['record']}}))
    state.chmod(0o664)  # Existing daily state is mutable and group-writable.
    monkeypatch.setattr(module,'DAILY_STATE_PATH',state,raising=False)
    raw['Forecast_Prediction_Receipt_JSON']=daily['receipt_raw']
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['schema']=='earthship-household-cycle-sources/v3'
    retained=result['daily_energy_source']
    assert retained['record']==daily['record']
    assert retained['receipt_raw']==daily['receipt_raw']
    assert retained['state_sha256']==sha256(state.read_bytes()).hexdigest()
    assert calls.count('Forecast_Prediction_Receipt_JSON')==1
    assert result['automatic_actuation'] is False


def test_bad_daily_publication_preserves_other_collected_evidence(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    import household_cycle_sources as module
    collector,raw,calls,_,now=collector_fixture(tmp_path,monkeypatch)
    daily=source(now);state=tmp_path/'daily-state.json'
    state.write_bytes(canonical({'predictions':{daily['prediction_day']:daily['record']}}))
    monkeypatch.setattr(module,'DAILY_STATE_PATH',state,raising=False)
    raw['Forecast_Prediction_Receipt_JSON']='UNDEF'
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['daily_energy_source'] is None
    assert result['power_receipt']['snapshot']['domains']['energy']['inverter_output_w']['value']==1000


def test_daily_capture_cannot_postdate_the_frozen_source_collection(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from household.control_contracts import instant
    import household_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch)
    daily=source(instant(capture['issued_at']))
    daily['collected_at']=(instant(args['originals']['captured_at'])+timedelta(microseconds=1)).isoformat()
    args['originals'].update(schema='earthship-household-cycle-sources/v2',daily_energy_source=daily)
    with pytest.raises(ValueError):household_cycle.derive_cycle(**args)


def test_missing_published_energy_fields_are_not_null_forecasts():
    value=source();inputs=value['record']['household_energy_inputs'];inputs['soc_pct']=None
    value['record'].update(pv=None,curtail=None,trough=None)
    receipt=json.loads(value['receipt_raw'])
    for key in ('pvTodayKwh','curtailmentHoursToday','overnightTroughSocPct'):receipt.pop(key)
    value['receipt_raw']=json.dumps(receipt);value['receipt_sha256']=sha256(value['receipt_raw'].encode()).hexdigest()
    with pytest.raises(ValueError):api().daily_inputs(value,as_of=NOW)


def test_sealed_daily_arguments_cannot_be_changed_independently(tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from household.control_contracts import instant
    from household.energy_model import PreparedEnergyInputs
    import household_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch)
    args['originals'].update(schema='earthship-household-cycle-sources/v2',daily_energy_source=source(instant(capture['issued_at'])))
    value=household_cycle.derive_cycle(**args)['inputs']['energy_inputs']
    value['numerical_inputs']['inputs']['tomorrow_cloud_pct']=99
    with pytest.raises(ValueError):PreparedEnergyInputs(canonical(value))


@pytest.mark.parametrize('tampered',[False,True])
def test_previous_local_day_source_keeps_thermal_but_not_corrupt_provenance(tampered,tmp_path,monkeypatch):
    from test_household_cycle import derived_fixture
    from household.control_contracts import instant
    import household_cycle
    args,capture=derived_fixture(tmp_path,monkeypatch)
    issue=instant(capture['issued_at'])
    daily=source(issue-timedelta(days=1))
    if tampered:daily['receipt_sha256']='d'*64
    args['originals'].update(schema='earthship-household-cycle-sources/v2',daily_energy_source=daily)
    if tampered:
        with pytest.raises(ValueError):household_cycle.derive_cycle(**args)
    else:
        result=household_cycle.derive_cycle(**args)
        assert result['inputs']['energy_inputs'] is None
        assert result['output']['projections']['energy'] is None
        assert result['output']['projections']['thermal']['output']==capture['output']
