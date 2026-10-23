"""Matched all-publication scores preserve dates, targets and original clocks."""
from datetime import timedelta
from dataclasses import replace
import importlib.util
import pytest
from test_refresh_evaluation import sources,publication,reseal
from learning_fixtures import EPOCH,receipt
from weather_learning.contracts import instant
from weather_learning.features import local_temperature_outcome


def api():
    assert importlib.util.find_spec('weather_learning.refresh_scoring'), 'Task6 matched refresh scorer missing'
    from weather_learning import refresh_scoring
    return refresh_scoring


def compile(tmp_path,sources,**kwargs):
    from learning_fixtures import SITE
    attempt,result=publication(tmp_path,sources)
    return api().compile_refresh_decision(attempt,result,archive=sources[0],site=SITE,**kwargs)


def outcome(at,value=18,*,assessed=None,available=None):
    assessed=assessed or at+timedelta(minutes=2)
    value=local_temperature_outcome(receipt(at,value),target_at=at,assessed_at=assessed,sensor_epoch=EPOCH)
    return value if available is None else replace(value,available_at=available)


def score(record,at,observed=18,**kwargs):
    return api().score_refresh_target(record,target_at=at,outcome=outcome(at,observed,**kwargs),
        observation_policy_sha256='a'*64,measurement_quality='qualified_receipt_v2')


def comparison(report,name='latest_48h_collection_vs_latest_360h_collection'):
    return next(c for c in report['comparisons'] if c['comparison']==name)


def test_compiled_population_retains_all_near_hours_and_declared_long_leads(tmp_path,sources):
    value=compile(tmp_path,sources).to_dict()
    assert len(value['targets'])==31  #25 native near endpoints plus6 long offsets
    assert value['sampling']['near']=='all native endpoints through ceil(decision+24h)'
    assert value['sampling']['long_offsets']==[48,72,120,168,240,336]
    assert value['targets'][-1]['offset_from_first_hour']==336
    first=value['targets'][0]
    assert first['forecasts']['actual_serving']['value_c']==20
    assert first['forecasts']['latest_360h_collection']['value_c']==10
    assert first['forecasts']['latest_48h_collection']['source']['grid_sha256']
    assert first['forecasts']['actual_serving']['actually_published'] is True
    assert first['forecasts']['latest_48h_collection']['actually_published'] is False
    assert value['targets'][-1]['forecasts']['latest_48h_collection']['value_c'] is None
    assert value['automatic_actuation'] is False


def test_identical_target_comparison_and_explicit_raw_correction_fallback(tmp_path,sources):
    record=compile(tmp_path,sources);at=instant(record.to_dict()['targets'][0]['target_at'])
    row=score(record,at);report=api().summarize_refresh_scores([row]);c=comparison(report)
    assert c['matched']['support']==dict(pairs=1,targets=1,local_dates=1)
    assert c['matched']['left']['mae_c']==pytest.approx(2)
    assert c['matched']['right']['mae_c']==pytest.approx(8)
    near=comparison(report,'near_term_local_correction_24h_v1_vs_actual_serving')
    assert near['fallback_inclusive']['left']['mae_c']==pytest.approx(2)
    assert near['coverage']['corrected']==0 and near['coverage']['fallback']==1
    assert c['disposition']=='insufficient_evidence'
    assert report['probability_claim'] is False


def test_only_targets_later_than_confirmed_publication_enter_scoring(tmp_path,sources):
    from learning_fixtures import SITE
    attempt,result=publication(tmp_path,sources)
    result['completed_at']=(sources[3]+timedelta(minutes=40)).isoformat();reseal(result,'result_sha256')
    value=api().compile_refresh_decision(attempt,result,archive=sources[0],site=SITE).to_dict()
    assert instant(value['targets'][0]['target_at'])==sources[3].replace(minute=0)+timedelta(hours=2)
    assert value['withheld']['elapsed_before_confirmed_publication']==1


def test_repeated_forecasts_use_equal_dates_then_targets_then_forecasts(tmp_path,sources):
    first=compile(tmp_path,sources);later=tmp_path/'later';later.mkdir(mode=0o700)
    second=compile(later,(*sources[:3],sources[3]+timedelta(minutes=1)),previous=first)
    at=instant(first.to_dict()['targets'][0]['target_at']);tomorrow=at+timedelta(days=1)
    a=score(first,at);b=score(second,at);c=score(first,tomorrow,observed=10)
    report=api().summarize_refresh_scores([a,b,c]);matched=comparison(report)['matched']
    assert matched['support']==dict(pairs=3,targets=2,local_dates=2)
    assert matched['left']['mae_c']==pytest.approx(6)  # equal date mass, not (2+2+10)/3
    assert matched['right']['mae_c']==pytest.approx(4)


def test_late_discovery_accepts_timely_original_availability_but_not_late_outcomes(tmp_path,sources):
    record=compile(tmp_path,sources);at=instant(record.to_dict()['targets'][-1]['target_at'])
    value=score(record,at,assessed=at+timedelta(days=20),available=at+timedelta(days=1))
    assert value['observation']['available_at']==(at+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match='availability'):
        score(record,at,assessed=at+timedelta(days=20),available=at+timedelta(days=8))


def test_revision_is_between_original_decisions_and_never_uses_a_future_issue(tmp_path,sources):
    first=compile(tmp_path,sources);later=tmp_path/'later';later.mkdir(mode=0o700)
    second=compile(later,(*sources[:3],sources[3]+timedelta(minutes=1)),previous=first)
    row=second.to_dict()['targets'][0]
    assert row['forecasts']['actual_serving']['revision_c']==0
    assert row['forecasts']['actual_serving']['previous_decision_sha256']==first.to_dict()['record_sha256']
    assert row['local_issue_age_hours']==pytest.approx(29/60)
    other=tmp_path/'other';other.mkdir(mode=0o700)
    with pytest.raises(ValueError,match='earlier'):
        compile(other,sources,previous=second)


def test_unavailable_comparator_never_becomes_zero_or_easy_target_skill(tmp_path,sources):
    record=compile(tmp_path,sources);at=instant(record.to_dict()['targets'][-1]['target_at'])
    report=api().summarize_refresh_scores([score(record,at)])
    c=comparison(report)
    assert c['matched']['support']['pairs']==0
    assert c['coverage']['left_unavailable']==1 and c['coverage']['right_unavailable']==1
    assert c['matched']['left']['mae_c'] is None


def test_changed_or_conflicting_measured_target_is_rejected(tmp_path,sources):
    record=compile(tmp_path,sources);at=instant(record.to_dict()['targets'][0]['target_at'])
    a=score(record,at);b=score(record,at,observed=19)
    with pytest.raises(ValueError,match='conflicting'):
        api().summarize_refresh_scores([a,b])
    a['forecasts']['actual_serving']['value_c']=99
    with pytest.raises(ValueError,match='unchanged'):
        api().summarize_refresh_scores([a])


def test_raw_comparison_is_not_mislabeled_as_correction_fallback(tmp_path,sources):
    record=compile(tmp_path,sources);at=instant(record.to_dict()['targets'][0]['target_at'])
    c=comparison(api().summarize_refresh_scores([score(record,at)]))
    assert c['coverage']['fallback']==0


from test_near_term_correction import context

def test_same_source_corrected_candidate_has_matched_and_fallback_inclusive_support(tmp_path,context):
    from weather_learning.near_term_correction import prepare_near_term_correction
    args,full,short=context
    near=prepare_near_term_correction(**args)
    root=tmp_path/'publisher';root.mkdir(mode=0o700)
    record=compile(root,(args['archive'],full,short,args['decision_at']),near=near)
    at=instant(record.to_dict()['targets'][0]['target_at'])
    c=comparison(api().summarize_refresh_scores([score(record,at,observed=21)]),'near_term_local_correction_24h_v1_vs_actual_serving')
    assert c['coverage']['corrected']==1 and c['coverage']['fallback']==0
    assert c['corrected_only']['support']['pairs']==1
    assert c['matched']['left']['mae_c']==pytest.approx(1)
    assert c['matched']['right']['mae_c']==pytest.approx(1)
    assert c['cohort']['left_model_sha256']==near.to_dict()['model']['model_sha256']


def test_candidate_only_easy_targets_keeps_corrected_match_and_full_fallback_policy(context,tmp_path):
    from weather_learning.near_term_correction import prepare_near_term_correction
    args,full,short=context
    first_root=tmp_path/'first';first_root.mkdir(mode=0o700)
    first=compile(first_root,(args['archive'],full,short,args['decision_at']),near=prepare_near_term_correction(**args))
    later=args['decision_at']+timedelta(minutes=1)
    near=prepare_near_term_correction(**dict(args,decision_at=later,origin_metadata=None))
    second_root=tmp_path/'second';second_root.mkdir(mode=0o700)
    second=compile(second_root,(args['archive'],full,short,later),near=near,previous=first)
    a=instant(first.to_dict()['targets'][0]['target_at']);b=a+timedelta(hours=1)
    report=api().summarize_refresh_scores([score(first,a,observed=22),score(second,b,observed=24)])
    groups=[c for c in report['comparisons'] if c['comparison']=='near_term_local_correction_24h_v1_vs_actual_serving']
    assert len(groups)==1
    c=groups[0]
    assert c['matched']['support']['pairs']==1
    assert c['fallback_inclusive']['support']['pairs']==2
    assert c['coverage']['corrected']==1 and c['coverage']['fallback']==1
    assert c['matched']['left']['mae_c']==pytest.approx(0)
    assert c['fallback_inclusive']['left']['mae_c']==pytest.approx(2)
    assert c['fallback_inclusive']['right']['mae_c']==pytest.approx(3)
