"""Compact profiles remain bound to the original days and numerical runtime."""
from datetime import timedelta
from copy import deepcopy
from test_household_ac_load_sources import START,packet,raw
from household.codec import canonical,identity
import importlib
import pytest


def originals():
    result=[]
    for i in range(14):
        at=START+timedelta(days=i)
        _,source=packet(start=at,rows=[(at,raw(at))]);result.append(source)
    return result


def artifact():
    api=importlib.import_module('household_ac_load_artifact');sources=originals();cutoff=START+timedelta(days=14)
    value=api.build_artifact(sources=sources,cutoff=cutoff,trained_at=cutoff+timedelta(hours=1),runtime_manifest=api.runtime_manifest())
    return api,sources,value


def test_original_days_determine_model_coverage_and_source_bindings():
    api,sources,value=artifact();saved=deepcopy(sources)
    assert value['profile']['status']=='insufficient_support'
    assert len(value['days'])==14 and len(value['profile']['inputs']['hourly_rows'])==336
    assert value['days'][0]['source_sha256']==sources[0]['source_sha256']
    assert value['days'][0]['source_document_sha256']==identity(sources[0])
    assert value['days'][0]['covered_seconds']==30 and value['days'][0]['missing_seconds']==86370
    assert value['dataset_sha256']==identity(value['days'])
    assert api.replay_artifact(value,sources=sources,runtime_manifest=api.runtime_manifest())==value
    assert sources==saved and value['automatic_actuation'] is False


@pytest.mark.parametrize('damage',['runtime','source','day_count','cutoff','future_original','resealed_profile'])
def test_changed_runtime_original_dataset_or_derived_profile_refuses(damage):
    api,sources,value=artifact();runtime=api.runtime_manifest()
    if damage=='runtime':runtime[next(iter(runtime))]='f'*64
    elif damage=='source':sources[0]['rows'][0][1]='invalid changed original'
    elif damage=='day_count':sources.pop()
    elif damage=='future_original':
        sources[0]['received_at']=(START+timedelta(days=15)).isoformat()
        sources[0]['source_sha256']=identity({k:v for k,v in sources[0].items() if k!='source_sha256'})
    else:
        if damage=='cutoff':value['cutoff']=(START+timedelta(days=15)).isoformat()
        else:value['profile']['hours']['0']['origin_days']=99
        value['artifact_sha256']=identity({k:v for k,v in value.items() if k!='artifact_sha256'})
    with pytest.raises(ValueError):api.replay_artifact(value,sources=sources,runtime_manifest=runtime)


def test_ambiguous_original_day_is_retained_with_explicit_exclusion():
    api=importlib.import_module('household_ac_load_artifact');sources=originals();at=START
    _,sources[0]=packet(start=at,rows=[(at,raw(at,2)),(at+timedelta(seconds=5),raw(at+timedelta(seconds=5),1))])
    cutoff=START+timedelta(days=14)
    value=api.build_artifact(sources=sources,cutoff=cutoff,trained_at=cutoff+timedelta(hours=1),runtime_manifest=api.runtime_manifest())
    assert value['days'][0]['status']=='unavailable' and value['days'][0]['reason']=='ambiguous_source_sequence'
    assert value['days'][0]['source_sha256']==sources[0]['source_sha256']
    assert len(value['profile']['inputs']['hourly_rows'])==312
    assert len(canonical(value))<262144
