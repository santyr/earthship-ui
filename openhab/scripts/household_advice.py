#!/usr/bin/env python3
"""Advice publication on the existing cycle; no model training or equipment I/O."""
from pathlib import Path
from hashlib import sha256
from datetime import timedelta
import os,sqlite3,secrets
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household.model_snapshot import restore_snapshot
from household.advice import evaluate_advice
from household.advice.lifecycle import AdviceHistory
from household.advice.shade_state import ShadeHistory
from household_observation import _directory,_private_file
from household.advice.contracts import validate_report


def runtime_manifest():
    root=Path(__file__).resolve().parent
    files=[Path(__file__).resolve(),*sorted((root/'household/advice').glob('*.py')),root/'household_pv_model.py',root/'household_profiled_storage.py',root/'household_ac_load_model.py']
    from household_snapshot import _read
    return {str(p.relative_to(root)):sha256(_read(p,262144)).hexdigest() for p in files}


def _optional(path,default,maximum=32768):
    if not path.exists() and not path.is_symlink():return default
    return loads(_private_file(path,maximum)[0])


def publish_advice(*,snapshot,projections,directory,now,guard):
    directory=Path(directory).absolute();_directory(directory);now=utc(now);guard();runtime=runtime_manifest()
    policy=_optional(directory/'advice-policy.json',None)
    operator=_optional(directory/'advice-operator-state.json',dict(schema='earthship-household-operator-state/v1',declarations=[],checks={}))
    if set(operator)!={'schema','declarations','checks'} or operator['schema']!='earthship-household-operator-state/v1':raise ValueError('closed operator state required')
    history=directory/'shade-observations.sqlite'
    events=[] if not history.exists() else ShadeHistory(history).latest(now=now)
    state=dict(schema='earthship-household-action-state/v1',snapshot_id=snapshot.snapshot_id,declarations=operator['declarations'],shade_reports=events,shade_movements=[] if not history.exists() else ShadeHistory(history).movements()[-26:],checks=operator['checks'])
    # Transient declarations and device state are retained beside, not injected
    # into, the immutable numerical source snapshot.
    report=evaluate_advice(snapshot=snapshot,projections=projections,policy=policy,action_state=state,now=now)
    store=AdviceHistory(directory/'advice.sqlite')
    inputs=dict(snapshot=snapshot.to_dict(),projections=projections,policy=policy,action_state=state,now=now.isoformat())
    store.retain(report,inputs=inputs,runtime=runtime)
    observed=store.observe_targets(events,now=now)
    _publish_observation_and_evaluation(directory,store,events,now,guard)
    guard()
    if runtime_manifest()!=runtime:raise ValueError('advice evaluation runtime changed')
    # Recheck mutable private policy/state bytes before publishing the frozen result.
    if canonical(_optional(directory/'advice-policy.json',None))!=canonical(policy) or canonical(_optional(directory/'advice-operator-state.json',dict(schema='earthship-household-operator-state/v1',declarations=[],checks={})))!=canonical(operator):raise ValueError('advice policy/state changed during evaluation')
    target=directory/'advice.json'
    old=None if not target.exists() else _private_file(target,32768)[0]
    if old==canonical(report):return dict(status='unchanged',report_id=report['report_id'],target_observed_count=len(observed),automatic_actuation=False)
    publish_owned_advice(target,report,guard=guard)
    return dict(status='written',report_id=report['report_id'],target_observed_count=len(observed),automatic_actuation=False)


def replay_retained(path,report_id):
    store=AdviceHistory(path)
    with store._connect() as db:row=db.execute('SELECT raw,inputs,runtime FROM reports WHERE id=?',(report_id,)).fetchone()
    if row is None:raise ValueError('original advice unavailable')
    original,inputs,runtime=map(loads,row)
    if runtime!=runtime_manifest():raise ValueError('replay requires the original versioned producer')
    # Restoring the raw immutable source keeps exact as-issued quality and IDs.
    from household.snapshot import HouseholdSnapshot
    body=inputs['snapshot'];snapshot=HouseholdSnapshot(canonical({k:v for k,v in body.items() if k!='snapshot_id'}))
    if snapshot.snapshot_id!=body['snapshot_id']:raise ValueError('original snapshot changed')
    result=evaluate_advice(snapshot=snapshot,projections=inputs['projections'],policy=inputs['policy'],action_state=inputs['action_state'],now=instant(inputs['now']))
    if result!=original:raise ValueError('rederived original advice differs')
    return result


def publish_cycle_advice(*,record,energy,profiled,directory,now,guard):
    now=utc(now);snapshot=restore_snapshot(record['inputs']['snapshot'],record['inputs'].get('source_contexts'));projections={}
    if energy is not None:
        pv=energy['output']['array_pv'];windows=pv.get('direct_sun_windows',[]);steps=pv.get('steps',[])
        if steps and pv.get('status')=='projected_provisional_array_potential':
            direct=any(instant(w['start'])<=now<instant(w['end']) for w in windows)
            first=next((s for s in steps if instant(s['start'])<=now<instant(s['end'])),None)
            if first is not None:
                projections['solar']=dict(snapshot_id=snapshot.snapshot_id,source_ref=energy['receipt_sha256'],available_at=energy['inputs']['assessed_at'],
                    valid_until=(instant(record['inputs']['now'])+timedelta(seconds=120)).isoformat(),direct_gain_available=direct and first['potential_pv_kwh']>0)
    # Existing household profiles do not identify an individual task's embedded
    # contribution. Require an original explicit attribution before shifting it.
    baseline=_optional(Path(directory)/'advice-energy-baseline.json',None,262144)
    if baseline is not None:
        if energy is None or profiled is None or baseline.get('source_ref')!=profiled['receipt_sha256'] or canonical(baseline.get('steps'))!=canonical(energy['output']['array_pv'].get('steps')) or canonical(baseline.get('baseline_load_forecast'))!=canonical(profiled['output'].get('load_forecast')):raise ValueError('explicit energy task baseline must match current original forecasts')
        projections['flexible_energy']=baseline
    return publish_advice(snapshot=snapshot,projections=projections,directory=directory,now=now,guard=guard)


def publish_owned_advice(path,report,*,guard,validator=validate_report):
    validator(report);encoded=canonical(report);directory=_directory(path.parent)
    try:previous=_private_file(path,32768)
    except FileNotFoundError:previous=None
    if previous is not None and loads(previous[0]).get('schema')!=report['schema']:raise ValueError('advice target belongs to another producer')
    if previous is not None and previous[0]==encoded:
        guard();return 'unchanged'
    temporary=path.parent/('.advice-'+secrets.token_hex(16))
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        guard()
        try:current=_private_file(path,32768)
        except FileNotFoundError:current=None
        if current!=previous or _directory(path.parent)!=directory:raise ValueError('advice publication context changed')
        os.replace(temporary,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        if _private_file(path,32768)[0]!=encoded:raise ValueError('advice publication readback differs')
    finally:
        try:temporary.unlink()
        except FileNotFoundError:pass


def _publish_observation_and_evaluation(directory,store,events,now,guard):
    from household.advice.lifecycle import evaluate_usefulness
    def valid_public(value):
        if len(canonical(value))>32768 or value['automatic_actuation'] is not False:raise ValueError('bounded observational report required')
    observations=[]
    for e in events:
        row={key:e[key] for key in ('shade_id','zone','epoch','position_open_pct','native_position','feedback_basis','movement','origin','observed_at','received_at','available_at','valid_until','quality','time_basis')}
        row['native_convention']=e['mapping']['convention'];observations.append(row)
    view=dict(schema='earthship-shade-observations/v1',generated_at=now.isoformat(),observations=observations,automatic_actuation=False)
    publish_owned_advice(directory/'shade-observations.json',view,guard=guard,validator=valid_public)
    with store._connect() as db:physical=[loads(r[0]) for r in db.execute('SELECT raw FROM physical_feedback ORDER BY rowid DESC LIMIT 32')]
    physical_view=dict(schema='earthship-household-observed-targets/v1',generated_at=now.isoformat(),events=physical,automatic_actuation=False)
    publish_owned_advice(directory/'advice-observed-targets.json',physical_view,guard=guard,validator=valid_public)
    feedback=_optional(directory/'advice-feedback.json',dict(schema='earthship-household-advice-feedback/v1',events=[]),262144)
    report=evaluate_usefulness(store.recent_reports(128),feedback['events']+physical,[]);report.update(generated_at=now.isoformat(),automatic_actuation=False)
    publish_owned_advice(directory/'advice-evaluation.json',report,guard=guard,validator=valid_public)
    from household.advice.evaluation import action_outcome_episodes
    moves=[] if not (directory/'shade-observations.sqlite').exists() else ShadeHistory(directory/'shade-observations.sqlite').movements()
    def original_contexts():
        with store._connect() as db:
            for row in db.execute('SELECT inputs FROM reports ORDER BY at DESC LIMIT 128'):yield loads(row[0])
    contexts=[];outcomes=[]
    for original in original_contexts():
        snapshot=original['snapshot'];at=instant(original['now']);context=dict(available_at=original['now'],snapshot_id=snapshot['snapshot_id'])
        from household.advice import _reading,_declaration
        for domain,role,field in (('thermal','air_temperature','initial_air_f'),('thermal','mass_temperature','initial_mass_f'),('weather','outdoor_temperature','outdoor_f')):
            value=_reading(snapshot,domain,role,at)
            if value is not None:context[field]=value['value']
        solar=original['projections'].get('solar')
        if solar is not None:context['solar_geometry_ref']=solar['source_ref'];context['weather_ref']=solar['source_ref']
        state=original['action_state'];policy=original['policy']
        if policy and policy['ventilation']:
            opening=_declaration(state,policy['ventilation']['target'],'opening',at)
            if opening:context['ventilation_state']=opening['state']
        context['sensor_epochs']={role:row['evidence']['source_epoch'] for rows in snapshot['domains'].values() for role,row in rows.items() if row.get('evidence')}
        contexts.append(context)
        air=snapshot['domains'].get('thermal',{}).get('air_temperature')
        if air and air.get('reason') is None and air.get('value') is not None and air.get('evidence') and air['evidence']['quality']=='qualified':
            outcomes.append(dict(observed_at=air['evidence']['observed_at'] or air['evidence']['received_at'],available_at=air['evidence']['available_at'],temperature_f=air['value'],source_ref=air['evidence']['digest']))
    episodes=action_outcome_episodes(moves[-512:],contexts,outcomes,as_of=now)
    # Full confounder/outcome originals stay private, separate from public advice.
    value=dict(schema='earthship-shade-action-episodes/v1',generated_at=now.isoformat(),episodes=episodes,automatic_actuation=False)
    if len(canonical(value))<=32768:publish_owned_advice(directory/'shade-action-episodes.json',value,guard=guard,validator=valid_public)
