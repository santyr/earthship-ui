"""Prospective summaries of already replayed plans; no model execution or authority."""
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import os,secrets,re
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household.planning import CAPABILITIES

ADMISSION='earthship-household-chronological-admission/v1'
REPORT='earthship-household-chronological-summary/v1'
MAX_BYTES=32768
MAX_ADMISSIONS=4096
FAMILIES=tuple(CAPABILITIES)
POLICY=('matching_block','different_gate_result','unknown')
MISSING=['statistical_independence','action_effects','baseline_performance','owner_safety','objective_decomposition']


def admit(record,view):
    """Called only at the successful original-plan replay publication boundary."""
    if (record['receipt_sha256']!=view['receipt_sha256'] or record['inputs']['now']!=view['decision_at'] or
        record['inputs']['snapshot']['snapshot_id']!=view['snapshot_id'] or view['automatic_actuation'] is not False):
        raise ValueError('replayed original view binding differs')
    decision=instant(view['decision_at'])
    # Verification time and presentation expiry are not new original decisions.
    original=loads(canonical(view));original['verified_at']=view['decision_at']
    available=bool(view['model_identities']) and decision<instant(view['valid_until'])
    original['planner_mode']='shadow' if available else 'unavailable'
    for row in original['source_quality']:row['current_quality']=row['quality_at_issue']
    models=[{k:row[k] for k in ('domain','artifact_sha256','runtime_sha256')} for row in view['model_identities']]
    versions=dict(planner_version=view['planner_version'],runtime_sha256=identity(record['runtime_manifest']),
        registry_sha256=identity(record['inputs']['registry']),config_sha256=identity(record['inputs']['config']),models=models)
    families={}
    for kind in FAMILIES:
        proposals=[p for p in view['proposals'] if p['type']==kind]
        families[kind]=dict(proposals=len(proposals),selected=sum(p['selected'] for p in proposals),
            hard_blocked=sum(any(c['status'] in ('unknown','rejected') for c in p['hard_checks']) for p in proposals),
            unknown_blocked=sum(any(c['status']=='unknown' for c in p['hard_checks']) for p in proposals))
    comparison=view['policy_comparison']
    policy={key:sum(c['status']==key for c in comparison.get('comparisons',[])) for key in POLICY}
    value=dict(schema=ADMISSION,receipt_sha256=view['receipt_sha256'],document_sha256=identity(record),
        observation_sha256=identity(original),snapshot_id=view['snapshot_id'],decision_at=view['decision_at'],
        original_valid_until=view['valid_until'],horizon_hours=record['inputs']['config']['horizon_hours'],versions=versions,
        planner_available=available,unavailable_sources=any(s['quality_at_issue']!='qualified' for s in view['source_quality']),
        families=families,policy_comparisons=policy,automatic_actuation=False)
    value['admission_sha256']=identity(value)
    return value


def _validate(row):
    fields={'schema','receipt_sha256','document_sha256','observation_sha256','snapshot_id','decision_at','original_valid_until',
        'horizon_hours','versions','planner_available','unavailable_sources','families','policy_comparisons','automatic_actuation','admission_sha256'}
    if (not isinstance(row,dict) or set(row)!=fields or row['schema']!=ADMISSION or row['automatic_actuation'] is not False or
        identity({k:v for k,v in row.items() if k!='admission_sha256'})!=row['admission_sha256'] or
        type(row['horizon_hours']) is not int or row['horizon_hours'] not in (6,12,24) or
        type(row['planner_available']) is not bool or type(row['unavailable_sources']) is not bool or
        not isinstance(row['families'],dict) or not isinstance(row['policy_comparisons'],dict) or
        set(row['families'])!=set(FAMILIES) or set(row['policy_comparisons'])!=set(POLICY)):
        raise ValueError('bounded original admission required')
    digest=lambda v:isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) is not None
    if any(not digest(row[k]) for k in ('receipt_sha256','document_sha256','observation_sha256','snapshot_id','admission_sha256')):
        raise ValueError('original identity required')
    versions=row['versions']
    if (not isinstance(versions,dict) or set(versions)!={'planner_version','runtime_sha256','registry_sha256','config_sha256','models'} or
        not isinstance(versions['planner_version'],str) or re.fullmatch('[a-z][a-z0-9_]{0,63}',versions['planner_version']) is None or
        any(not digest(versions[k]) for k in ('runtime_sha256','registry_sha256','config_sha256')) or
        not isinstance(versions['models'],list) or len(versions['models'])>2):raise ValueError('bounded version provenance required')
    for model in versions['models']:
        if (not isinstance(model,dict) or set(model)!={'domain','artifact_sha256','runtime_sha256'} or model['domain'] not in ('energy','thermal') or
            any(model[k] is not None and not digest(model[k]) for k in ('artifact_sha256','runtime_sha256'))):raise ValueError('bounded model provenance required')
    for family in row['families'].values():
        if (not isinstance(family,dict) or set(family)!={'proposals','selected','hard_blocked','unknown_blocked'} or
            any(type(n) is not int or not 0<=n<=8 for n in family.values()) or
            family['selected']+family['hard_blocked']>family['proposals'] or family['unknown_blocked']>family['hard_blocked']):
            raise ValueError('original proposal counts differ')
    if any(type(n) is not int or not 0<=n<=8 for n in row['policy_comparisons'].values()):raise ValueError('original comparisons differ')
    instant(row['original_valid_until']);instant(row['decision_at'])
    if len(canonical(row))>MAX_BYTES:raise ValueError('bounded original admission required')


def _counts(rows,kind=None):
    if kind is not None:rows=[r for r in rows if r['families'][kind]['proposals']]
    selected=[];until=None
    for row in sorted(rows,key=lambda r:(instant(r['decision_at'])+timedelta(hours=r['horizon_hours']),r['receipt_sha256'])):
        start=instant(row['decision_at'])
        if until is None or start>=until:
            selected.append(row);until=start+timedelta(hours=row['horizon_hours'])
    def total(key):return sum(sum(f[key] for f in r['families'].values()) if kind is None else r['families'][kind][key] for r in rows)
    return dict(raw_decisions=len(rows),origin_days=len({instant(r['decision_at']).astimezone(ZoneInfo('America/Denver')).date() for r in rows}),
        non_overlapping_windows=len(selected),planner_available=sum(r['planner_available'] for r in rows),
        decisions_with_unavailable_sources=sum(r['unavailable_sources'] for r in rows),
        proposals=total('proposals'),selected=total('selected'),hard_blocked=total('hard_blocked'),unknown_blocked=total('unknown_blocked'))


def summarize(admissions,*,generated_at):
    generated=utc(generated_at);start=generated-timedelta(days=7);unique={}
    for row in admissions:
        _validate(row);decision=instant(row['decision_at'])
        if decision>generated:raise ValueError('admission follows report clock')
        if decision<start:continue
        key=row['receipt_sha256']
        if key in unique and unique[key]!=row:raise ValueError('original admission conflicts')
        unique[key]=row
        if len(unique)>MAX_ADMISSIONS:raise ValueError('bounded chronological window required')
    rows=sorted(unique.values(),key=lambda r:(instant(r['decision_at']),r['receipt_sha256']))
    groups=defaultdict(list)
    for row in rows:groups[identity(row['versions'])].append(row)
    if len(groups)>16:raise ValueError('bounded version groups required')
    value=dict(schema=REPORT,generated_at=generated.isoformat(),valid_until=(generated+timedelta(minutes=15)).isoformat(),
        window_start=start.isoformat(),window_days=7,timezone='America/Denver',sampling_basis='distinct_original_replayed_plans',
        counts=_counts(rows),families={kind:_counts(rows,kind) for kind in FAMILIES},
        policy_comparisons={key:sum(r['policy_comparisons'][key] for r in rows) for key in POLICY},
        first_decision_at=None if not rows else rows[0]['decision_at'],last_decision_at=None if not rows else rows[-1]['decision_at'],
        last_receipt_sha256=None if not rows else rows[-1]['receipt_sha256'],
        retained_set_sha256=identity([r['admission_sha256'] for r in rows]),
        version_groups=[dict(version_id=key,versions=group[0]['versions'],counts=_counts(group),
            families={kind:_counts(group,kind) for kind in FAMILIES}) for key,group in sorted(groups.items())],
        missing_evidence=MISSING,statistical_independence_assessed=False,release_authorized=False,automatic_actuation=False)
    value['report_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded chronological report required')
    return value


def _publish(path,value,guard):
    from household_observation import _directory,_private_file
    directory=_directory(path.parent);encoded=canonical(value)
    try:previous=_private_file(path,MAX_BYTES)
    except FileNotFoundError:previous=None
    if previous is not None and loads(previous[0]).get('schema')!=REPORT:raise ValueError('report target belongs to another producer')
    temporary=path.parent/('.chronology-'+secrets.token_hex(16))
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        guard()
        try:current=_private_file(path,MAX_BYTES)
        except FileNotFoundError:current=None
        if current!=previous or _directory(path.parent)!=directory:raise ValueError('report publication changed')
        os.replace(temporary,path)
        if _private_file(path,MAX_BYTES)[0]!=encoded:raise ValueError('report readback differs')
    finally:temporary.unlink(missing_ok=True)


def retain_and_summarize(record,view,*,directory,generated_at,guard):
    """Single scheduled writer; eight bounded day directories, no history replay."""
    from household_observation import _directory,_private_file
    root=Path(directory);_directory(root);generated=utc(generated_at);admission=admit(record,view)
    day=instant(admission['decision_at']).astimezone(ZoneInfo('America/Denver')).date()
    store=root/'chronological-admissions';store.mkdir(mode=0o700,exist_ok=True);_directory(store)
    bucket=store/day.isoformat();bucket.mkdir(mode=0o700,exist_ok=True);_directory(bucket)
    target=bucket/(admission['receipt_sha256']+'.json');encoded=canonical(admission)
    guard()
    try:previous=_private_file(target,MAX_BYTES)
    except FileNotFoundError:previous=None
    if previous is None:
        temp=bucket/('.admission-'+secrets.token_hex(16))
        try:
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            _directory(bucket);guard();os.link(temp,target,follow_symlinks=False)
        finally:temp.unlink(missing_ok=True)
    elif previous[0]!=encoded:raise ValueError('original admission changed')
    rows=[];today=generated.astimezone(ZoneInfo('America/Denver')).date()
    for offset in range(8):
        folder=store/(today-timedelta(days=offset)).isoformat()
        if not folder.exists():continue
        guard();before=_directory(folder)
        with os.scandir(folder) as entries:
            for entry in entries:
                if len(rows)>=MAX_ADMISSIONS:raise ValueError('bounded chronological store required')
                raw,_=_private_file(Path(entry.path),MAX_BYTES);row=loads(raw);_validate(row)
                if entry.name!=row['receipt_sha256']+'.json' or instant(row['decision_at']).astimezone(ZoneInfo('America/Denver')).date().isoformat()!=folder.name:
                    raise ValueError('original admission location differs')
                rows.append(row)
        if _directory(folder)!=before:raise ValueError('admission directory changed')
    report=summarize(rows,generated_at=generated);guard();_publish(root/'chronological-summary.json',report,guard)
    return report
