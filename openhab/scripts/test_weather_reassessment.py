"""Paired target/time-block analysis must preserve observation dependence."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest

T=datetime(2026,1,1,tzinfo=timezone.utc)

def rows(n=72):
    result=[]
    for i in range(n):
        target=T+timedelta(hours=i)
        raw=[-2.,1.,3.,-1.,2.,-3.,1.5][i%7]
        result.append(dict(target_at=target,issued_at=target-timedelta(hours=6),target_identity=str(i),forecast_identity=f'{i:064x}',
            observed=10.,predictions=dict(raw=10+raw,incumbent=10+raw*.6,candidate=10+raw*.5)))
    return result


def test_reassessment_is_paired_target_weighted_and_deterministic():
    from weather_learning.reassessment import paired_reassessment
    data=rows();dense=deepcopy(data)
    for row in data[:12]:
        other=deepcopy(row);other['issued_at']-=timedelta(minutes=5);dense.append(other)
    base=paired_reassessment(data,samples=100)
    repeated=paired_reassessment(data*2,samples=100)
    assert repeated==base
    changed=paired_reassessment(dense,samples=100)
    assert changed['support']['unique_measured_targets']==base['support']['unique_measured_targets']==72
    assert changed['support']['forecast_pairs']==84
    for name in ('raw','incumbent','candidate'):
        for metric in ('mae','rmse','bias','p95_absolute_error'):
            assert changed['metrics'][name][metric]==pytest.approx(base['metrics'][name][metric])
    assert base['paired']['candidate_vs_incumbent']['mae_difference']<0
    assert base['qualification']=='retrospective_analysis_not_qualification_or_selection'


def test_few_temporal_blocks_withhold_intervals_but_keep_point_metrics():
    from weather_learning.reassessment import paired_reassessment
    result=paired_reassessment(rows(8),samples=100)
    assert result['metrics']['candidate']['mae']>0
    assert result['uncertainty']['base']['intervals'] is None
    assert 'blocks' in result['uncertainty']['base']['reason']
    assert result['uncertainty']['block_hours']>=6
    assert set(result['uncertainty']['sensitivity'])=={'half','base','double'}


def test_conflicting_shared_target_and_future_origin_are_rejected():
    from weather_learning.reassessment import paired_reassessment
    original=rows(12)
    bad=deepcopy(original[0]);bad['issued_at']-=timedelta(minutes=1);bad['observed']+=1
    with pytest.raises(ValueError,match='conflicting'):
        paired_reassessment(original+[bad],samples=100)
    bad=deepcopy(original);bad[0]['issued_at']=bad[0]['target_at']+timedelta(hours=1)
    with pytest.raises(ValueError,match='future|clock'):
        paired_reassessment(bad,samples=100)


def test_empty_common_population_is_explicitly_unavailable():
    from weather_learning.reassessment import paired_reassessment
    result=paired_reassessment([],samples=100)
    assert result['metrics'] is None and result['support']['unique_measured_targets']==0
    assert result['uncertainty']['reason']=='no_common_qualified_targets'


def test_constant_paired_loss_difference_has_exact_block_interval():
    from random import Random
    from weather_learning.reassessment import paired_reassessment
    generator=Random(91);data=rows(1000)
    for row in data:
        error=1+generator.random()*3
        row['predictions']=dict(raw=11+error,incumbent=10+error,candidate=9.5+error)
    result=paired_reassessment(data,samples=100)
    interval=result['uncertainty']['base']['intervals']['incumbent']
    assert interval['lower']==pytest.approx(-.5)
    assert interval['upper']==pytest.approx(-.5)
    assert result['paired']['candidate_vs_incumbent']['mae_difference']==pytest.approx(-.5)
    assert result['uncertainty']['base']['blocks']>=4


def test_same_issue_clock_distinct_original_source_forecasts_remain_distinct():
    from weather_learning.reassessment import paired_reassessment
    data=rows(12)
    for i,row in enumerate(data):row['forecast_identity']=f'{i:064x}'
    other=deepcopy(data[0]);other['forecast_identity']='f'*64;other['predictions']['raw']+=1
    result=paired_reassessment(data+[other],samples=100)
    assert result['support']['forecast_pairs']==13
    assert result['support']['unique_measured_targets']==12
    other['forecast_identity']=data[0]['forecast_identity']
    with pytest.raises(ValueError,match='conflicting original prediction'):
        paired_reassessment(data+[other],samples=100)
