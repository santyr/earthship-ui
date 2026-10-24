"""Pure bounded household decisions, independent of equipment authority."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from ..codec import canonical,loads,identity
from ..evidence import utc
from ..control_contracts import instant
from ..snapshot import HouseholdSnapshot
from .contracts import SCHEMA,VERSION,closed,number,name,validate_report
from .policy import validate_policy,EXCLUDED


def _domain(status,reason,missing=(),comparison=()):
    return dict(status=status,reason=reason,missing=list(missing),comparison=list(comparison))


def _compare(alternative,outcome,end,value=None,metric='directional_thermal_effect',unit='qualitative'):
    return dict(alternative=alternative,outcome=outcome,metric=metric,value=value,unit=unit,horizon_end=end.isoformat())


def _reading(snapshot,domain,role,now):
    row=snapshot['domains'].get(domain,{}).get(role)
    if not row or row.get('reason') is not None or row.get('value') is None:return None
    ref=row.get('evidence');asof=instant(snapshot['as_of']);age=snapshot['temporal_policy']['max_age_seconds'].get(role)
    if not ref or ref.get('quality')!='qualified' or not age:return None
    if not instant(ref['available_at'])<=asof<=now<instant(ref['valid_until']):return None
    observed=instant(ref.get('observed_at') or ref['received_at'])
    if observed>asof or now>=observed+timedelta(seconds=age):return None
    number(row['value'],-200,200)
    return dict(value=row['value'],ref=ref['digest'],until=min(instant(ref['valid_until']),observed+timedelta(seconds=age)))


def _declaration(state,target,kind,now):
    rows=[r for r in state['declarations'] if r['target']==target and r['kind']==kind and instant(r['reported_at'])<=now<instant(r['valid_until'])]
    if not rows:return None
    latest=max(rows,key=lambda r:instant(r['reported_at']))
    if any(r['value']!=latest['value'] and r['reported_at']==latest['reported_at'] for r in rows):return None
    return dict(state=latest['value'],basis='operator_declaration',revision=latest['revision'],until=instant(latest['valid_until']),ref=identity(latest),reported_at=instant(latest['reported_at']))


def _state(value,snapshot_id):
    closed(value,{'schema','snapshot_id','declarations','shade_reports','shade_movements','checks'})
    if value['schema']!='earthship-household-action-state/v1' or value['snapshot_id']!=snapshot_id:raise ValueError('action state snapshot differs')
    if not isinstance(value['declarations'],list) or len(value['declarations'])>64:raise ValueError('bounded declarations required')
    for row in value['declarations']:
        closed(row,{'target','kind','value','reported_at','valid_until','source','revision'});name(row['target']);name(row['revision'])
        if row['source']!='operator' or row['kind'] not in ('shade','opening'):raise ValueError('explicit operator provenance required')
        if row['kind']=='shade':number(row['value'],0,100)
        elif row['value'] not in ('open','closed'):raise ValueError('explicit opening state required')
        if not timedelta(0)<instant(row['valid_until'])-instant(row['reported_at'])<=timedelta(hours=24):raise ValueError('bounded declaration validity required')
    if not isinstance(value['shade_reports'],list) or len(value['shade_reports'])>26:raise ValueError('bounded shade reports required')
    from .shade_state import validate_event
    for event in value['shade_reports']:validate_event(event)
    if len({e['shade_id'] for e in value['shade_reports']})!=len(value['shade_reports']):raise ValueError('duplicate shade state refused')
    if not isinstance(value['shade_movements'],list) or len(value['shade_movements'])>26:raise ValueError('bounded recent movements required')
    for movement in value['shade_movements']:
        if not isinstance(movement,dict) or not {'shade_id','epoch','stop_observed_at','event_refs'}<=set(movement):raise ValueError('retained movement evidence required')
        instant(movement['stop_observed_at'])
    if not isinstance(value['checks'],dict) or len(value['checks'])>8:raise ValueError('bounded condition evidence required')
    for key,row in value['checks'].items():
        if key not in ('rain','wind','security','smoke','occupancy'):raise ValueError('known condition required')
        closed(row,{'clear','observed_at','valid_until','source_ref'})
        if type(row['clear']) is not bool:raise ValueError('explicit condition state required')
        from ..evidence import digest
        digest(row['source_ref'])
        if not instant(row['observed_at'])<instant(row['valid_until']):raise ValueError('condition time order required')
    return loads(canonical(value))


def _recommend(report,policy,kind,target,action,baseline,reason,comparison,sources,conditions=(),effects=None,start=None,end=None,action_spec=None):
    now=instant(report['evaluated_at']);deadline=min(instant(report['valid_until']),*(s['until'] for s in sources),baseline['until'])
    end=end or deadline;start=start or now;deadline=min(deadline,end)
    if deadline<=now:return None
    # Stable for equivalent refreshes; material action/state/policy changes create
    # a new episode. A dismissed suggestion is not revived by a new source hash.
    baseline_public={k:baseline[k] for k in ('state','basis','revision')}
    material_baseline={k:baseline[k] for k in ('state','basis')}
    if baseline['basis']=='independent_position':material_baseline['epoch_state_revision']=baseline['revision']
    relevant=('comfort_min_f','comfort_max_f','minimum_temperature_delta_f','manual_hold_seconds','shades') if kind=='SHADE_POSITION' else ('comfort_min_f','comfort_max_f','minimum_temperature_delta_f','ventilation') if kind=='VENTILATION_WINDOW' else ('energy',)
    material_policy={k:policy[k] for k in relevant}
    episode=dict(version=VERSION,kind=kind,target=target,action_spec=action_spec,baseline=material_baseline,policy_preferences=material_policy)
    r=dict(episode_id=identity(episode),snapshot_id=report['snapshot_id'],policy_sha256=report['policy_sha256'],kind=kind,target=target,
        action=action,action_spec=action_spec,baseline=baseline_public,comparison=comparison,effects=effects or dict(thermal_f=None,soc_pct=None,energy_kwh=None),
        evidence_basis='rule_based',limitations=['Directional comparison; thermal benefit is unqualified. No numeric temperature benefit is established.'] if kind!='FLEXIBLE_LOAD_TIMING' else ['Conditional nominal storage scenario; usable capacity, losses, PV acceptance and forecast errors are unqualified.'],
        conditions=list(conditions),invalidation_triggers=['New physical or declared state','Source expiry','Changed preferences or environmental conditions'],
        decision_at=now.isoformat(),start_at=start.isoformat(),end_at=end.isoformat(),review_at=min(deadline,now+timedelta(seconds=policy['review_seconds'])).isoformat(),
        valid_until=deadline.isoformat(),source_valid_until=min(s['until'] for s in sources).isoformat(),source_refs=sorted(set(s['ref'] for s in sources)|{baseline['ref']}),model_refs=[],
        reason=reason,human_action_only=True,automatic_actuation=False)
    if kind=='FLEXIBLE_LOAD_TIMING':r['evidence_basis']='model_compared'
    r['recommendation_id']=identity(r);report['recommendations'].append(r);return r


def _shade(report,snap,projections,policy,state,now):
    p=policy['shades'];domain='shades'
    if p is None:return _domain('unavailable','shade_policy_missing',['shades'])
    baseline=_declaration(state,p['target'],'shade',now)
    reports={r['shade_id']:r for r in state['shade_reports']}
    physical={}
    for row in state['shade_reports']:
        if row['quality']=='qualified' and instant(row['available_at'])<=now<instant(row['valid_until']):
            key=(row['source'],row['device_id'])
            if key in physical and (row['shade_id'] in p['shade_ids'] or physical[key] in p['shade_ids']):return _domain('insufficient_evidence','shade_mapping_collision',['unique_per_shade_device_mapping'])
            physical[key]=row['shade_id']
    if any(shade in reports for shade in p['shade_ids']):
        # All required members, stopped and independently reported. Never use a
        # group mean, estimated travel time, target command or preview position.
        members=[reports.get(shade) for shade in p['shade_ids']]
        if any(r is None or r['quality']!='qualified' or r['feedback_basis']!='independent_position' or r['movement']!='stopped' or not instant(r['available_at'])<=now<instant(r['valid_until']) for r in members):return _domain('insufficient_evidence','shade_member_unavailable',['per_shade_position'])
        values=[r['position_open_pct'] for r in members]
        if baseline and any(v!=baseline['state'] for v in values):return _domain('conditional','device_declaration_conflict',['resolve_shade_state'])
        baseline=dict(state=values,basis='independent_position',revision=identity([(r['shade_id'],r['epoch'],r['position_open_pct']) for r in members]),until=min(instant(r['valid_until']) for r in members),ref=identity(members),reported_at=max(instant(r['observed_at']) for r in members))
        if any(r['origin']=='manual' and (now-instant(r['observed_at'])).total_seconds()<policy['manual_hold_seconds'] for r in members):return _domain('no_change_recommended','manual_setting_hold')
    if baseline is not None and baseline['basis']=='independent_position' and any(m['shade_id'] in p['shade_ids'] and 0<=(now-instant(m['stop_observed_at'])).total_seconds()<policy['manual_hold_seconds'] for m in state['shade_movements']):return _domain('no_change_recommended','recent_setting_hold')
    if baseline is None:return _domain('insufficient_evidence','shade_state_unknown',['current_shade_position'])
    air=_reading(snap,'thermal','air_temperature',now)
    if air is None:return _domain('insufficient_evidence','indoor_temperature_unavailable',['air_temperature'])
    solar=projections.get('solar')
    if not solar or solar.get('snapshot_id')!=report['snapshot_id'] or not instant(solar['available_at'])<=now<instant(solar['valid_until']):return _domain('insufficient_evidence','solar_gain_basis_unavailable',['terrain_and_solar_gain'])
    closed(solar,{'snapshot_id','source_ref','available_at','valid_until','direct_gain_available'})
    if type(solar['direct_gain_available']) is not bool:raise ValueError('explicit solar evidence required')
    from ..evidence import digest
    digest(solar['source_ref'])
    gain=solar['direct_gain_available'];target=None
    if p['privacy_required']:target=0
    elif gain and air['value']<=policy['comfort_min_f']-policy['minimum_temperature_delta_f']:target=100
    elif gain and air['value']>=policy['comfort_max_f']+policy['minimum_temperature_delta_f']:target=0
    comparison=[_compare('Leave unchanged','Hold the known shade state while independent schedules continue.',now+timedelta(minutes=30))]
    if target is None:return _domain('no_change_recommended','no_directional_thermal_advantage',comparison=comparison)
    values=baseline['state'] if isinstance(baseline['state'],list) else [baseline['state']]
    if all(v==target for v in values):return _domain('no_change_recommended','target_already_observed',comparison=comparison)
    verb='Open' if target else 'Close';reason='Respect the declared privacy preference.' if p['privacy_required'] else 'Admit available solar heat below the comfort band.' if target else 'Reduce additional solar gain at or above the comfort ceiling.'
    comparison.append(_compare(f'{verb} the named shades',reason,now+timedelta(minutes=30)))
    comparison.append(_compare('Wait until later','No action-conditioned timing benefit has been qualified; reassess at the review time.',now+timedelta(minutes=30)))
    sources=[air,dict(ref=solar['source_ref'],until=instant(solar['valid_until']))]
    _recommend(report,policy,'SHADE_POSITION',p['target'],f'{verb} {p["target"]} shades to {target}% open',baseline,reason,comparison,sources,action_spec=dict(position_open_pct=target,shade_ids=p['shade_ids']))
    return _domain('recommendation_available','directional_solar_rule',comparison=comparison)


def _vent(report,snap,projections,policy,state,now):
    p=policy['ventilation']
    if p is None:return _domain('unavailable','ventilation_policy_missing',['ventilation'])
    baseline=_declaration(state,p['target'],'opening',now)
    if baseline is None:return _domain('insufficient_evidence','opening_state_unknown',['opening_state'])
    air=_reading(snap,'thermal','air_temperature',now);out=_reading(snap,'weather','outdoor_temperature',now)
    if air is None or out is None:return _domain('insufficient_evidence','temperature_comparison_unavailable',['indoor_outdoor_temperature'])
    checks=state['checks'];unknown=[];adverse=[];sources=[air,out]
    for key in p['required_checks']:
        r=checks.get(key)
        if not r or not instant(r['observed_at'])<=now<instant(r['valid_until']):unknown.append(key)
        else:
            sources.append(dict(ref=r['source_ref'],until=instant(r['valid_until'])))
            if not r['clear']:adverse.append(key)
    comparison=[_compare('Leave unchanged',f'Hold the declared {baseline["state"]} opening state.',now+timedelta(minutes=p['window_minutes']))]
    favorable=(air['value']>policy['comfort_max_f'] and air['value']-out['value']>=policy['minimum_temperature_delta_f'] and out['value']>=policy['comfort_min_f'])
    if baseline['state']=='open':
        elapsed=(now-baseline['reported_at']).total_seconds()>=p['window_minutes']*60
        if adverse or not favorable or not p['allowed'] or elapsed:
            reason='Close or reassess the opening: '+('adverse '+', '.join(adverse) if adverse else 'the bounded window has elapsed' if elapsed else 'cooling conditions are no longer favorable')+'.'
            comparison.append(_compare('Close and reassess',reason,now+timedelta(minutes=p['window_minutes'])))
            _recommend(report,policy,'VENTILATION_WINDOW',p['target'],f'Close {p["target"]} and reassess',baseline,reason,comparison,sources,action_spec=dict(opening_state='closed',window_minutes=p['window_minutes']))
            return _domain('recommendation_available','close_or_review_window',comparison=comparison)
        return _domain('conditional' if unknown else 'no_change_recommended','reassess_open_window',unknown,comparison)
    if not p['allowed'] or adverse:return _domain('conditional','ventilation_constraint_not_clear',adverse or ['allowed_ventilation_period'],comparison)
    if not favorable:return _domain('no_change_recommended','no_supported_cooling_advantage',comparison=comparison)
    conditions=[f'Check {key} before opening; this condition is unresolved.' for key in unknown]
    end=now+timedelta(minutes=p['window_minutes'])
    comparison.extend([_compare('Open briefly','Cooler outdoor air can provide directional cooling; effect magnitude is unknown.',end),_compare('Wait','Future conditions are unqualified; reassess rather than assume a later advantage.',end)])
    _recommend(report,policy,'VENTILATION_WINDOW',p['target'],f'Consider opening {p["target"]} for at most {p["window_minutes"]} minutes; then close or reassess',baseline,
        'Indoor temperature exceeds the comfort ceiling and outdoor air is cooler. This does not establish clean air, drying, or condensation safety.',comparison,sources,conditions,end=end,action_spec=dict(opening_state='open',window_minutes=p['window_minutes']))
    return _domain('conditional' if unknown else 'recommendation_available','bounded_cooling_window',unknown,comparison)


def evaluate_advice(*,snapshot,projections,policy,action_state,now):
    now=utc(now)
    if not isinstance(snapshot,HouseholdSnapshot):raise ValueError('immutable household snapshot required')
    snap=snapshot.to_dict()
    if not instant(snap['created_at'])<=now or not instant(snap['as_of'])<=now:raise ValueError('snapshot unavailable at decision')
    state=_state(action_state,snapshot.snapshot_id)
    if not isinstance(projections,dict) or len(projections)>16 or len(canonical(projections))>524288:raise ValueError('bounded projections required')
    p=None if policy is None else validate_policy(policy)
    until=now+timedelta(seconds=120 if p is None else p['validity_seconds'])
    r=dict(schema=SCHEMA,evaluation_version=VERSION,snapshot_id=snapshot.snapshot_id,policy_sha256=None if p is None else identity(p),evaluated_at=now.isoformat(),valid_until=until.isoformat(),timezone='America/Denver' if p is None else p['timezone'],domains={},recommendations=[],human_action_only=True,automatic_actuation=False)
    if p is None and projections.get('provisional_preferences',{}).get('enabled') is True:
        from .provisional import evaluate as evaluate_provisional
        evaluate_provisional(r,snap,projections,state,now)
    elif p is None or instant(p['valid_until'])<=now:
        reason='operator_policy_missing' if p is None else 'operator_policy_expired'
        r['domains']={key:_domain('insufficient_evidence',reason,['operator_policy']) for key in ('shades','ventilation','energy')}
    else:
        r['valid_until']=min(until,instant(p['valid_until'])).isoformat()
        from .energy import energy_advice
        for domain,evaluator in (('shades',_shade),('ventilation',_vent),('energy',energy_advice)):
            before=len(r['recommendations'])
            try:r['domains'][domain]=evaluator(r,snap,projections,p,state,now)
            except (ValueError,TypeError,KeyError,OverflowError):
                del r['recommendations'][before:];r['domains'][domain]=_domain('unavailable','domain_evaluation_failed')
        # A thermal conflict is resolved conservatively; never claim a joint optimum.
        heat=next((row for row in r['recommendations'] if row['kind']=='SHADE_POSITION' and row['action_spec']['position_open_pct']==100),None)
        cool=next((row for row in r['recommendations'] if row['kind']=='VENTILATION_WINDOW' and row['action_spec']['opening_state']=='open'),None)
        if heat and cool:
            r['recommendations'].remove(cool);r['domains']['ventilation']=_domain('conditional','thermal_action_conflict',['resolve_heat_capture_versus_cooling'])
    for domain,result in r['domains'].items():
        limits=[instant(r['valid_until'])]
        if result.get('valid_until'):limits.append(instant(result['valid_until']))
        if p is not None and result['status'] in ('recommendation_available','no_change_recommended','conditional'):
            roles=[('thermal','air_temperature')] if domain=='shades' else [('thermal','air_temperature'),('weather','outdoor_temperature')] if domain=='ventilation' else [('energy','battery_soc')] if p['energy'] and p['energy']['loads'] else []
            for source_domain,role in roles:
                reading=_reading(snap,source_domain,role,now)
                if reading is not None:limits.append(reading['until'])
            projection=projections.get('solar' if domain=='shades' else 'flexible_energy' if domain=='energy' else 'ventilation')
            if isinstance(projection,dict) and projection.get('valid_until') and instant(projection['valid_until'])>now:limits.append(instant(projection['valid_until']))
            domain_policy=p.get(domain)
            if domain_policy and domain in ('shades','ventilation'):
                declaration=_declaration(state,domain_policy['target'],'shade' if domain=='shades' else 'opening',now)
                if declaration is not None:limits.append(declaration['until'])
            if domain=='shades' and p['shades']:
                for member in state['shade_reports']:
                    if member['shade_id'] in p['shades']['shade_ids'] and member['quality']=='qualified' and instant(member['available_at'])<=now<instant(member['valid_until']):limits.append(instant(member['valid_until']))
            if domain=='ventilation' and p['ventilation']:
                for key in p['ventilation']['required_checks']:
                    check=state['checks'].get(key)
                    if check and instant(check['observed_at'])<=now<instant(check['valid_until']):limits.append(instant(check['valid_until']))
            for rec in r['recommendations']:
                if rec['kind']=={'shades':'SHADE_POSITION','ventilation':'VENTILATION_WINDOW','energy':'FLEXIBLE_LOAD_TIMING'}[domain]:limits.append(instant(rec['valid_until']))
        result['valid_until']=min(limits).isoformat()
    r['report_id']=identity(r);return validate_report(r)
