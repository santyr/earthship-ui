"""Prepared native geometry preserves the as-issued household thermal model."""
from copy import deepcopy
from pathlib import Path
import importlib
import pytest
from household.codec import canonical,identity
from test_native_thermal_score import issued,originals

CODE='a'*40

def api():return importlib.import_module('household.thermal_model')

def context(tmp_path,monkeypatch,originals):
    capture,_,k=issued(tmp_path,monkeypatch,originals)
    # Native candidate/forecast source identity is already validated separately;
    # this fixture isolates household freezing/parity from live runtime discovery.
    import native_thermal_artifact
    monkeypatch.setattr(native_thermal_artifact,'current_native_runtime',lambda **kw:deepcopy(k['runtime']))
    return capture,k

def prepare(capture,k,**kw):return api().prepare_native_projection(capture,code_revision=CODE,**k,**kw)


def test_native_household_projection_reproduces_all_hourly_original_values(tmp_path,monkeypatch,originals):
    c,k=context(tmp_path,monkeypatch,originals);p=prepare(c,k);result=api().project(p)
    assert isinstance(p,api().PreparedProjection)
    assert p.to_dict()['schema']=='earthship-household-prepared-thermal/v2'
    assert result['schema']=='earthship-household-thermal-projection/v2'
    assert canonical(result['output'])==canonical(c['output'])
    assert result['original_capture_sha256']==c['capture_sha256']
    assert result['action_effects_qualified'] is False and result['automatic_actuation'] is False
    assert p.to_dict()['geometry_series_sha256']==c['geometry_series_sha256']
    from household.model_snapshot import describe_thermal
    descriptor=describe_thermal(p)
    assert descriptor['artifact_sha256']==c['candidate']['artifact_sha256'] and descriptor['confidence']=='low'


def test_native_frozen_projection_restore_never_reads_files_or_sql(tmp_path,monkeypatch,originals):
    c,k=context(tmp_path,monkeypatch,originals);p=prepare(c,k);before=api().project(p)
    import builtins,os,psycopg2
    def forbidden(*args,**kwargs):pytest.fail('I/O inside frozen native model')
    for target,name in ((builtins,'open'),(os,'open'),(Path,'read_bytes'),(psycopg2,'connect')):monkeypatch.setattr(target,name,forbidden)
    restored=api().PreparedProjection(canonical(p.to_dict()))
    assert api().project(restored)==before


@pytest.mark.parametrize('damage',['artifact','capture','runtime','geometry','output'])
def test_native_preparation_requires_pinned_original_model_and_geometry(tmp_path,monkeypatch,originals,damage):
    c,k=context(tmp_path,monkeypatch,originals)
    if damage in ('artifact','capture'):k['expected_'+damage+'_sha256']='f'*64
    if damage=='runtime':k['runtime']['native_source_manifest']['openhab/scripts/native_thermal_forecast.py']='e'*64
    if damage=='geometry':c['geometry_series_sha256']='f'*64
    if damage=='output':c['output']['trajectory'][0]['air_f']+=1
    with pytest.raises(ValueError):prepare(c,k)


def test_native_preparation_freezes_caller_before_runtime_callbacks(tmp_path,monkeypatch,originals):
    c,k=context(tmp_path,monkeypatch,originals);expected=deepcopy(c['output'])
    def mutate():c['output']['trajectory'][0]['air_f']=99
    p=prepare(c,k,check_budget=mutate)
    assert c['output']['trajectory'][0]['air_f']==99 and api().project(p)['output']==expected


def test_native_projection_is_immutable_and_legacy_factory_refuses_it(tmp_path,monkeypatch,originals):
    c,k=context(tmp_path,monkeypatch,originals);p=prepare(c,k);expected=api().project(p)
    value=p.to_dict();value['coefficients'][0]=0
    assert api().project(p)==expected
    with pytest.raises(ValueError):api().prepare_projection(c,code_revision=CODE)
    value=p.to_dict();value['extra']=True;value['prepared_sha256']=identity({key:v for key,v in value.items() if key!='prepared_sha256'})
    with pytest.raises(ValueError):api().PreparedProjection(canonical(value))


@pytest.mark.parametrize('damage',['missing_source','invalid_source_hash'])
def test_native_prepared_execution_source_closure_is_closed(tmp_path,monkeypatch,originals,damage):
    c,k=context(tmp_path,monkeypatch,originals);p=prepare(c,k);value=p.to_dict()
    sources=value['executing_runtime']['household_source_manifest']
    if damage=='missing_source':sources.pop('household/codec.py')
    else:sources['household/codec.py']='invalid'
    value['prepared_sha256']=identity({key:v for key,v in value.items() if key!='prepared_sha256'})
    with pytest.raises(ValueError):api().PreparedProjection(canonical(value))
