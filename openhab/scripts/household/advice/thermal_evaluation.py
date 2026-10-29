"""Bounded, retained sidecar evaluation through the existing thermal framework.

No fitted weights, forecast originals, action journal or equipment are changed.
The existing house-level shade response supports uniform endpoint states only;
partial/mixed feedback is retained but never linearly converted to heat gain.
"""
from dataclasses import replace
from datetime import timedelta
from ..codec import canonical,loads,identity
from ..control_contracts import instant
from ..evidence import utc
from ..thermal_model import PreparedProjection,project,_geometry,NATIVE_SCHEMAS
from thermal_model.installed_shade_dynamics import InstalledShadeDynamics,InstalledShadeForcing
from .shade_state import validate_event
from .evaluation import action_outcome_episodes,compare_known_action_forecasts

HOUSE_SHADES=tuple(f'shade-{i}' for i in range(1,27))


def compare_original_model(prepared,observations,*,training_end,now,guard=lambda:None):
    now=utc(now)
    if not isinstance(prepared,PreparedProjection):raise ValueError('original prepared thermal model required')
    value=prepared.to_dict();issue=instant(value['issue']);guard()
    result=dict(schema='earthship-shade-model-comparison/v1',status='unavailable',reason='complete_house_position_coverage_required',
        decision_at=issue.isoformat(),target_at=(issue+timedelta(hours=1)).isoformat(),training_end=None if training_end is None else utc(training_end).isoformat(),
        prepared_sha256=value['prepared_sha256'],artifact_sha256=value['artifact_sha256'],runtime_sha256=value['runtime_sha256'],
        coarse_prediction_f=None,position_prediction_f=None,position_state={},source_refs=[],causal_benefit_qualified=False,automatic_actuation=False)
    if training_end is None or not utc(training_end)<issue or instant(value['snapshot']['created_at'])>now:
        result['reason']='predecision_model_training_context_required';return result
    rows={}
    for row in observations:
        validate_event(row)
        if row['shade_id'] in rows:raise ValueError('duplicate house shade refused')
        rows[row['shade_id']]=row
    if set(rows)!=set(HOUSE_SHADES):return result
    if any(r['quality']!='qualified' or r['feedback_basis']!='independent_position' or r['movement']!='stopped' or not instant(r['available_at'])<=issue<instant(r['valid_until']) for r in rows.values()):return result
    positions=[rows[k]['position_open_pct'] for k in HOUSE_SHADES]
    result['position_state']={k:dict(position_open_pct=rows[k]['position_open_pct'],epoch=rows[k]['epoch']) for k in HOUSE_SHADES}
    result['source_refs']=[rows[k]['event_sha256'] for k in HOUSE_SHADES]
    if any(p not in (0,100) for p in positions) or len(set(positions))!=1:
        result.update(status='unsupported_position_effect',reason='existing_model_has_no_qualified_partial_or_zone_position_mapping');return result
    coarse=project(prepared)['output'];guard()
    forcings=tuple(InstalledShadeForcing(**{**r,'at':instant(r['at'])}) for r in value['forcings'])
    if value['schema'] in NATIVE_SCHEMAS:
        from native_thermal_model import NativeInstalledShadeDynamics
        from native_joint_shade import NativeJointShadeDynamics,RULE as JOINT_RULE
        from native_irradiance_shade import NativeIrradianceShadeDynamics,RULE as IRRADIANCE_RULE
        if value['schema']==NATIVE_SCHEMAS[1]:
            from ..thermal_weather_conditioning import apply_conditioning
            forcings=apply_conditioning(forcings,value['weather_conditioning'],issue=issue,available=instant(value['inputs_available_at']),initial_outdoor_f=value['initial']['outdoor'])
        model_type=NativeIrradianceShadeDynamics if value['model_rule']==IRRADIANCE_RULE else NativeJointShadeDynamics if value['model_rule']==JOINT_RULE else NativeInstalledShadeDynamics
        model=model_type(tuple(value['coefficients']),geometry=_geometry(value),expected_series_sha256=value['geometry_series_sha256'])
    else:model=InstalledShadeDynamics(tuple(value['coefficients']))
    target=instant(result['target_at']);coarse_point=next((r for r in coarse['trajectory'] if instant(r['at'])==target),None)
    if coarse_point is None:result['reason']='complete_one_hour_model_window_required';return result
    conditioned=tuple(replace(r,indoor_shade_closed=float(positions[0]==0)) for r in forcings if r.at<=target)
    rolled=model.rollout(origin_at=issue,air_f=value['initial']['air'],mass_f=value['initial']['mass'],forcings=conditioned)
    guard()
    result.update(status='predicted_experimental',reason=None,coarse_prediction_f=coarse_point['air_f'],position_prediction_f=float(rolled.states[-1][0]),
        baseline_assumption='original_coarse_journal_state',position_assumption='hold_independently_observed_uniform_house_endpoint_state',
        interpretation='Forecast comparison under known initial state; no causal benefit or partial-position heat-transmission claim.')
    result['prediction_id']=identity(result);return result


def context_from_original(original,at):
    """Only data actually available by the action time can enter its context."""
    from . import _reading,_declaration
    snapshot=original['snapshot'];context=dict(available_at=original['now'],snapshot_id=snapshot['snapshot_id'])
    for domain,role,field in (('thermal','air_temperature','initial_air_f'),('thermal','mass_temperature','initial_mass_f'),('weather','outdoor_temperature','outdoor_f')):
        reading=_reading(snapshot,domain,role,at)
        if reading is not None:context[field]=reading['value']
    model=original['projections'].get('thermal_evaluation_context')
    if model:
        prepared=model['prepared'];context['weather_ref']=prepared['original_capture_sha256']
        context['solar_geometry_ref']=prepared.get('geometry_series_sha256',prepared['original_capture_sha256'])
        if model.get('training_end') and instant(model['training_end'])<at:context['model_training_end']=model['training_end']
        if model.get('concurrent_changes') is not None:context['concurrent_changes']=model['concurrent_changes']
    policy=original['policy'];state=original['action_state']
    if policy and policy['ventilation']:
        opening=_declaration(state,policy['ventilation']['target'],'opening',at)
        if opening:context['ventilation_state']=opening['state']
    context['sensor_epochs']={role:row['evidence']['source_epoch'] for rows in snapshot['domains'].values() for role,row in rows.items() if row.get('evidence')}
    return context


def _stationary_coverage(originals,prediction):
    origin,target=map(instant,(prediction['decision_at'],prediction['target_at']))
    if set(prediction['position_state'])!=set(HOUSE_SHADES):return False
    for shade,state in prediction['position_state'].items():
        rows=sorted((r for r in originals if r['shade_id']==shade and instant(r['available_at'])<=target),key=lambda r:(instant(r['observed_at']),r['sequence']))
        covered=origin
        for row in rows:
            start=max(origin,instant(row['observed_at']),instant(row['available_at']));end=min(target,instant(row['valid_until']))
            if end<=origin or start>=target:continue
            if row['epoch']!=state['epoch'] or row['position_open_pct']!=state['position_open_pct'] or row['movement']!='stopped' or row['quality']!='qualified' or row['feedback_basis']!='independent_position':return False
            if start>covered:return False
            covered=max(covered,end)
        if covered<target:return False
    return True


def orchestrate(store,shade_history,*,original,now,guard):
    """Predict with original models, bind episodes durably, score later windows."""
    now=utc(now);guard();model=original['projections'].get('thermal_evaluation_context');status='original_model_context_unavailable'
    with store._connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS shade_predictions (id TEXT PRIMARY KEY, target TEXT, raw BLOB)')
        db.execute('CREATE TABLE IF NOT EXISTS shade_scores (id TEXT PRIMARY KEY, raw BLOB)')
        db.execute('CREATE TABLE IF NOT EXISTS shade_eval_cursor (id INTEGER PRIMARY KEY, last_row INTEGER)')
        db.execute('CREATE TABLE IF NOT EXISTS shade_episodes (id TEXT PRIMARY KEY, at TEXT, raw BLOB)')
    events=[] if shade_history is None else shade_history.originals()
    if model:
        prepared=PreparedProjection(canonical(model['prepared']))
        if prepared.to_dict()['original_capture_sha256']!=model['source_ref'] or instant(prepared.to_dict()['issue'])!=instant(original['snapshot']['as_of']):raise ValueError('sidecar thermal source differs from original household snapshot')
        observed=[] if shade_history is None else shade_history.latest(now=instant(prepared.to_dict()['issue']))
        prediction=compare_original_model(prepared,observed,training_end=None if model.get('training_end') is None else instant(model['training_end']),now=now,guard=guard)
        status=prediction['status']
        if status=='predicted_experimental':
            prediction['context_complete']=not (set(('initial_air_f','initial_mass_f','outdoor_f','solar_geometry_ref','weather_ref','ventilation_state','concurrent_changes','sensor_epochs','model_training_end'))-set(context_from_original(original,instant(prediction['decision_at']))))
            with store._connect() as db:
                if db.execute('SELECT count(*) FROM shade_predictions').fetchone()[0]>=512:status='prediction_retention_capacity_exhausted'
                else:db.execute('INSERT OR IGNORE INTO shade_predictions VALUES (?,?,?)',(prediction['prediction_id'],prediction['target_at'],canonical(prediction)))
    movements=[] if shade_history is None else shade_history.movements()
    newly_bound=0
    for movement in movements[-512:]:
        if newly_bound>=16:break
        guard();start=instant(movement['start_earliest'])
        with store._connect() as db:
            if db.execute('SELECT 1 FROM shade_episodes WHERE id=?',(movement['episode_id'],)).fetchone():continue
            if db.execute('SELECT count(*) FROM shade_episodes').fetchone()[0]>=512:break
            row=db.execute('SELECT inputs FROM reports WHERE at<=? ORDER BY at DESC LIMIT 1',(start.isoformat(),)).fetchone()
        context=[] if row is None else [context_from_original(loads(row[0]),start)]
        episode=action_outcome_episodes([movement],context,[],as_of=now)[0]
        with store._connect() as db:db.execute('INSERT INTO shade_episodes VALUES (?,?,?)',(movement['episode_id'],movement['stop_observed_at'],canonical(episode)))
        newly_bound+=1
    snapshot=original['snapshot'];row=snapshot['domains'].get('thermal',{}).get('air_temperature');ref=None if row is None else row.get('evidence')
    outcomes=[] if model is None else model.get('temperature_outcomes',[])
    with store._connect() as db:
        cursor=db.execute('SELECT last_row FROM shade_eval_cursor WHERE id=1').fetchone();last=0 if cursor is None else cursor[0]
        query='SELECT rowid,raw FROM shade_predictions WHERE target<=? AND id NOT IN (SELECT id FROM shade_scores) AND rowid>? ORDER BY rowid LIMIT 16'
        pending=db.execute(query,(now.isoformat(),last)).fetchall()
        if not pending:pending=db.execute(query,(now.isoformat(),0)).fetchall()
        if pending:db.execute('INSERT OR REPLACE INTO shade_eval_cursor VALUES (1,?)',(pending[-1][0],))
    for _,raw_prediction in pending:
        guard();prediction=loads(raw_prediction);target=instant(prediction['target_at']);endpoint=None
        for value in outcomes:
            if instant(value['target_at'])==target and instant(value['source_received_at'])<=target<instant(value['valid_until']) and instant(value['known_at'])<=now:
                endpoint=dict(actual_f=value['actual_f'],known_at=value['known_at'],source_ref=value['source_ref']);break
        if endpoint is None and row and row.get('reason') is None and ref and ref['quality']=='qualified' and row.get('value') is not None and instant(ref['available_at'])<=now:
            observed=instant(ref.get('observed_at') or ref['received_at'])
            if target<=observed<=target+timedelta(minutes=2):endpoint=dict(actual_f=row['value'],known_at=ref['available_at'],source_ref=ref['digest'])
        if endpoint is None or not _stationary_coverage(events,prediction):continue
        concurrent=[] if model is None else model.get('concurrent_changes')
        unchanged=concurrent is not None and not any(instant(prediction['decision_at'])<instant(e['effective_at'])<=target for e in concurrent)
        scored=dict(decision_at=prediction['decision_at'],target_at=prediction['target_at'],observed_available_at=endpoint['known_at'],training_end=prediction['training_end'],
            actual_f=endpoint['actual_f'],coarse_prediction_f=prediction['coarse_prediction_f'],position_prediction_f=prediction['position_prediction_f'],context_complete=prediction['context_complete'] and unchanged,source_ref=endpoint['source_ref'])
        with store._connect() as db:db.execute('INSERT OR IGNORE INTO shade_scores VALUES (?,?)',(prediction['prediction_id'],canonical(scored)))
    with store._connect() as db:
        scores=[loads(r[0]) for r in db.execute('SELECT raw FROM shade_scores ORDER BY rowid LIMIT 512')]
        episodes=[loads(r[0]) for r in db.execute('SELECT raw FROM shade_episodes ORDER BY at DESC LIMIT 32')]
        episode_count=db.execute('SELECT count(*) FROM shade_episodes').fetchone()[0]
    summary=compare_known_action_forecasts(scores,as_of=now);summary.update(latest_model_status=status,episode_count=episode_count,generated_at=now.isoformat(),automatic_actuation=False)
    return summary,dict(schema='earthship-shade-action-episodes/v1',generated_at=now.isoformat(),episodes=episodes,omitted_count=max(0,episode_count-len(episodes)),automatic_actuation=False)
