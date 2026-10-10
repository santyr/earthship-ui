"""Chronological provisional errors; missing baseline evidence remains explicit."""
from datetime import timedelta
import json
import pytest
from test_provisional_thermal_forecast import context,ISSUE,module as forecast_module
from test_installed_shade_origin import outcome


def module():
    from thermal_model import provisional_score
    return provisional_score


def issued(tmp_path,monkeypatch):
    candidate,data=context(tmp_path,monkeypatch);forecast=forecast_module()
    monkeypatch.setattr(forecast,'replay_binding',lambda *a,**k:None)
    capture=forecast.build_capture(candidate,data,issue=ISSUE,available=ISSUE,published=ISSUE+timedelta(seconds=2))
    receipts={}
    from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM
    for i,(name,value) in enumerate(((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,forecast.publication(capture)))):
        receipts[name]={'item':name,'time':int((ISSUE+timedelta(seconds=3+i)).timestamp()*1000),'state':json.dumps(value)}
    return capture,receipts


def test_mature_error_retains_model_and_persistence_with_recent_unavailable(tmp_path,monkeypatch):
    capture,receipts=issued(tmp_path,monkeypatch)
    pair=module().score(capture,receipts,outcome(ISSUE+timedelta(hours=1),75),horizon_hours=1,assessed_at=ISSUE+timedelta(hours=1,minutes=5),recent={'status':'insufficient_qualified_history','prediction_f':None})
    assert pair['predictions']['model']==capture['output']['trajectory'][0]['air_f']
    assert pair['errors']['model']==pair['predictions']['model']-75
    assert pair['errors']['persistence']==capture['output']['initial']['air_f']-75
    assert pair['errors']['recent_cycle'] is None
    report=module().summarize([pair])
    assert report['by_horizon']['1']['model']['count']==1
    assert report['by_horizon']['1']['recent_cycle']['count']==0
    assert report['by_horizon']['1']['recent_cycle']['mae_f'] is None


@pytest.mark.parametrize('damage',['immature','wrong_target','changed_delivery'])
def test_ineligible_outcome_or_delivery_never_counts(tmp_path,monkeypatch,damage):
    capture,receipts=issued(tmp_path,monkeypatch);target=ISSUE+timedelta(hours=1)
    observed=outcome(target,75);assessed=target+timedelta(minutes=5)
    if damage=='immature':assessed=target
    if damage=='wrong_target':observed=outcome(target+timedelta(hours=1),75)
    if damage=='changed_delivery':
        name=next(iter(receipts));receipts[name]['state']='{}'
    with pytest.raises(ValueError):module().score(capture,receipts,observed,horizon_hours=1,assessed_at=assessed,recent={'status':'insufficient_qualified_history','prediction_f':None})
