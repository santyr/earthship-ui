"""Only confirmed production writes create new as-issued identities."""
from datetime import timedelta
import copy
import pytest
from test_production_forecast import serving,prepare,NOW
from weather_learning.contracts import identity
from weather_learning.shadow import ShadowStore
from weather_learning.production_publish import production_states,publish_cycle


def published(serving):
 product=prepare(serving);provider=serving['provider'];states=production_states(provider,now=NOW,production=product);store={}
 publication=publish_cycle(provider,now=NOW,production=product,put_state=lambda k,v:store.__setitem__(k,v),read_state=store.__getitem__,authorize=lambda p:True)
 attempt=dict(started_at=NOW.isoformat(),provider=provider.to_dict(),states=states,states_sha256=identity(states))
 attempt['attempt_sha256']=identity(attempt)
 result=dict(attempt_sha256=attempt['attempt_sha256'],status='PUBLISHED',completed_at=(NOW+timedelta(seconds=5)).isoformat(),publication=publication)
 result['result_sha256']=identity(result)
 return product,attempt,result


def test_prepared_original_has_no_issued_receipt_and_confirmed_write_retains_exact_prediction(serving,tmp_path):
 from weather_learning.production_emissions import retain_prepared,confirm_publication,read_emission
 product,attempt,result=published(serving);state=ShadowStore(tmp_path/'private')
 ref=retain_prepared(state,product,provider=serving['provider'],now=NOW)
 assert ref==product.to_dict()['issue_sha256'] and not list((state.root/'production-emissions').glob('*.json'))
 emission=confirm_publication(state,product,provider=serving['provider'],attempt=attempt,result=result)
 assert emission['issued'] is True and emission['issue_sha256']==ref and emission['parallel_shadow_required'] is False
 assert read_emission(state,emission['emission_sha256'])==emission
 assert product.to_dict()['issued'] is False
 assert len(emission['score_rows'])<=48 and len(emission['published_rows'])>len(emission['score_rows'])
 assert all(row['kind'] in ('temperature','wind') for row in emission['published_rows'])
 assert emission['publication_original']==result
 before={p:p.read_bytes() for name in ('production-issues','production-emissions') for p in (state.root/name).glob('*.json')}
 assert confirm_publication(state,product,provider=serving['provider'],attempt=attempt,result=result)==emission
 assert all(path.read_bytes()==raw for path,raw in before.items())


@pytest.mark.parametrize('change',['failed','unconfirmed','wrong_states','late','different_issue'])
def test_failed_mismatched_or_late_publication_cannot_become_an_issued_prediction(serving,tmp_path,change):
 from weather_learning.production_emissions import retain_prepared,confirm_publication
 product,attempt,result=published(serving);state=ShadowStore(tmp_path/'state');retain_prepared(state,product,provider=serving['provider'],now=NOW)
 result=copy.deepcopy(result)
 if change=='failed':result['status']='FAILED'
 elif change=='unconfirmed':result['publication']['verified_items'].pop()
 elif change=='wrong_states':result['publication']['states_sha256']='f'*64
 elif change=='late':result['completed_at']=(NOW+timedelta(seconds=86)).isoformat()
 elif change=='different_issue':result['publication']['production_issue_sha256']='f'*64
 result['result_sha256']=identity({k:v for k,v in result.items() if k!='result_sha256'})
 with pytest.raises(ValueError):confirm_publication(state,product,provider=serving['provider'],attempt=attempt,result=result)
 assert not list((state.root/'production-emissions').glob('*.json'))


def test_emission_requires_the_original_persisted_issue_before_any_publication_claim(serving,tmp_path):
 from weather_learning.production_emissions import confirm_publication
 product,attempt,result=published(serving);state=ShadowStore(tmp_path/'state')
 with pytest.raises((ValueError,FileNotFoundError)):confirm_publication(state,product,provider=serving['provider'],attempt=attempt,result=result)


def test_retention_compresses_repeated_original_fields_losslessly_with_a_bounded_reader(serving,tmp_path):
 from weather_learning.production_emissions import retain_prepared,read_issue
 from weather_learning.contracts import canonical
 product=prepare(serving);state=ShadowStore(tmp_path/'bounded')
 pin=retain_prepared(state,product,provider=serving['provider'],now=NOW)
 path=state.root/'production-issues'/(pin+'.json')
 assert path.stat().st_size<len(canonical(product.to_dict()))/2
 assert read_issue(state,pin).to_dict()==product.to_dict()


def test_compressed_original_cannot_expand_beyond_the_existing_object_bound(serving,tmp_path):
 import base64,gzip,json
 from weather_learning.production_emissions import retain_prepared,read_issue
 from weather_learning.contracts import canonical
 product=prepare(serving);state=ShadowStore(tmp_path/'expansion');pin=retain_prepared(state,product,provider=serving['provider'],now=NOW)
 path=state.root/'production-issues'/(pin+'.json');capsule=json.loads(path.read_bytes())
 capsule['uncompressed_bytes']=16*1024**2
 capsule['gzip_base64']=base64.b64encode(gzip.compress(b'x'*(16*1024**2+1),mtime=0)).decode()
 capsule['capsule_sha256']=identity({k:v for k,v in capsule.items() if k!='capsule_sha256'});path.write_bytes(canonical(capsule))
 with pytest.raises(ValueError,match='bounded'):read_issue(state,pin)
