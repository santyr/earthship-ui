"""Freeze and replay temporal decisions without live reads."""
from datetime import timedelta
from dataclasses import replace, FrozenInstanceError
import importlib
import pytest
from test_household_evidence import api,args
from local_measurement_test_support import bms_evidence as evidence, NOW


def build(values=None,**changes):
    assert importlib.util.find_spec('household.snapshot') is not None, 'household snapshot missing'
    from household.snapshot import build_snapshot
    value=api().battery_soc(**args(evidence(),epoch='00000000-0000-0000-0000-000000000001'))
    options=dict(as_of=NOW,created_at=NOW,code_revision='a'*40,config_revision='b'*64,
                 requirements={'battery_display':['battery_soc'],'water_display':['water_inventory']},
                 max_age_seconds={'battery_soc':120},max_skew_seconds=60)
    options.update(changes)
    return build_snapshot([value] if values is None else values,**options)


def test_freezing_deterministic_identity_and_explicit_unknown_water():
    requirements={'battery_display':['battery_soc'],'water_display':['water_inventory']}
    snapshot=build(requirements=requirements);original=snapshot.to_dict();requirements['battery_display'].append('water_inventory')
    mutable=snapshot.to_dict();mutable['domains']['energy']['battery_soc']['value']=0
    assert snapshot.to_dict()==original
    assert original['domains']['water']['water_inventory']['value'] is None
    assert original['completeness']=={'battery_display':True,'water_display':False}
    assert original['planner_authority']=='none'
    assert snapshot.snapshot_id==build().snapshot_id
    with pytest.raises(FrozenInstanceError):snapshot.content=b'bad'


def test_source_expires_at_boundary_without_laundering_original_qualification():
    snapshot=build(as_of=NOW+timedelta(seconds=100),created_at=NOW+timedelta(seconds=100))
    row=snapshot.to_dict()['domains']['energy']['battery_soc']
    assert row['value'] is None and row['reason']=='expired_source'
    assert row['evidence']['quality']=='qualified'
    assert snapshot.to_dict()['completeness']['battery_display'] is False


@pytest.mark.parametrize('damage',['duplicate','future','age','bad_policy','empty_requirements'])
def test_temporal_and_policy_failures_are_honest(damage):
    value=api().battery_soc(**args(evidence(),epoch='00000000-0000-0000-0000-000000000001'))
    if damage=='duplicate':
        with pytest.raises(ValueError):build([value,value])
    elif damage=='future':
        result=build(as_of=NOW-timedelta(seconds=1))
        assert result.to_dict()['domains']['energy']['battery_soc']['value'] is None
    elif damage=='age':
        result=build(max_age_seconds={'battery_soc':10})
        assert result.to_dict()['domains']['energy']['battery_soc']['reason']=='source_too_old'
    elif damage=='bad_policy':
        with pytest.raises(ValueError):build(max_skew_seconds=True)
    else:
        with pytest.raises(ValueError):build(requirements={'empty':[]})


def test_skew_is_capability_specific_without_invalidating_unrelated_display():
    from test_pv_day_evidence import receipt,EPOCH
    import json
    bms=api().battery_soc(**args(evidence(),epoch='00000000-0000-0000-0000-000000000001'))
    raw=json.dumps(receipt(NOW-timedelta(seconds=50),1))
    pv=api().pv_day_counter(**args(raw,epoch=EPOCH))
    options=dict(max_age_seconds={'battery_soc':120,'pv_day_wh':90},max_skew_seconds=10,
                 requirements={'joint':['battery_soc','pv_day_wh'],'battery_display':['battery_soc']})
    result=build([bms,pv],**options).to_dict()
    assert result['completeness']=={'joint':False,'battery_display':True}
    assert result['capability_reasons']['joint']=='source_skew'
    assert result['domains']['energy']['battery_soc']['value']==100
    assert build([pv,bms],**options).to_dict()==result
