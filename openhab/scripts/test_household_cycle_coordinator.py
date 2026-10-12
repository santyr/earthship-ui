"""Coordinator tests keep genuine publisher archives and isolate model boundaries.

The numerical integration is covered by test_household_cycle; these cases cover
verified delivery, original archive stability, and the cache publication gate.
"""
import json
from pathlib import Path
import pytest
from household.codec import canonical
from test_provisional_thermal_live import fixture,module as live


def setup(tmp_path,monkeypatch):
    import household_cycle as cycle
    import household.thermal_model as thermal
    import household.weather_context as weather
    import household_pipeline as pipeline
    import household_observation as observation
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    publication=live().publish_cycle(settings,backend=parent,guard=lambda:None)
    capture=json.loads(Path(publication['origin_path']).read_bytes())
    evidence=tmp_path/'household';evidence.mkdir(mode=0o700)
    calls=[]
    monkeypatch.setattr(thermal,'prepare_projection',lambda body,**kw: ('prepared',body['capture_sha256']))
    monkeypatch.setattr(weather,'prepare_weather_context',lambda body,**kw: ('weather',body['capture_sha256']))
    monkeypatch.setattr(weather,'prepare_cycle_contexts',lambda body,**kw: (('prepared',body['capture_sha256']),('weather',body['capture_sha256'])))
    def derive(**kw):
        calls.append(('derive',kw))
        return {'receipt_sha256':'a'*64,'inputs':{'thermal_inputs':None},'automatic_actuation':False}
    monkeypatch.setattr(cycle,'derive_cycle',derive)
    monkeypatch.setattr(pipeline,'verify_source_closure',lambda record,runtime:calls.append(('closure',record)))
    def materialize(path,target,**kw):
        record=json.loads(Path(path).read_bytes());calls.append(('cache',record))
        return {'status':'observation_written','receipt_sha256':record['receipt_sha256'],'automatic_actuation':False}
    monkeypatch.setattr(observation,'materialize',materialize)
    originals={'original':'unmodified'}
    collection={'status':'collected','issue':capture['issued_at'],'originals':originals}
    return cycle,dict(publication=publication,collection=collection,parameter_record={'collected_at':capture['issued_at']},
        runtime_manifest={'runtime':'b'*64},code_revision='e'*40,evidence_directory=evidence,
        observation_cache=tmp_path/'observation.json',guard=lambda:None,clock=lambda:clock[0]),calls


def test_verified_delivery_gates_models_and_retains_originals(tmp_path,monkeypatch):
    cycle,args,calls=setup(tmp_path,monkeypatch)
    result=cycle.complete_cycle(**args)
    assert result['status']=='observation_written'
    assert [row[0] for row in calls]==['derive','closure','cache']
    derived=calls[0][1]
    assert derived['originals']==args['collection']['originals']
    assert derived['capture']['capture_sha256']==derived['thermal'][1]
    assert derived['weather'][1]==derived['thermal'][1]
    files=list(args['evidence_directory'].iterdir());assert len(files)==2
    assert all(path.stat().st_mode & 0o777==0o600 for path in files)
    assert any(json.loads(path.read_bytes())==args['collection']['originals'] for path in files)

@pytest.mark.parametrize('damage',['unverified','wrong_issue','delivery_hash','capture_binding','archive_mode'])
def test_bad_original_delivery_never_derives_or_writes_cache(damage,tmp_path,monkeypatch):
    cycle,args,calls=setup(tmp_path,monkeypatch)
    publication=args['publication'];path=Path(publication['delivery_path'])
    if damage=='unverified':publication['delivery_verified']=False
    elif damage=='wrong_issue':args['collection']['issue']='2026-10-11T00:00:00+00:00'
    elif damage=='archive_mode':Path(publication['origin_path']).chmod(0o644)
    else:
        value=json.loads(path.read_bytes())
        if damage=='delivery_hash':value['delivery_sha256']='b'*64
        else:
            from thermal_model.provisional_forecast import digest
            value['capture_path']=str(tmp_path/'different.json')
            value['delivery_sha256']=digest(value,'delivery_sha256')
        path.write_bytes(canonical(value))
    with pytest.raises(ValueError):cycle.complete_cycle(**args)
    assert calls==[]
    assert list(args['evidence_directory'].iterdir())==[]


def test_unavailable_observer_leaves_cache_untouched(tmp_path,monkeypatch):
    cycle,args,calls=setup(tmp_path,monkeypatch)
    args['collection']={'status':'unavailable','reason':'source_collection_failed'}
    result=cycle.complete_cycle(**args)
    assert result['status']=='observation_unavailable'
    assert calls==[]
    assert list(args['evidence_directory'].iterdir())==[]


def test_source_drift_before_materialization_refuses_cache(tmp_path,monkeypatch):
    cycle,args,calls=setup(tmp_path,monkeypatch)
    def guard():
        if any(row[0]=='derive' for row in calls):
            Path(args['publication']['origin_path']).write_bytes(b'{}')
    args['guard']=guard
    with pytest.raises(ValueError):cycle.complete_cycle(**args)
    assert not any(row[0]=='cache' for row in calls)


def test_lazy_backend_uses_the_actual_publisher_issue_archive(tmp_path,monkeypatch):
    import household_cycle as cycle
    import thermal_model.provisional_live as publisher
    settings,_,clock,_=fixture(tmp_path,monkeypatch)
    calls=[];original={'input':'unchanged'}
    class Parent:
        def __init__(self,value,*,shared_lock_guard):calls.append(('created',value,shared_lock_guard))
        def collect(self,**kw):calls.append(('collect',kw));return original
        def verify_unchanged(self):calls.append(('verified',))
        def put(self,*args,**kw):calls.append(('put',args,kw))
        def persisted(self,*args,**kw):return ('receipt',args,kw)
    monkeypatch.setattr(publisher,'CompressedSourceLiveBackend',Parent)
    monkeypatch.setattr(publisher,'backend_settings',lambda value:{'preserved_settings':value})
    guard=lambda:None
    backend=cycle.LazyForecastBackend(settings,guard=guard)
    assert calls==[]
    issue=clock[0]
    assert backend.collect(issue=issue,known_at=issue) is original
    assert calls[0][1]['evidence_directory']==str(publisher.delivery_directory(settings,issue))
    assert calls[0][2] is guard
    backend.verify_unchanged();assert calls[-1]==('verified',)
    assert backend.persisted('item','state',since=issue)==('receipt',('item','state'),{'since':issue})
    with pytest.raises(ValueError):backend.collect(issue=issue,known_at=issue)
