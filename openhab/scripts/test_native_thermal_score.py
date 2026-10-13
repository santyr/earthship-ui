"""Native measured-error arithmetic requires original forecast delivery and phase."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import importlib,json
import pytest
from test_native_thermal_forecast import originals,context as forecast_context,ISSUE,api as forecast_api
from test_installed_shade_origin import outcome
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM

def api():return importlib.import_module('native_thermal_score')

def issued(tmp_path,monkeypatch,originals):
    import native_thermal_artifact as artifacts
    c,i,k=forecast_context(tmp_path,monkeypatch,originals)
    runtime=deepcopy(k['runtime']);runtime['native_source_manifest']['openhab/scripts/native_thermal_score.py']='d'*64
    runtime['native_code_revision']=artifacts.digest(runtime['native_source_manifest'])
    c=artifacts.build_native_candidate(originals={role:Path(ref['path']) for role,ref in c['originals'].items()},runtime=runtime,created_at=c['created_at'])
    k.update(runtime=runtime,expected_artifact_sha256=c['artifact_sha256'])
    capture=forecast_api().build_capture(c,i,**k)
    receipts={name:dict(item=name,time=int((ISSUE+timedelta(seconds=3+index)).timestamp()*1000),state=json.dumps(value))
      for index,(name,value) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,forecast_api().publication(capture))))}
    return capture,receipts,dict(runtime=runtime,expected_artifact_sha256=c['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])

def scored(tmp_path,monkeypatch,originals,*,hours=1,recent=None):
    c,r,k=issued(tmp_path,monkeypatch,originals);target=ISSUE+timedelta(hours=hours)
    return api().score(c,r,outcome(target),horizon_hours=hours,assessed_at=target+timedelta(minutes=10),recent=recent or {'status':'insufficient_qualified_history','prediction_f':None},**k)

@pytest.mark.parametrize('hours',[1,6,12,24])
def test_native_mature_pairs_preserve_measured_baselines_and_geometry(tmp_path,monkeypatch,originals,hours):
    c,r,k=issued(tmp_path,monkeypatch,originals);target=ISSUE+timedelta(hours=hours)
    pair=api().score(c,r,outcome(target),horizon_hours=hours,assessed_at=target+timedelta(minutes=10),recent={'status':'insufficient_qualified_history','prediction_f':None},**k)
    assert pair['errors']['model']==c['output']['trajectory'][hours-1]['air_f']-75
    assert pair['errors']['persistence']==-1 and pair['errors']['recent_cycle'] is None
    assert pair['geometry_series_sha256']==c['geometry_series_sha256']
    assert api().validate_pair(pair,expected_pair_sha256=pair['pair_sha256'])==pair
    report=api().summarize([pair],artifact_sha256=pair['artifact_sha256'])
    assert report['by_horizon'][str(hours)]['persistence']=={'count':1,'mae_f':1,'bias_f':-1}
    assert report['by_horizon'][str(hours)]['recent_cycle']=={'count':0,'mae_f':None,'bias_f':None}
    assert report['graduated'] is False and pair['automatic_actuation'] is False

@pytest.mark.parametrize('damage',['missing','numeric','main','reordered','late'])
def test_native_score_requires_both_exact_ordered_delivery_receipts(tmp_path,monkeypatch,originals,damage):
    c,r,k=issued(tmp_path,monkeypatch,originals)
    if damage=='missing':r.pop(NUMERIC_ITEM)
    if damage=='numeric':r[NUMERIC_ITEM]['state']='{}'
    if damage=='main':r[PUBLICATION_ITEM]['state']='{}'
    if damage=='reordered':r[PUBLICATION_ITEM]['time']=r[NUMERIC_ITEM]['time']-1
    if damage=='late':r[PUBLICATION_ITEM]['time']=int((ISSUE+timedelta(seconds=92)).timestamp()*1000)
    with pytest.raises(ValueError):api().score(c,r,outcome(ISSUE+timedelta(hours=1)),horizon_hours=1,assessed_at=ISSUE+timedelta(hours=1,minutes=10),recent={'status':'unavailable','prediction_f':None},**k)

@pytest.mark.parametrize('damage',['immature','phase','precision','missing_baseline'])
def test_native_score_refuses_unqualified_outcome_or_baseline(tmp_path,monkeypatch,originals,damage):
    c,r,k=issued(tmp_path,monkeypatch,originals);target=ISSUE+timedelta(hours=1);receipt=outcome(target);assessed=target+timedelta(minutes=10);recent={'status':'unavailable','prediction_f':None}
    if damage=='immature':assessed=target+timedelta(minutes=4,seconds=59)
    if damage=='phase':receipt['sensorEpoch']='00000000-0000-0000-0000-000000000001'
    if damage=='precision':assessed=assessed.isoformat().split('+')[0]+'.0000009+00:00'
    if damage=='missing_baseline':recent['prediction_f']=0
    with pytest.raises(ValueError):api().score(c,r,receipt,horizon_hours=1,assessed_at=assessed,recent=recent,**k)


def test_native_report_rejects_duplicate_scores_and_resealed_arithmetic(tmp_path,monkeypatch,originals):
    pair=scored(tmp_path,monkeypatch,originals)
    with pytest.raises(ValueError):api().summarize([pair,pair],artifact_sha256=pair['artifact_sha256'])
    bad=deepcopy(pair);bad['errors']['model']+=1;bad['pair_sha256']=api().digest(bad,'pair_sha256')
    with pytest.raises(ValueError):api().validate_pair(bad,expected_pair_sha256=bad['pair_sha256'])
    with pytest.raises(ValueError):api().validate_pair(pair,expected_pair_sha256='f'*64)


def test_available_recent_cycle_is_counted_without_graduating(tmp_path,monkeypatch,originals):
    pair=scored(tmp_path,monkeypatch,originals,recent={'status':'available','prediction_f':76})
    assert pair['errors']['recent_cycle']==1
    report=api().summarize([pair],artifact_sha256=pair['artifact_sha256'])
    assert report['by_horizon']['1']['recent_cycle']=={'count':1,'mae_f':1,'bias_f':1}
    assert report['graduated'] is False


def test_score_freezes_caller_outcome_before_capture_guard_callbacks(tmp_path,monkeypatch,originals):
    c,r,k=issued(tmp_path,monkeypatch,originals);target=ISSUE+timedelta(hours=1);receipt=outcome(target)
    def mutate():receipt['temperatureF']=99
    pair=api().score(c,r,receipt,horizon_hours=1,assessed_at=target+timedelta(minutes=10),recent={'status':'unavailable','prediction_f':None},check_budget=mutate,**k)
    assert receipt['temperatureF']==99 and pair['outcome']['temperatureF']==75 and pair['errors']['persistence']==-1


def test_native_report_refuses_mixed_model_runtime_but_filters_explicit_revision(tmp_path,monkeypatch,originals):
    pair=scored(tmp_path,monkeypatch,originals);other=deepcopy(pair)
    other['capture_sha256']='e'*64;other['runtime_sha256']='f'*64;other['pair_sha256']=api().digest(other,'pair_sha256')
    with pytest.raises(ValueError):api().summarize([pair,other],artifact_sha256=pair['artifact_sha256'])
    other['artifact_sha256']='d'*64;other['pair_sha256']=api().digest(other,'pair_sha256')
    with pytest.raises(ValueError):api().summarize([pair,other])
    selected=api().summarize([pair,other],artifact_sha256=pair['artifact_sha256'])
    assert selected['by_horizon']['1']['persistence']['count']==1
