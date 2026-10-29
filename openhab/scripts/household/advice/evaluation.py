"""As-of action contexts and matched known-action forecast diagnostics.

Predictions come from the existing thermal framework. No alternative is labeled
as observed; position knowledge does not identify a causal treatment benefit.
"""
from collections import defaultdict
from zoneinfo import ZoneInfo
import math
from ..codec import identity,loads,canonical
from ..control_contracts import instant
from ..evidence import utc

CONFOUNDERS={'initial_air_f','initial_mass_f','outdoor_f','solar_geometry_ref','weather_ref','ventilation_state','concurrent_changes','sensor_epochs','model_training_end'}


def action_outcome_episodes(movements,contexts,outcomes,*,as_of):
    as_of=utc(as_of)
    if len(movements)>512 or len(contexts)>4096 or len(outcomes)>4096:raise ValueError('bounded action evaluation required')
    result=[]
    for move in movements:
        start=instant(move['start_earliest']);stop=instant(move['stop_observed_at'])
        if stop>as_of:continue
        available=[c for c in contexts if instant(c['available_at'])<=start]
        original=max(available,key=lambda c:instant(c['available_at'])) if available else {}
        context={key:original[key] for key in CONFOUNDERS if key in original}
        missing=sorted(CONFOUNDERS-set(context))
        later=[o for o in outcomes if stop<instant(o['observed_at'])<=as_of and instant(o['available_at'])<=as_of]
        value=dict(action=move,context=context,context_available_at=original.get('available_at'),missing_confounders=missing,outcomes=later,
            recommended_action_required=False,causal_benefit_qualified=False,position_aware_qualification='collecting')
        value['episode_receipt_sha256']=identity(value);result.append(value)
    return loads(canonical({'episodes':result}))['episodes']


def compare_known_action_forecasts(rows,*,as_of,timezone_name='America/Denver'):
    as_of=utc(as_of)
    if not isinstance(rows,list) or len(rows)>4096:raise ValueError('bounded matched pairs required')
    matched=[];days=set();windows=set();rejected=0
    for row in rows:
        decision,target,available,trained=map(instant,(row['decision_at'],row['target_at'],row['observed_available_at'],row['training_end']))
        if not trained<decision<target<=available<=as_of or row['context_complete'] is not True:rejected+=1;continue
        if (decision,target) in windows:rejected+=1;continue
        values=[row[key] for key in ('actual_f','coarse_prediction_f','position_prediction_f')]
        if any(type(v) not in (int,float) or not math.isfinite(v) or not -100<=v<=200 for v in values):raise ValueError('finite matched temperature outcomes required')
        matched.append(values);days.add(target.astimezone(ZoneInfo(timezone_name)).date().isoformat());windows.add((decision,target))
    count=len(matched)
    return dict(schema='earthship-shade-known-action-evaluation/v1',pair_count=count,independent_days=len(days),rejected_pairs=rejected,
        coarse_mae_f=None if not count else sum(abs(actual-coarse) for actual,coarse,position in matched)/count,
        position_aware_mae_f=None if not count else sum(abs(actual-position) for actual,coarse,position in matched)/count,
        qualification='collecting',prediction_under_known_actions=True,causal_benefit_qualified=False,unchosen_alternatives_observed=False,
        limitation='Matched later windows measure forecast performance under actual actions; they do not establish optimal actions or causal thermal savings.')
