"""Storage flows must not inflate the household consumption learning target."""
from datetime import timedelta
from copy import deepcopy
import importlib
import pytest
from household.codec import canonical
from household.control_contracts import instant
from test_household_energy_persistence import fixture,metric as battery_metric


def api():return importlib.import_module('household.power_flows')


def project(*,snapshot,topology_source,now):
    at=instant(snapshot.to_dict()['as_of'])
    return api().project_power_flows(snapshot=snapshot,topology_source=topology_source,now=now,metric_source=battery_metric(at-timedelta(seconds=1)))


def declaration(at,**changes):
    value=dict(schema='earthship-household-load-topology/v1',confirmed_by='operator',
        confirmed_at=(at-timedelta(minutes=1)).isoformat(),effective_from=(at-timedelta(minutes=1)).isoformat(),
        effective_until=None,household_loads='ac_only',dc_loads='battery_and_solar_pv_system')
    value.update(changes)
    return api().prepare_topology_source(canonical(value),available_at=at-timedelta(seconds=1))


@pytest.mark.parametrize('watts,charge,discharge',[(500,500,0),(-500,0,500),(0,0,0)])
def test_battery_storage_does_not_change_household_consumption_target(tmp_path,monkeypatch,watts,charge,discharge):
    snap,_,now=fixture(tmp_path,monkeypatch,watts=watts);at=instant(snap.to_dict()['as_of'])
    out=project(snapshot=snap,topology_source=declaration(at),now=now)
    assert out['household_ac_load_w']==1000 and out['household_load_w']==1000
    assert out['battery_net_dc_w']==watts and out['battery_charge_w']==charge and out['battery_discharge_w']==discharge
    assert out['pv_controller_output_w']==1900
    assert out['system_dc_consumption_w'] is None and out['conversion_losses_w'] is None
    assert out['household_dc_scope']=='none_operator_declared'
    assert out['balance_closed'] is False and out['automatic_actuation'] is False
    assert out['physical_calibration_qualified'] is False
    assert out['source_evidence_sha256']['household_ac_load_w']==snap.to_dict()['domains']['energy']['estimated_load_w']['evidence']['digest']


def test_missing_dc_scope_confirmation_keeps_ac_and_storage_separate(tmp_path,monkeypatch):
    snap,_,now=fixture(tmp_path,monkeypatch,watts=500)
    out=project(snapshot=snap,topology_source=None,now=now)
    assert out['household_ac_load_w']==1000 and out['household_load_w'] is None
    assert out['battery_charge_w']==500 and out['household_dc_scope']=='unknown'
    assert out['reasons']['household_load_w']=='household_dc_scope_unavailable'


@pytest.mark.parametrize('damage',['expired','future_confirmation','unsupported','invalid_clock'])
def test_topology_declaration_only_applies_inside_its_original_window(tmp_path,monkeypatch,damage):
    snap,_,now=fixture(tmp_path,monkeypatch);at=instant(snap.to_dict()['as_of'])
    changes={'effective_until':at.isoformat()} if damage=='expired' else {'confirmed_at':(at+timedelta(seconds=1)).isoformat()} if damage=='future_confirmation' else {'household_loads':'unknown'}
    if damage=='invalid_clock':changes={'effective_from':'invalid clock'}
    source=declaration(at,**changes)
    out=project(snapshot=snap,topology_source=source,now=now)
    assert out['household_load_w'] is None and out['household_ac_load_w']==1000
    assert out['battery_discharge_w']==500


def test_expired_power_remains_unknown_instead_of_zero(tmp_path,monkeypatch):
    snap,_,now=fixture(tmp_path,monkeypatch);at=instant(snap.to_dict()['as_of'])
    out=project(snapshot=snap,topology_source=declaration(at),now=now+timedelta(seconds=121))
    assert all(out[k] is None for k in ('household_load_w','household_ac_load_w','battery_net_dc_w','battery_charge_w','battery_discharge_w','pv_controller_output_w'))
    assert out['status']=='unavailable'


@pytest.mark.parametrize('damage',['hash','identity','availability'])
def test_declared_original_cannot_be_substituted_or_arrive_after_issue(tmp_path,monkeypatch,damage):
    snap,_,now=fixture(tmp_path,monkeypatch);at=instant(snap.to_dict()['as_of']);source=declaration(at)
    if damage=='hash':source['sha256']='f'*64
    elif damage=='identity':source['source_identity']='another-topology.json'
    else:source['available_at']=(at+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):project(snapshot=snap,topology_source=source,now=now)


def test_inverter_measurement_is_not_household_load_without_original_ac_topology(tmp_path,monkeypatch):
    from test_household_energy_source_pipeline import make
    snap,_,_,_=make(tmp_path,monkeypatch,topology_raw=None);at=instant(snap.to_dict()['as_of']);now=instant(snap.to_dict()['created_at'])
    out=project(snapshot=snap,topology_source=declaration(at),now=now)
    assert out['inverter_ac_output_w']==1000
    assert out['household_ac_load_w'] is None and out['household_load_w'] is None
    assert out['battery_discharge_w']==500


def test_pure_flow_projection_needs_no_reads_and_returns_independent_values(tmp_path,monkeypatch):
    snap,_,now=fixture(tmp_path,monkeypatch);at=instant(snap.to_dict()['as_of']);source=declaration(at)
    expected=project(snapshot=snap,topology_source=source,now=now)
    import builtins,urllib.request,psycopg2
    def forbidden(*a,**kw):pytest.fail('live read at frozen flow boundary')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(urllib.request,'urlopen',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    actual=project(snapshot=snap,topology_source=source,now=now);assert actual==expected
    actual['source_evidence_sha256'].clear()
    assert project(snapshot=snap,topology_source=source,now=now)==expected
