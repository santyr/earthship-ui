"""Closed migration contracts for unchanged Sun calendar display Items."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

NAMES={'Sun_Spring':80,'Sun_Summer':81,'Sun_Autumn':82,'Sun_Winter':83,
       'Sun_RingEclipse':89,'Sun_TotalEclipse':86,'Sun_PartialEclipse':87,
       'Sun_Eclipse_PartialElevation':88}


def module():
    import sun_calendar_items
    return sun_calendar_items


def test_exact_live_inventory_and_derived_semantics():
    m=module();rows=m.specification()
    assert {n:r['jdbc_id'] for n,r in rows.items()}==NAMES
    assert m.checked_source()==m.render(rows)
    for name,row in rows.items():
        item={**deepcopy(row['item']),'editable':True,'state':'2027-01-01T12:00:00-0700'}
        if name=='Sun_Eclipse_PartialElevation':item['state']='1.5 °'
        m.validate_item(item,name,managed=True)
        m.validate_links([{**row['link'],'editable':True}],name,managed=True)
        item['editable']=False;m.validate_item(item,name,managed=False)


@pytest.mark.parametrize('field,value',[('type','Number'),('label','Changed'),('groupNames',[]),
    ('tags',[]),('unitSymbol','rad'),('stateDescription',{'pattern':'%s'}),('metadata',{}),('editable',False)])
def test_definition_or_provider_drift_refuses_handoff(field,value):
    m=module();name='Sun_Eclipse_PartialElevation'
    item={**deepcopy(m.specification()[name]['item']),'editable':True,'state':'1.5 °'}
    item[field]=value
    with pytest.raises(RuntimeError):m.validate_item(item,name,managed=True)


@pytest.mark.parametrize('extra',[{'profile':'system:follow'},{'function':'astro.map'}])
def test_original_single_empty_profile_link_required(extra):
    m=module();name='Sun_Spring';link={**m.specification()[name]['link'],'editable':True}
    for rows in ([],[link,link],[{**link,'configuration':extra}],[{**link,'editable':False}]):
        with pytest.raises(RuntimeError):m.validate_links(rows,name,managed=True)


@pytest.mark.parametrize('method,path,body',[
    ('PUT','/items/Sun_Spring/state','2030-01-01T00:00:00Z'),
    ('POST','/items/Sun_Spring','ON'),('DELETE','/items/Sun_Position_Elevation',None),
    ('DELETE','/items/Sun_Set_Start',None),('DELETE','/items/Sun_Daylight_Start',None),
    ('POST','/rules/hex_south_planter_fan/runnow',None),('DELETE','/things/astro:sun:local',None),
    ('DELETE','/items/Sun_Spring/metadata/semantics',None)])
def test_protected_inputs_and_non_definition_writes_are_outside_scope(method,path,body):
    with pytest.raises(RuntimeError):module().allowed_mutation(method,path,body)


def test_only_original_definitions_and_links_can_be_restored():
    from urllib.parse import quote
    m=module()
    for n,r in m.specification().items():
        dto=m.managed_item(n);m.allowed_mutation('PUT','/items/'+n,dto)
        m.allowed_mutation('DELETE','/items/'+n,None)
        target='/links/'+n+'/'+quote(r['link']['channelUID'],safe='')
        m.allowed_mutation('PUT',target,r['link']);m.allowed_mutation('DELETE',target,None)
        dto['label']='Changed'
        with pytest.raises(RuntimeError):m.allowed_mutation('PUT','/items/'+n,dto)


def test_source_and_specification_drift_refuse_qualification(tmp_path,monkeypatch):
    m=module();source=tmp_path/'source.items';source.write_bytes(m.checked_source()+b'\n')
    monkeypatch.setattr(m,'SOURCE',source)
    with pytest.raises(RuntimeError):m.checked_source()
    spec=tmp_path/'spec.json';spec.write_text('{}');monkeypatch.setattr(m,'SPEC',spec)
    with pytest.raises(RuntimeError):m.specification()


def test_private_auth_header_is_restaged_before_each_owned_definition_write(monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    p=Path(__file__).with_name('qualify-sun-calendar-provider.py')
    s=importlib.util.spec_from_file_location('sun_provider_header_recovery',p);q=importlib.util.module_from_spec(s);s.loader.exec_module(q)
    staged=[];header=b'Authorization: Bearer disposable-fixture-only\n'
    monkeypatch.setattr(q.aqi,'install_bytes',lambda container,directory,name,body,**kw:staged.append((name,body)))
    monkeypatch.setattr(q.aqi,'run',lambda *args,**kw:SimpleNamespace(stdout=b'201'))
    q.mutation('owned-fixture',header,'PUT','/items/Sun_Spring',module().managed_item('Sun_Spring'))
    assert ('calendar-auth-header',header) in staged
