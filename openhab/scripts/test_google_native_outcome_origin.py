"""Native Google deliveries retain model, source and actual publication identity."""
from copy import deepcopy
from datetime import timedelta
import importlib,json
from pathlib import Path
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM


def case(tmp_path,monkeypatch):
    from test_household_weather_context import make
    from native_thermal_forecast import publication
    _,prepared,capture=make(tmp_path,monkeypatch)
    issue=instant(capture['issued_at'])
    receipts={item:dict(item=item,time=int((issue+timedelta(seconds=3+i)).timestamp()*1000),state=canonical(body).decode())
        for i,(item,body) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture))))}
    args=dict(code_revision='a'*40,runtime=capture['candidate']['runtime'],
        expected_artifact_sha256=capture['candidate']['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    return prepared,capture,receipts,args


def prepare(capture,receipts,args):
    api=importlib.import_module('household.outcome_origin')
    assert hasattr(api,'prepare_native_outcome_origin'),'native delivered-outcome adapter missing'
    return api.prepare_native_outcome_origin(capture,receipts,**args)


def test_native_delivered_origin_preserves_the_exact_prepared_model_and_receipts(tmp_path,monkeypatch):
    prepared,capture,receipts,args=case(tmp_path,monkeypatch)
    origin=prepare(capture,receipts,args)
    assert origin.to_dict()['schema']=='earthship-household-outcome-origin/v2'
    assert origin.prepared.to_dict()==prepared.to_dict()
    assert origin.to_dict()['original_capture']==capture and origin.to_dict()['receipts']==receipts


@pytest.mark.parametrize('damage',['artifact','capture','runtime','receipt'])
def test_native_origin_requires_external_pins_and_both_delivered_states(tmp_path,monkeypatch,damage):
    _,capture,receipts,args=case(tmp_path,monkeypatch)
    api=importlib.import_module('household.outcome_origin')
    assert hasattr(api,'prepare_native_outcome_origin'),'native delivered-outcome adapter missing'
    if damage in ('artifact','capture'):args['expected_'+damage+'_sha256']='f'*64
    elif damage=='runtime':args['runtime']=deepcopy(args['runtime']);args['runtime']['native_code_revision']='f'*64
    else:receipts[PUBLICATION_ITEM]['state']='{}'
    with pytest.raises(ValueError):api.prepare_native_outcome_origin(capture,receipts,**args)


def test_frozen_native_origin_replay_performs_no_files_network_or_database_reads(tmp_path,monkeypatch):
    _,capture,receipts,args=case(tmp_path,monkeypatch);origin=prepare(capture,receipts,args)
    import builtins,psycopg2,requests,urllib.request
    def forbidden(*a,**kw):pytest.fail('I/O while restoring frozen native delivery')
    for owner,name in [(builtins,'open'),(Path,'read_bytes'),(psycopg2,'connect'),(requests.Session,'request'),(urllib.request,'urlopen')]:monkeypatch.setattr(owner,name,forbidden)
    api=importlib.import_module('household.outcome_origin')
    assert api.PreparedOutcomeOrigin(origin.content).to_dict()==origin.to_dict()


def test_native_origin_cannot_be_downgraded_to_an_old_model_contract(tmp_path,monkeypatch):
    _,capture,receipts,args=case(tmp_path,monkeypatch);body=prepare(capture,receipts,args).to_dict()
    body['schema']='earthship-household-outcome-origin/v1';body['origin_sha256']=identity({k:v for k,v in body.items() if k!='origin_sha256'})
    api=importlib.import_module('household.outcome_origin')
    with pytest.raises(ValueError):api.PreparedOutcomeOrigin(canonical(body))


@pytest.mark.parametrize('native',[True,False])
def test_resealed_weather_rows_cannot_detach_from_original_google_bytes(tmp_path,monkeypatch,native):
    api=importlib.import_module('household.outcome_origin')
    if native:
        _,capture,receipts,args=case(tmp_path,monkeypatch);origin=prepare(capture,receipts,args)
        from native_thermal_forecast import publication
    else:
        from test_household_models import prepared_thermal
        from thermal_model.provisional_forecast import publication
        _,capture=prepared_thermal(tmp_path,monkeypatch);issue=instant(capture['issued_at'])
        receipts={item:dict(item=item,time=int((issue+timedelta(seconds=3+i)).timestamp()*1000),state=canonical(body).decode())
            for i,(item,body) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture))))}
        origin=api.prepare_outcome_origin(capture,receipts,code_revision='a'*40)
    value=origin.to_dict();capture=value['original_capture'];forecast=capture['inputs']['forecast']
    forecast['rows'][0]['windMph']+=1
    forecast['rows_sha256']=identity(forecast['rows'])
    forecast['forecast_sha256']=identity({k:v for k,v in forecast.items() if k!='forecast_sha256'})
    from thermal_model.provisional_forecast import digest
    capture['capture_sha256']=digest(capture,'capture_sha256')
    prepared=value['prepared_thermal'];prepared['original_capture_sha256']=capture['capture_sha256']
    snapshot=prepared['snapshot']
    for domain in snapshot['domains'].values():
        for row in domain.values():
            if row['evidence'] is not None:row['evidence']['parent_digests']=[capture['capture_sha256']]
    snapshot['snapshot_id']=identity({k:v for k,v in snapshot.items() if k!='snapshot_id'})
    prepared['prepared_sha256']=identity({k:v for k,v in prepared.items() if k!='prepared_sha256'})
    for item,body in ((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture))):value['receipts'][item]['state']=canonical(body).decode()
    value['origin_sha256']=identity({k:v for k,v in value.items() if k!='origin_sha256'})
    with pytest.raises(ValueError):api.PreparedOutcomeOrigin(canonical(value))
