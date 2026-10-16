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


def _policy_comparison(coordination,proposals,decision):
    """Describe rederived original blocks, never eligibility or performance."""
    from household.owner_policy import OWNER,BLOCKERS
    from household.planning import GATES
    observation=coordination['policy_observations'].get(OWNER)
    value=dict(schema='earthship-household-policy-block-comparison/v1',status='unavailable',reason='source_unavailable',
        owner=OWNER,owner_reason=None,owner_scheduling=None,evaluated_at=None,valid_until=None,
        source_sha256=None,rule_sha256=None,gate=None,comparisons=[],performance_status='unavailable',
        performance_reason='unqualified_effect',physical_permission=False,automatic_actuation=False)
    if observation is not None:
        value.update(owner_reason=observation['reason'],owner_scheduling=observation['scheduling'],
            evaluated_at=observation['evaluated_at'],valid_until=observation['valid_until'],
            source_sha256=observation['source_sha256'],rule_sha256=observation['rule_sha256'])
        if instant(observation['evaluated_at'])>decision:raise ValueError('owner evaluation follows original decision')
        if decision>=instant(observation['valid_until']):value['reason']='source_stale'
        elif observation['reason'] in BLOCKERS:value.update(status='observed_block',reason=None,gate=BLOCKERS[observation['reason']])
        else:value['reason']='eligibility_not_permission' if observation['scheduling']=='conditional' else 'owner_reason_not_comparable'
    for proposal in proposals:
        if proposal['type']!='RUN_GREYWATER_CYCLE':continue
        check=None
        if value['gate'] is not None:
            matches=[row for row in proposal['hard_checks'] if row['rule']==value['gate']]
            if len(matches)==1:check=matches[0]
        status='unknown'
        if check is not None and check['status']!='unknown':
            status='matching_block' if check['status']=='rejected' and check['reason']==GATES[value['gate']] else 'different_gate_result'
        value['comparisons'].append(dict(intent_id=proposal['intent_id'],status=status,shadow_status=None if check is None else check['status']))
    return value



def _qualification_report(view,registry):
    """Evidence observed in this replay; no gate or intent is graduated here.

    Called only after complete pipeline rederivation. Separate outcome,
    uncertainty, owner and release audits are not part of an as-issued plan.
    """
    from household.planning import CAPABILITIES
    missing=(('independent_windows','intent_windows_not_qualified'),
        ('input_stability','input_sensitivity_not_qualified'),
        ('model_error_uncertainty','action_model_error_not_qualified'),
        ('baseline_comparison','policy_performance_not_qualified'),
        ('reason_codes','operator_interpretation_not_qualified'),
        ('no_planner_rollback','separate_release_rollback_not_qualified'),
        ('no_provider_write_path','protected_write_audit_not_bound'),
        ('owner_safety_recheck','owner_physical_safety_not_qualified'))
    families=[]
    def gate(key,observed,reason):
        return dict(id=key,evidence_status='observed' if observed else 'unavailable',reason=reason)
    for kind,capability_id in CAPABILITIES.items():
        capability=registry['capabilities'].get(capability_id)
        proposals=[row for row in view['proposals'] if row['type']==kind]
        unknown=[row for row in proposals if any(check['status']=='unknown' for check in row['hard_checks'])]
        if any(row['selected'] for row in unknown):raise ValueError('unknown original checks cannot authorize a proposal')
        gates=[gate('deterministic_replay',True,'original_plan_replayed'),
            gate('evidence_contracts',capability is not None,'original_source_contracts_replayed' if capability is not None else 'registered_capability_unavailable'),
            gate('hard_constraints',bool(proposals),'original_family_checks_replayed' if proposals else 'no_family_proposal'),
            gate('unknown_fails_closed',bool(unknown),'unknown_checks_blocked_in_original' if unknown else 'unknown_case_not_observed')]
        gates.extend(gate(key,False,reason) for key,reason in missing)
        families.append(dict(intent_type=kind,capability_id=capability_id,owner=None if capability is None else capability['ownerRule'],
            proposal_count=len(proposals),status='not_qualified',release_authorized=False,gates=gates))
    return dict(schema='earthship-household-intent-qualification/v1',scope='original_plan_evidence',status='not_qualified',
        receipt_sha256=view['receipt_sha256'],snapshot_id=view['snapshot_id'],decision_at=view['decision_at'],
        release_authorized=False,automatic_actuation=False,families=families)


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
            ref=row.get('evidence')
            qualified=(row.get('value') is not None and row.get('reason') is None and ref is not None and
                ref.get('quality')=='qualified' and instant(ref['available_at'])<=instant(snapshot['as_of'])<instant(ref['valid_until']))
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
    if inputs['coordination']['schema']=='earthship-shadow-coordination/v3':
        view.update(schema='earthship-household-observation/v3',policy_comparison=_policy_comparison(inputs['coordination'],proposals,decision))
        view['qualification_report']=_qualification_report(view,inputs['registry'])
    if len(canonical(view))>MAX_BYTES:raise ValueError('bounded public observation required')
    return view


import argparse,json,os,stat,sys,ctypes,secrets
from pathlib import Path
from datetime import datetime,timezone
from hashlib import sha256
from household.codec import loads

PUBLIC_FIELDS={'schema','receipt_sha256','snapshot_id','snapshot_as_of','decision_at','verified_at','valid_until','planner_mode',
    'planner_version','authority','automatic_actuation','plan_status','model_identities','candidate_generation','proposals',
    'source_quality','confidence','effects_qualified','policy_comparison'}


def _private_file(path,maximum,*,directory_fd=None):
    if directory_fd is None and path.absolute().resolve()!=path.absolute():raise ValueError('resolved original file required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory_fd)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600 or info.st_size>maximum:
            raise ValueError('bounded owned private file required')
        raw=os.read(fd,maximum+1)
        if len(raw)>maximum:raise ValueError('private file exceeds bound')
        after=os.fstat(fd)
        metadata=lambda item:(item.st_dev,item.st_ino,item.st_mode,item.st_size,item.st_mtime_ns,item.st_ctime_ns)
        if metadata(after)!=metadata(info):raise ValueError('original private file changed')
        return raw,metadata(info)
    finally:os.close(fd)


def _directory(path):
    if path.absolute().resolve()!=path.absolute():raise ValueError('resolved cache directory required')
    info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('owned private cache directory required')
    return info.st_dev,info.st_ino,info.st_mode


def _existing_view(path):
    try:raw,metadata=_private_file(path,MAX_BYTES)
    except FileNotFoundError:return None
    value=loads(raw)
    fields=PUBLIC_FIELDS|({'qualification_report'} if value.get('schema')=='earthship-household-observation/v3' else set()) if isinstance(value,dict) else set()
    if not isinstance(value,dict) or set(value)!=fields or value['schema'] not in ('earthship-household-observation/v1','earthship-household-observation/v2','earthship-household-observation/v3'):
        raise ValueError('existing target is not an observation cache')
    return raw,metadata



def _move_no_replace(directory_fd,source,target):
    # Linux renameat2 pins both names to the verified directory and never
    # destroys a destination introduced concurrently. Refuse unsupported hosts.
    rename=getattr(ctypes.CDLL(None,use_errno=True),'renameat2',None)
    if rename is None:raise ValueError('no-clobber publication unavailable')
    rename.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
    rename.restype=ctypes.c_int
    if rename(directory_fd,os.fsencode(source),directory_fd,os.fsencode(target),1):
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code))


def materialize(receipt_path,output_path,*,clock=lambda:datetime.now(timezone.utc),publication_guard=lambda:None):
    from household_pipeline import pipeline_runtime_manifest,verify_source_closure,thermal_execution_runtime
    from household.pipeline import MAX_BYTES as RECEIPT_BYTES
    publication_guard()
    source,target=Path(receipt_path).absolute(),Path(output_path).absolute()
    if source==target:raise ValueError('original receipt cannot be a publication target')
    directory=_directory(target.parent);previous=_existing_view(target)
    original=_private_file(source,RECEIPT_BYTES);record=loads(original[0]);version=record.get('schema')
    expanded=version in ('earthship-household-model-plan-receipt/v2','earthship-household-model-plan-receipt/v3','earthship-household-model-plan-receipt/v4','earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6')
    configured=version in ('earthship-household-model-plan-receipt/v4','earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6')
    measured=version in ('earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6')
    def runtime():return pipeline_runtime_manifest(expanded=expanded,configured=configured,measured=measured)
    executing=runtime();root=Path(__file__).resolve().parent
    thermal=thermal_execution_runtime(root,record['inputs']['thermal_inputs'])
    own=Path(__file__).read_bytes()
    if expanded:verify_source_closure(record,executing)
    view=observe_pipeline(record,runtime_manifest=executing,thermal_runtime=thermal,observed_at=clock());encoded=canonical(view)
    publication_guard()
    directory_fd=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temp='.household-observation-'+secrets.token_hex(16);displaced=None;published=False;created=False;installed=False;installed_identity=None
    try:
        info=os.fstat(directory_fd)
        if (info.st_dev,info.st_ino,info.st_mode)!=directory:raise ValueError('publication directory changed')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=directory_fd);created=True
        with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        if (_private_file(source,RECEIPT_BYTES)!=original or runtime()!=executing or Path(__file__).read_bytes()!=own or
            thermal_execution_runtime(root,record['inputs']['thermal_inputs'])!=thermal or _directory(target.parent)!=directory or
            _existing_view(target)!=previous or _directory(target.parent)!=directory):
            raise ValueError('source, runtime or publication target changed')
        publication_guard()
        if previous is not None:
            backup='.household-observation-displaced-'+secrets.token_hex(16)
            _move_no_replace(directory_fd,target.name,backup);displaced=backup
            saved=_private_file(Path(backup),MAX_BYTES,directory_fd=directory_fd)
            # Rename may change ctime; original bytes, inode, mode, size and
            # mtime must still match. Unknown displaced files are restored.
            if saved[0]!=previous[0] or saved[1][:-1]!=previous[1][:-1]:
                raise ValueError('publication target changed')
        publication_guard()
        temporary=os.stat(temp,dir_fd=directory_fd,follow_symlinks=False)
        installed_identity=(temporary.st_dev,temporary.st_ino)
        try:os.link(temp,target.name,src_dir_fd=directory_fd,dst_dir_fd=directory_fd,follow_symlinks=False)
        except FileExistsError:raise ValueError('publication target changed') from None
        installed=True
        os.unlink(temp,dir_fd=directory_fd);created=False
        if _private_file(Path(target.name),MAX_BYTES,directory_fd=directory_fd)[0]!=encoded or _directory(target.parent)!=directory:
            raise ValueError('publication readback differs')
        publication_guard()
        os.fsync(directory_fd);published=True
    finally:
        try:
            if installed and not published:
                try:current=os.stat(target.name,dir_fd=directory_fd,follow_symlinks=False)
                except FileNotFoundError:pass
                else:
                    if (current.st_dev,current.st_ino)==installed_identity:os.unlink(target.name,dir_fd=directory_fd)
            if displaced is not None:
                if published:os.unlink(displaced,dir_fd=directory_fd)
                else:
                    # Never overwrite a concurrently introduced target to
                    # restore a displaced file. Keep it private if occupied.
                    try:_move_no_replace(directory_fd,displaced,target.name)
                    except FileExistsError:pass
            if created:os.unlink(temp,dir_fd=directory_fd)
        finally:os.close(directory_fd)
    # Optional reporting consumes this successful replay, never a second model run.
    chronology='unavailable'
    try:
        from household_chronology import retain_and_summarize
        retain_and_summarize(record,view,directory=target.parent,generated_at=clock(),guard=publication_guard)
        chronology='written'
    except (OSError,ValueError):
        pass
    return dict(status='observation_written',receipt_sha256=view['receipt_sha256'],snapshot_id=view['snapshot_id'],
        observation_sha256=sha256(encoded).hexdigest(),planner_mode=view['planner_mode'],automatic_actuation=False,chronology_status=chronology)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    try:report=materialize(args.receipt,args.output)
    except Exception:
        print(json.dumps(dict(status='observation_refused',automatic_actuation=False)),file=sys.stderr);return 1
    print(json.dumps(report));return 0


if __name__=='__main__':raise SystemExit(main())
