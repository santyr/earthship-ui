"""Closed human-advice contract. No actuator intents, permissions or commands."""
from datetime import timedelta
import math,re
from zoneinfo import ZoneInfo
from ..codec import canonical,loads,identity
from ..control_contracts import instant
from ..evidence import digest

SCHEMA='earthship-household-advice/v1'
VERSION='directional-advice-1'
KINDS={'SHADE_POSITION','VENTILATION_WINDOW','FLEXIBLE_LOAD_TIMING'}
DOMAINS={'shades','ventilation','energy'}
STATUSES={'recommendation_available','no_change_recommended','conditional','insufficient_evidence','unavailable'}
REPORT_FIELDS={'schema','evaluation_version','snapshot_id','policy_sha256','evaluated_at','valid_until','timezone','domains','recommendations','human_action_only','automatic_actuation','report_id'}
REC_FIELDS={'recommendation_id','episode_id','snapshot_id','policy_sha256','kind','target','action','action_spec','baseline','comparison','effects','evidence_basis','limitations','conditions','invalidation_triggers','decision_at','start_at','end_at','review_at','valid_until','source_valid_until','source_refs','model_refs','reason','human_action_only','automatic_actuation'}


def closed(value,fields):
    if not isinstance(value,dict) or set(value)!=set(fields):raise ValueError('closed advice fields required')
    return value


def number(value,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('bounded finite number required')
    return value


def name(value):
    if not isinstance(value,str) or re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_. -]{0,79}',value) is None:raise ValueError('bounded logical name required')
    return value


def text(value):
    if not isinstance(value,str) or not 1<=len(value)<=512:raise ValueError('bounded explanation required')
    return value


def validate_report(value):
    closed(value,REPORT_FIELDS)
    if value['schema']!=SCHEMA or value['evaluation_version']!=VERSION or value['human_action_only'] is not True or value['automatic_actuation'] is not False:raise ValueError('human-only advice required')
    if len(canonical(value))>32768:raise ValueError('bounded public report required')
    for key in ('snapshot_id','report_id'):digest(value[key])
    if value['policy_sha256'] is not None:digest(value['policy_sha256'])
    ZoneInfo(value['timezone']);at=instant(value['evaluated_at']);until=instant(value['valid_until'])
    if not timedelta(0)<until-at<=timedelta(minutes=30):raise ValueError('bounded advice lifetime required')
    if not isinstance(value['domains'],dict) or set(value['domains'])!=DOMAINS:raise ValueError('independent domains required')
    for domain,row in value['domains'].items():
        closed(row,{'status','reason','missing','comparison','valid_until'})
        if row['status'] not in STATUSES:raise ValueError('known domain outcome required')
        name(row['reason'])
        if not at<instant(row['valid_until'])<=until:raise ValueError('bounded domain evaluation validity required')
        if not isinstance(row['missing'],list) or len(row['missing'])>16:raise ValueError('bounded missing fields required')
        for missing in row['missing']:name(missing)
        _comparison(row['comparison'])
    recs=value['recommendations']
    if not isinstance(recs,list) or len(recs)>3:raise ValueError('bounded coordinated shortlist required')
    ids=set()
    for rec in recs:
        closed(rec,REC_FIELDS)
        for key in ('recommendation_id','episode_id','snapshot_id','policy_sha256'):digest(rec[key])
        if rec['recommendation_id'] in ids:raise ValueError('duplicate advice refused')
        ids.add(rec['recommendation_id'])
        if rec['snapshot_id']!=value['snapshot_id'] or rec['policy_sha256']!=value['policy_sha256']:raise ValueError('advice source binding differs')
        if rec['kind'] not in KINDS or rec['human_action_only'] is not True or rec['automatic_actuation'] is not False:raise ValueError('known human action required')
        name(rec['target']);text(rec['action']);
        if rec['target'].lower() in ('greywater','feeder','feeding','southoutlet','eastoutlet','set_night_load_override'):raise ValueError('excluded recommendation target')
        spec=rec['action_spec']
        if rec['kind']=='SHADE_POSITION':
            closed(spec,{'position_open_pct','shade_ids'});number(spec['position_open_pct'],0,100)
            if not isinstance(spec['shade_ids'],list) or not 1<=len(spec['shade_ids'])<=26:raise ValueError('required shade targets missing')
            for shade in spec['shade_ids']:name(shade)
        elif rec['kind']=='VENTILATION_WINDOW':
            closed(spec,{'opening_state','window_minutes'})
            if spec['opening_state'] not in ('open','closed'):raise ValueError('physical opening state required')
            number(spec['window_minutes'],1,60)
        else:
            closed(spec,{'scheduled_start'});instant(spec['scheduled_start'])
        text(rec['reason']);_comparison(rec['comparison'])
        if not isinstance(rec['baseline'],dict) or set(rec['baseline'])!={'state','basis','revision'}:raise ValueError('explicit baseline provenance required')
        if rec['evidence_basis'] not in ('rule_based','model_compared','experimental'):raise ValueError('explicit evidence basis required')
        if len(rec['comparison'])<2:raise ValueError('baseline and considered alternative required')
        baseline=rec['baseline'];name(baseline['revision'])
        if baseline['basis'] not in ('operator_declaration','independent_position','declared_scheduled_task'):raise ValueError('known baseline provenance required')
        if rec['kind']=='SHADE_POSITION':
            states=baseline['state'] if isinstance(baseline['state'],list) else [baseline['state']]
            if not 1<=len(states)<=26:raise ValueError('bounded baseline positions required')
            for position in states:number(position,0,100)
            if rec['evidence_basis']=='rule_based' and rec['action_spec']['position_open_pct'] not in (0,100):raise ValueError('partial effect unsupported by directional rule')
        elif rec['kind']=='VENTILATION_WINDOW':
            if baseline['state'] not in ('open','closed'):raise ValueError('explicit opening baseline required')
        else:instant(baseline['state'])
        closed(rec['effects'],{'thermal_f','soc_pct','energy_kwh'})
        if rec['evidence_basis']=='rule_based' and any(v is not None for v in rec['effects'].values()):raise ValueError('numeric effects unsupported by directional rule')
        for effect in rec['effects'].values():
            if effect is not None:number(effect,-10000,10000)
        for key in ('limitations','conditions','invalidation_triggers'):
            if not isinstance(rec[key],list) or len(rec[key])>16:raise ValueError('bounded conditions required')
            for item in rec[key]:text(item)
        for key in ('source_refs','model_refs'):
            if not isinstance(rec[key],list) or not 0<=len(rec[key])<=16:raise ValueError('bounded original references required')
            for ref in rec[key]:digest(ref)
        if not rec['source_refs']:raise ValueError('original evidence required')
        times={key:instant(rec[key]) for key in ('decision_at','start_at','end_at','review_at','valid_until','source_valid_until')}
        if times['decision_at']!=at or not at<=times['start_at']<times['end_at'] or not at<times['review_at']<=times['valid_until']<=min(until,times['source_valid_until'],times['end_at']):raise ValueError('ordered advice clocks required')
        if identity({k:v for k,v in rec.items() if k!='recommendation_id'})!=rec['recommendation_id']:raise ValueError('recommendation identity differs')
    if identity({k:v for k,v in value.items() if k!='report_id'})!=value['report_id']:raise ValueError('report identity differs')
    return loads(canonical(value))


def _comparison(rows):
    if not isinstance(rows,list) or len(rows)>8:raise ValueError('bounded comparison required')
    for row in rows:
        closed(row,{'alternative','outcome','metric','value','unit','horizon_end'})
        text(row['alternative']);text(row['outcome']);name(row['metric']);name(row['unit']);instant(row['horizon_end'])
        if row['value'] is not None:number(row['value'],-100000,100000)
