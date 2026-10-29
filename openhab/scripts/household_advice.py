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
    files=[Path(__file__).resolve(),root/'proactive_advice.py',*sorted((root/'household/advice').glob('*.py')),root/'household_pv_model.py',root/'household_profiled_storage.py',root/'household_ac_load_model.py']
    from household_snapshot import _read
    return {str(p.relative_to(root)):sha256(_read(p,262144)).hexdigest() for p in files}


def _optional(path,default,maximum=32768):
    if not path.exists() and not path.is_symlink():return default
    return loads(_private_file(path,maximum)[0])


def publish_advice(*,snapshot,projections,directory,now,guard):
    directory=Path(directory).absolute();_directory(directory);now=utc(now);guard();runtime=runtime_manifest()
    policy=_optional(directory/'advice-policy.json',None)
    provisional=None if policy is not None else _optional(directory/'advice-provisional-preferences.json',None)
    if provisional is not None:
        from household.advice.provisional import validate_preferences
        provisional=validate_preferences(provisional)
        projections={**projections,'provisional_preferences':provisional}
    glazing=_optional(directory/'advice-glazing.json',None)
    if glazing is not None:projections={**projections,'passive_solar_geometry':glazing}
    operator=_optional(directory/'advice-operator-state.json',dict(schema='earthship-household-operator-state/v1',declarations=[],checks={}))
    if set(operator)!={'schema','declarations','checks'} or operator['schema']!='earthship-household-operator-state/v1':raise ValueError('closed operator state required')
    history=directory/'shade-observations.sqlite'
    events=[] if not history.exists() else ShadeHistory(history).latest(now=now)
    state=dict(schema='earthship-household-action-state/v1',snapshot_id=snapshot.snapshot_id,declarations=operator['declarations'],shade_reports=events,shade_movements=[] if not history.exists() else ShadeHistory(history).movements()[-26:],checks=operator['checks'])
    # Transient declarations and device state are retained beside, not injected
    # into, the immutable numerical source snapshot.
    advisory={key:value for key,value in projections.items() if key in ('solar','flexible_energy','energy_context_error','provisional_preferences','thermal_evaluation_context','passive_solar_geometry')}
    report=evaluate_advice(snapshot=snapshot,projections=advisory,policy=policy,action_state=state,now=now)
    store=AdviceHistory(directory/'advice.sqlite')
    inputs=dict(snapshot=snapshot.to_dict(),projections=projections,policy=policy,action_state=state,now=now.isoformat())
    store.retain(report,inputs=inputs,runtime=runtime)
    observed=store.observe_targets(events,now=now)
    guard()
    if runtime_manifest()!=runtime:raise ValueError('advice evaluation runtime changed')
    # Recheck mutable private policy/state bytes before publishing the frozen result.
    if canonical(_optional(directory/'advice-glazing.json',None))!=canonical(glazing) or canonical(None if policy is not None else _optional(directory/'advice-provisional-preferences.json',None))!=canonical(provisional) or canonical(_optional(directory/'advice-policy.json',None))!=canonical(policy) or canonical(_optional(directory/'advice-operator-state.json',dict(schema='earthship-household-operator-state/v1',declarations=[],checks={})))!=canonical(operator):raise ValueError('advice policy/state changed during evaluation')
    target=directory/'advice.json'
    old=None if not target.exists() else _private_file(target,32768)[0]
    status='unchanged' if old==canonical(report) else 'written'
    if status=='written':publish_owned_advice(target,report,guard=guard)
    try:
        _publish_observation_and_evaluation(directory,store,events,now,guard,inputs)
        auxiliary='written'
    except Exception:
        auxiliary='unavailable'
    return dict(status=status,report_id=report['report_id'],target_observed_count=len(observed),auxiliary_status=auxiliary,automatic_actuation=False)


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
    advisory={key:value for key,value in inputs['projections'].items() if key in ('solar','flexible_energy','energy_context_error','provisional_preferences','thermal_evaluation_context','passive_solar_geometry')}
    result=evaluate_advice(snapshot=snapshot,projections=advisory,policy=inputs['policy'],action_state=inputs['action_state'],now=instant(inputs['now']))
    if result!=original:raise ValueError('rederived original advice differs')
    return result


def publish_cycle_advice(*,record,energy,profiled,directory,now,guard,thermal_capture=None):
    now=utc(now);snapshot=restore_snapshot(record['inputs']['snapshot'],record['inputs'].get('source_contexts'));projections={'thermal_evaluation_context': None}
    if energy is not None:
        pv=energy['output']['array_pv'];windows=pv.get('direct_sun_windows',[]);steps=pv.get('steps',[])
        if steps and pv.get('status')=='projected_provisional_array_potential':
            direct=any(instant(w['start'])<=now<instant(w['end']) for w in windows)
            first=next((s for s in steps if instant(s['start'])<=now<instant(s['end'])),None)
            if first is not None:
                projections['solar']=dict(snapshot_id=snapshot.snapshot_id,source_ref=energy['receipt_sha256'],available_at=energy['inputs']['assessed_at'],
                    valid_until=(instant(record['inputs']['now'])+timedelta(seconds=120)).isoformat(),direct_gain_available=direct and first['potential_pv_kwh']>0)
    prepared=record['inputs'].get('thermal_inputs')
    if prepared is not None:
        capture={} if thermal_capture is None else thermal_capture
        fit=capture.get('candidate',{}).get('fit',{});actions=capture.get('inputs',{}).get('action_snapshot',{}).get('actions')
        changes=None
        if isinstance(actions,dict):
            changes=[]
            for kind,event in actions.items():
                if kind=='indoor_shade' or event is None:continue
                if not isinstance(event,dict) or not event.get('received_at') or not event.get('effective_at'):changes=None;break
                if instant(event['received_at'])<=instant(prepared['issue']) and instant(event['effective_at'])<=instant(prepared['issue']):
                    changes.append(dict(action=kind,state=event.get('state'),source=event.get('source'),effective_at=event['effective_at'],received_at=event['received_at'],event_ref=identity(event)))
        endpoints=[]
        roles=capture.get('inputs',{}).get('origin_temperatures',{}).get('roles',{})
        for grid_at,receipt in roles.get('air',{}).get('grid',[])[-288:]:
            if receipt is None:continue
            if all(key in receipt for key in ('temperatureF','receivedAt','storedAt','validUntil','snapshotSha256')):
                endpoints.append(dict(target_at=grid_at,actual_f=receipt['temperatureF'],source_received_at=receipt['receivedAt'],source_stored_at=receipt['storedAt'],valid_until=receipt['validUntil'],source_ref=receipt['snapshotSha256'],known_at=capture['published_at'],basis='original_qualified_native_temperature_grid'))
        projections['thermal_evaluation_context']=dict(prepared=prepared,training_end=fit.get('training_end'),concurrent_changes=changes,temperature_outcomes=endpoints,source_ref=prepared['original_capture_sha256'])
    # Existing household profiles do not identify an individual task's embedded
    # contribution. Require an original explicit attribution before shifting it.
    try:
        baseline=_optional(Path(directory)/'advice-energy-baseline.json',None,262144)
        if baseline is not None:
            if energy is None or profiled is None or baseline.get('source_ref')!=profiled['receipt_sha256'] or canonical(baseline.get('steps'))!=canonical(energy['output']['array_pv'].get('steps')) or canonical(baseline.get('baseline_load_forecast'))!=canonical(profiled['output'].get('load_forecast')):raise ValueError('original energy attribution mismatch')
            projections['flexible_energy']=baseline
    except (OSError,ValueError,TypeError,KeyError):
        projections['energy_context_error']='original_energy_attribution_unavailable'
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


def _publish_observation_and_evaluation(directory,store,events,now,guard,original):
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
    with store._connect() as db:physical_total=db.execute('SELECT count(*) FROM physical_feedback').fetchone()[0]
    physical_view=dict(schema='earthship-household-observed-targets/v1',generated_at=now.isoformat(),events=physical,omitted_count=max(0,physical_total-len(physical)),automatic_actuation=False)
    while len(canonical(physical_view))>32768 and physical_view['events']:
        physical_view['events'].pop();physical_view['omitted_count']+=1
    publish_owned_advice(directory/'advice-observed-targets.json',physical_view,guard=guard,validator=valid_public)
    feedback=_optional(directory/'advice-feedback.json',dict(schema='earthship-household-advice-feedback/v1',events=[]),262144)
    report=evaluate_usefulness(store.recent_reports(128),feedback['events']+physical,[]);report.update(generated_at=now.isoformat(),automatic_actuation=False)
    publish_owned_advice(directory/'advice-evaluation.json',report,guard=guard,validator=valid_public)
    from household.advice.thermal_evaluation import orchestrate
    history=None if not (directory/'shade-observations.sqlite').exists() else ShadeHistory(directory/'shade-observations.sqlite')
    thermal,episodes=orchestrate(store,history,original=original,now=now,guard=guard)
    publish_owned_advice(directory/'shade-thermal-evaluation.json',thermal,guard=guard,validator=valid_public)
    while len(canonical(episodes))>32768 and episodes['episodes']:
        episodes['episodes'].pop();episodes['omitted_count']+=1
    publish_owned_advice(directory/'shade-action-episodes.json',episodes,guard=guard,validator=valid_public)
