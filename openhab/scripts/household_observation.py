"""Curated operator inspection after pure original model/plan rederivation."""
import re
from household.codec import canonical
from household.control_contracts import instant
from household.evidence import utc
from household.pipeline import replay_pipeline
from household.intents import EFFECT_UNITS

MAX_BYTES=32768


def _reason(value):
    if value is not None and (not isinstance(value,str) or re.fullmatch('[a-z][a-z0-9_]{0,63}',value) is None):
        raise ValueError('bounded stable public reason required')
    return value


def observe_pipeline(receipt,*,runtime_manifest,thermal_runtime,observed_at):
    observed=utc(observed_at)
    original=replay_pipeline(receipt,runtime_manifest=runtime_manifest,thermal_runtime=thermal_runtime)
    inputs=original['inputs'];output=original['output'];snapshot=inputs['snapshot'];plan=output['plan_receipt']['plan']
    decision=instant(inputs['now'])
    if observed<decision:raise ValueError('observation cannot precede original decision')
    if output['automatic_actuation'] is not False or plan['automatic_actuation'] is not False:raise ValueError('shadow-only inspection required')
    deadlines=[instant(output['no_action_intent']['expiresAt'])];sources=[]
    for domain,rows in sorted(snapshot['domains'].items()):
        for role,row in sorted(rows.items()):
            ref=row.get('evidence');qualified=ref is not None and ref.get('quality')=='qualified'
            until=None if ref is None else ref.get('valid_until')
            if qualified:deadlines.append(instant(until))
            sources.append(dict(domain=domain,role=role,quality_at_issue='qualified' if qualified else 'unavailable',
                current_quality='expired' if qualified and observed>=instant(until) else 'qualified' if qualified else 'unavailable',
                reason=_reason(row.get('reason')),received_at=None if ref is None else ref.get('received_at'),valid_until=until))
    if len(sources)>64:raise ValueError('bounded public source list required')
    models=[]
    for domain in ('energy','thermal'):
        projection=output['projections'][domain]
        if projection is None:continue
        body=projection['output']
        models.append(dict(domain=domain,artifact_sha256=body.get('artifact_sha256'),runtime_sha256=body.get('runtime_sha256'),
            projection_sha256=projection['projection_sha256'],confidence=body.get('confidence','unavailable'),
            qualification=projection.get('input_qualification','not_graduated')))
    decisions={row['intent_id']:row for row in plan['candidate_decisions']};selected=set(plan['selected_intent_ids']);proposals=[]
    for item in output['candidate_intents']:
        result=decisions[item['intentId']]
        checks=[dict(rule=row['rule'],status=row['status'],reason=_reason(row.get('reason'))) for row in result['hard_checks']]
        if len(checks)>32:raise ValueError('bounded public hard checks required')
        proposals.append(dict(intent_id=item['intentId'],type=item['type'],selected=item['intentId'] in selected,
            confidence=item['confidence'],reasons=[_reason(reason) for reason in item['reasonCodes']],
            expected_effects=item['predictedEffects'],effect_units=dict(EFFECT_UNITS),decision_status=result['status'],
            decision_reason=_reason(result['reason']),hard_checks=checks))
    if len(proposals)>8:raise ValueError('bounded public proposals required')
    until=min(deadlines)
    generation=output['candidate_generation']
    view=dict(schema='earthship-household-observation/v1',receipt_sha256=original['receipt_sha256'],snapshot_id=snapshot['snapshot_id'],
        snapshot_as_of=snapshot['as_of'],decision_at=decision.isoformat(),verified_at=observed.isoformat(),valid_until=until.isoformat(),
        planner_mode='shadow' if observed<until and models else 'unavailable',planner_version=plan['planner_version'],authority='none',
        automatic_actuation=False,plan_status=plan['status'],model_identities=models,
        candidate_generation=dict(status=generation['status'],reason=_reason(generation['reason']),input_qualification=generation['input_qualification']),
        proposals=proposals,source_quality=sources,confidence='unavailable',effects_qualified=False,
        policy_comparison=dict(status='unavailable',reason=_reason(plan['baseline_reasons']['current_owner_policy'])))
    if len(canonical(view))>MAX_BYTES:raise ValueError('bounded public observation required')
    return view
