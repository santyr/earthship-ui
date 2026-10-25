"""Bounded, read-only retirement proof shared by packaging and final handoff.

Unknown frozen consumer policies retain their stage. No archived record is
removed. A proof never grants permission to discard an unobserved dependency.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import stat
import time
from household.codec import canonical, loads, identity
from household.control_contracts import instant
from household.evidence import digest

SCHEMA='earthship-native-history-retirement/v1'
POLICIES=tuple('openhab/scripts/'+p for p in (
    'thermal_model/native_operational_io.py','native_thermal_live.py',
    'household_forecast_score.py','household_retained_native_score.py',
    'household_battery_score.py','household_solar_score.py','household_profiled_score.py',
    'household_pv_score.py','household_profiled_state.py','household_energy_state.py',
    'household_observation.py'))
STORES={
    'battery-outcomes':('earthship-household-battery-sample-index/v1','plan','.household-model-plan-v6.json',False),
    'energy-outcomes':('earthship-household-solar-storage-samples/v1','forecast','.household-energy-forecast-v1.json',False),
    'profiled-energy-outcomes':('earthship-household-profiled-energy-samples/v1','forecast','.household-profiled-energy-v1.json',True),
    'captured-pv-outcomes':('earthship-household-captured-pv-samples/v1','forecast','.household-energy-forecast-v1.json',True)}


def index_dependencies(index,*,store,now):
    schema,kind,suffix,compact=STORES[store.name]
    if (not isinstance(index,dict) or set(index)!={'schema','samples'} or index['schema']!=schema or
            not isinstance(index['samples'],dict) or len(index['samples'])>192):
        raise ValueError('bounded original auxiliary sample index required')
    needed=set()
    fields={kind+'_path',kind+'_sha256',kind+'_receipt_sha256','issued_at','cohort_id','retry_after'}
    fields|={'sample_sha256','score_file_sha256'} if compact else {'score_path'}
    for hour,ref in index['samples'].items():
        at=instant(hour)
        if at!=at.replace(minute=0,second=0,microsecond=0) or at>now:raise ValueError('original UTC sample hour required')
        # The PV consumer checks solar row shape even before its age skip.
        if store.name=='energy-outcomes' and (not isinstance(ref,dict) or set(ref)!=fields):raise ValueError('closed solar reference required')
        if at<now-timedelta(days=7):continue
        if not isinstance(ref,dict) or set(ref)!=fields:raise ValueError('closed auxiliary reference required')
        for key in (kind+'_sha256',kind+'_receipt_sha256','cohort_id'):digest(ref[key])
        issue=instant(ref['issued_at'])
        path=Path(ref[kind+'_path'])
        if (not path.is_absolute() or path.resolve()!=path or path.parent.name!='evidence' or
                path.name!=ref[kind+'_sha256']+suffix or issue>now or
                issue.replace(minute=0,second=0,microsecond=0)!=at):raise ValueError('original auxiliary binding differs')
        if ref['retry_after'] is not None and not issue<=instant(ref['retry_after'])<=now+timedelta(minutes=30):raise ValueError('bounded original retry required')
        if compact:
            if (ref['sample_sha256'] is None)!=(ref['score_file_sha256'] is None):raise ValueError('complete original score pair required')
            if ref['sample_sha256'] is not None:
                digest(ref['sample_sha256']);digest(ref['score_file_sha256'])
        elif ref['score_path'] is not None and Path(ref['score_path']).parent!=store:raise ValueError('owned original score required')
        needed.add(str(path.parent.parent))
    return needed


class Inventory:
    def __init__(self,guard):self.guard=guard;self.files={};self.directories={};self.absent=[];self.memberships={};self.deadline=time.monotonic()+30
    def check(self):
        self.guard()
        if time.monotonic()>=self.deadline or len(self.files)>100000:raise ValueError('bounded history proof inventory exceeded')
    def directory(self,path,*,optional=False):
        self.check();path=Path(path)
        if not path.exists() and not path.is_symlink():
            if optional:self.absent.append(str(path));return None
            raise ValueError('missing original history directory')
        info=path.lstat()
        if not path.is_absolute() or path.resolve()!=path or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022:
            raise ValueError('owned history directory required')
        self.directories[str(path)]=[info.st_dev,info.st_ino,info.st_mode,info.st_uid]
        return path
    def read(self,path,maximum=262144,*,optional=False,decode=True):
        from thermal_model.runtime_bundle import _owned_bytes
        self.check();path=Path(path);self.directory(path.parent)
        if not path.exists() and not path.is_symlink() and optional:self.absent.append(str(path));return None
        raw=_owned_bytes(path,maximum);info=path.lstat()
        self.files[str(path)]=dict(sha256=sha256(raw).hexdigest(),identity=[info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns])
        return loads(raw) if decode else raw
    def entries(self,path,maximum):
        directory=self.directory(path)
        result=[]
        with os.scandir(directory) as entries:
            for count,entry in enumerate(entries):
                self.check()
                if count>=maximum:raise ValueError('bounded original history directory inventory required')
                result.append(Path(entry.path))
        self.memberships[str(path)]=[p.name for p in sorted(result)]
        return sorted(result)


def _policy(record):
    root=Path(__file__).resolve().parents[2]
    return all(record['source_manifest'].get(name)==sha256((root/name).read_bytes()).hexdigest() for name in POLICIES)


def assess(references,*,now,guard,state_root=None):
    import household_cycle_deploy as deploy
    now=instant(now.isoformat());refs=list(references)
    if len(refs)>64 or len({r['stage'] for r in refs})!=len(refs):raise ValueError('bounded unique history selections required')
    inv=Inventory(guard);needed=set();roots=set();policies={};settings_by_stage={}
    for ref in refs:
        stage=Path(ref['stage']);digest(ref['deployment_sha256'])
        manifest=inv.read(stage/'deployment.json',131072)
        if inv.files[str(stage/'deployment.json')]['sha256']!=ref['deployment_sha256']:raise ValueError('original history deployment pin differs')
        record=deploy.verify_stage(stage,expected_deployment_sha256=ref['deployment_sha256'])
        policies[str(stage)]={name:record['source_manifest'].get(name) for name in POLICIES}
        if not _policy(record):
            needed.add(str(stage));continue
        cycle=inv.read(stage/'cycle.json',8192);settings=inv.read(cycle['forecast_config'],8192)
        roots.add(settings['evidence_directory'])
        # Keep all eligible metadata hints, not only the three hourly winners.
        # Decode originals as well: mtime alone can never establish expiry.
        for path in inv.entries(stage/'evidence',20000):
            suffix=next((s for s in ('.household-model-plan-v6.json','.household-energy-forecast-v1.json','.household-profiled-energy-v1.json') if path.name.endswith(s)),None)
            if suffix is None:continue
            value=inv.read(path,2097152)
            if path.name!=inv.files[str(path)]['sha256']+suffix:raise ValueError('original auxiliary filename differs')
            if suffix=='.household-model-plan-v6.json':issue=instant(value['inputs']['snapshot']['as_of'])
            elif suffix=='.household-energy-forecast-v1.json':issue=instant(value['output']['array_pv']['origin'])
            else:
                pin=digest(value['inputs']['original_energy_document_sha256']);energy=inv.read(path.parent/(pin+'.household-energy-forecast-v1.json'))
                if energy['receipt_sha256']!=value['inputs']['original_energy_receipt_sha256']:raise ValueError('profile original energy differs')
                issue=instant(energy['output']['array_pv']['origin'])
            stamp=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc)
            if issue>now or stamp>now:raise ValueError('future original auxiliary candidate')
            if suffix!='.household-model-plan-v6.json':
                energy=value if suffix=='.household-energy-forecast-v1.json' else energy
                pin=digest(energy['inputs']['plan_document_sha256']);plan_path=path.parent/(pin+'.household-model-plan-v6.json');inv.read(plan_path,2097152)
                if inv.files[str(plan_path)]['sha256']!=pin:raise ValueError('original auxiliary plan differs')
            if max(issue,stamp)>=now-timedelta(days=7):needed.add(str(stage))
    if not roots:
        return dict(schema=SCHEMA,assessed_at=now.isoformat(),references=refs,retained=refs,retired=[],policies=policies,files=inv.files,directories=inv.directories,absent=[],state_root=str(state_root or Path.home()/'.local/state/household-intel'),archives_modified=False,automatic_actuation=False)
    binding_fields={'schema','capture_sha256','artifact_sha256','runtime_sha256','issued_at','stage','deployment_sha256','model_receipt_path','model_receipt_sha256','automatic_actuation','binding_sha256'}
    for root in sorted(roots):
        inv.directory(root)
        for offset in range(3):
            folder=Path(root)/('origins-'+(now-timedelta(days=offset)).strftime('%Y%m%d'))
            if inv.directory(folder,optional=True) is None:continue
            entries=inv.entries(folder,20000);bindings={};deliveries=[]
            for path in entries:
                if path.name.endswith('.native-serving-model-binding-v1.json'):
                    value=inv.read(path,8192)
                    if (set(value)!=binding_fields or value['schema']!='earthship-native-serving-model-binding/v1' or value['automatic_actuation'] is not False or
                        identity({k:v for k,v in value.items() if k!='binding_sha256'})!=value['binding_sha256'] or
                        path.name!=digest(value['capture_sha256'])+'.native-serving-model-binding-v1.json'):raise ValueError('original native binding differs')
                    at=instant(value['issued_at'])
                    if at>now or folder.name!='origins-'+at.strftime('%Y%m%d'):raise ValueError('original native binding date differs')
                    key=dict(stage=value['stage'],deployment_sha256=digest(value['deployment_sha256']))
                    if key not in refs:raise ValueError('native binding requires unowned selection')
                    if value['stage'] not in settings_by_stage:
                        cycle=inv.read(Path(value['stage'])/'cycle.json',8192)
                        settings_by_stage[value['stage']]=inv.read(cycle['forecast_config'],8192)
                    settings=settings_by_stage[value['stage']]
                    if any(value[k]!=settings[k] for k in ('artifact_sha256','runtime_sha256','model_receipt_path','model_receipt_sha256')):
                        raise ValueError('original native model binding differs')
                    bindings[value['capture_sha256']]=value;needed.add(value['stage'])
                elif path.name.endswith('.native-provisional-delivery-v2.json'):
                    value=inv.read(path,65536);deliveries.append(value)
                    fields={'schema','issued_at','capture_path','capture_sha256','artifact_sha256','runtime_sha256','geometry_series_sha256','receipts','delivery_sha256'}
                    if set(value)!=fields or value['schema']!='earthship-provisional-thermal-delivery/v2':raise ValueError('closed original native delivery required')
                    if identity({k:v for k,v in value.items() if k!='delivery_sha256'})!=value['delivery_sha256'] or path.name!=value['delivery_sha256']+'.native-provisional-delivery-v2.json':raise ValueError('original native delivery differs')
            if len(bindings)>4096 or len(deliveries)>1024:raise ValueError('bounded native history required')
            for value in deliveries:
                binding=bindings.get(value['capture_sha256'])
                if binding is None or any(binding[k]!=value[k] for k in ('issued_at','artifact_sha256','runtime_sha256')):raise ValueError('missing or changed original delivery binding')
                path=Path(value['capture_path'])
                if path.parent!=folder:raise ValueError('original capture outside delivery archive')
                capture=inv.read(path,32000000)
                if capture['capture_sha256']!=value['capture_sha256'] or identity({k:v for k,v in capture.items() if k!='capture_sha256'})!=capture['capture_sha256']:
                    raise ValueError('original native capture binding differs')
    state=Path(state_root) if state_root is not None else Path.home()/'.local/state/household-intel'
    inv.directory(state)
    for name in STORES:
        store=state/name
        if inv.directory(store,optional=True) is None:continue
        index=inv.read(store/'samples.json',optional=True)
        if index is None:continue
        required=index_dependencies(index,store=store,now=now)
        if not required<={r['stage'] for r in refs}:raise ValueError('auxiliary index requires unowned selection')
        needed|=required
        for hour,ref in index['samples'].items():
            if instant(hour)<now-timedelta(days=7):continue
            kind=STORES[name][1];path=Path(ref[kind+'_path']);value=inv.read(path,2097152)
            if inv.files[str(path)]['sha256']!=ref[kind+'_sha256'] or value['receipt_sha256']!=ref[kind+'_receipt_sha256']:raise ValueError('auxiliary indexed original differs')
            energy=value
            if name=='profiled-energy-outcomes':
                pin=digest(value['inputs']['original_energy_document_sha256'])
                energy_path=path.parent/(pin+'.household-energy-forecast-v1.json');energy=inv.read(energy_path)
                if inv.files[str(energy_path)]['sha256']!=pin or energy['receipt_sha256']!=value['inputs']['original_energy_receipt_sha256']:raise ValueError('indexed profiled energy dependency differs')
            if name!='battery-outcomes':
                pin=digest(energy['inputs']['plan_document_sha256']);plan_path=path.parent/(pin+'.household-model-plan-v6.json');inv.read(plan_path,2097152)
                if inv.files[str(plan_path)]['sha256']!=pin:raise ValueError('indexed original plan dependency differs')
            if 'score_path' in ref and ref['score_path'] is not None:inv.read(ref['score_path'],2097152)
            if ref.get('sample_sha256') is not None:
                suffix='.profiled-energy-sample-v1.json' if name=='profiled-energy-outcomes' else '.captured-pv-verified-v1.json'
                sample=store/(ref['sample_sha256']+suffix);sample_value=inv.read(sample,32768)
                raw_suffix='.profiled-energy-outcome-v1.json.gz' if name=='profiled-energy-outcomes' else '.captured-pv-outcome-v1.json.gz'
                raw=store/(ref['score_file_sha256']+raw_suffix);inv.read(raw,32000000,decode=False)
                if inv.files[str(raw)]['sha256']!=ref['score_file_sha256']:raise ValueError('indexed compact score dependency differs')
                if name=='profiled-energy-outcomes':
                    from household_profiled_samples import validate_sample
                    sample_value=validate_sample(sample_value)
                    if (inv.files[str(sample)]['sha256']!=ref['sample_sha256'] or
                        sample_value['profiled_receipt_sha256']!=ref['forecast_receipt_sha256'] or
                        sample_value['output']['cohort_id']!=ref['cohort_id'] or
                        sample_value['output']['origin']['issued_at']!=ref['issued_at']):
                        raise ValueError('indexed compact profile sample binding differs')
                else:
                    from household_pv_samples import validate_sample
                    sample_value=validate_sample(sample_value)
                    if (sample_value['sample_sha256']!=ref['sample_sha256'] or
                        sample_value['inputs']['energy_document_sha256']!=ref['forecast_sha256'] or
                        sample_value['inputs']['energy_receipt_sha256']!=ref['forecast_receipt_sha256'] or
                        sample_value['output']['cohort_id']!=ref['cohort_id'] or
                        sample_value['output']['prediction_context']['issued_at']!=ref['issued_at']):
                        raise ValueError('indexed compact PV sample binding differs')
    retained=[r for r in refs if r['stage'] in needed]
    return dict(schema=SCHEMA,assessed_at=now.isoformat(),references=refs,retained=retained,
        retired=[r for r in refs if r not in retained],policies=policies,files=inv.files,directories=inv.directories,
        absent=sorted(set(inv.absent)),memberships=inv.memberships,state_root=str(state),archives_modified=False,automatic_actuation=False)


def validate_partition(proof):
    fields={'schema','assessed_at','references','retained','retired','policies','files','directories',
        'absent','state_root','archives_modified','automatic_actuation'}
    if (not isinstance(proof,dict) or set(proof) not in (fields,fields|{'memberships'}) or proof['schema']!=SCHEMA or
        proof['archives_modified'] is not False or proof['automatic_actuation'] is not False or
        any(not isinstance(proof[key],dict) for key in ('policies','files','directories')) or
        not isinstance(proof['absent'],list) or not isinstance(proof.get('memberships',{}),dict) or
        not isinstance(proof['state_root'],str) or not Path(proof['state_root']).is_absolute()):
        raise ValueError('closed history retirement proof required')
    def keys(rows):
        if not isinstance(rows,list) or len(rows)>64:raise ValueError('bounded history partition required')
        result=set();stages=set()
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'stage','deployment_sha256'} or not isinstance(row['stage'],str):
                raise ValueError('closed history partition reference required')
            path=Path(row['stage'])
            if not path.is_absolute() or path.resolve()!=path:raise ValueError('owned history partition path required')
            key=(row['stage'],digest(row['deployment_sha256']))
            if row['stage'] in stages:raise ValueError('unique history partition references required')
            result.add(key);stages.add(row['stage'])
        return result
    references=keys(proof['references']);retained=keys(proof['retained']);retired=keys(proof['retired'])
    if retained&retired or retained|retired!=references:
        raise ValueError('disjoint exhaustive history partition required')


def revalidate(proof,*,now,guard):
    validate_partition(proof)
    if proof.get('schema')!=SCHEMA or instant(proof['assessed_at']).date()!=now.date() or instant(proof['assessed_at'])>now:raise ValueError('history proof clock changed')
    current=assess(proof['references'],now=now,guard=guard,state_root=proof['state_root'])
    if current['policies']!=proof['policies']:raise ValueError('original history policy changed')
    for kind in ('files','directories'):
        if any(current[kind].get(path)!=value for path,value in proof[kind].items()):raise ValueError('original history dependency changed or missing')
    for path,names in proof.get('memberships',{}).items():
        if not set(names)<=set(current.get('memberships',{}).get(path,[])):raise ValueError('original history inventory entry removed')
    if any(r not in proof['retained'] for r in current['retained']):raise ValueError('new history dependency requires retired selection')
    return current


def snapshot_guard(proof):
    """Keep final independently scanned inputs fixed through file replacement.

    Timestamp/inode checks supplement the full hashes just recomputed under the
    serving lock. A new publication after final quiescence refuses this attempt.
    """
    directories={path:(Path(path).stat().st_mtime_ns,Path(path).stat().st_ctime_ns) for path in proof['directories']}
    def check():
        for path,expected in proof['files'].items():
            path=Path(path);info=path.lstat()
            actual=[info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns]
            if path.resolve()!=path or actual!=expected['identity']:raise ValueError('final history dependency changed')
        for path,expected in proof['directories'].items():
            info=Path(path).lstat()
            if ([info.st_dev,info.st_ino,info.st_mode,info.st_uid]!=expected or
                    (info.st_mtime_ns,info.st_ctime_ns)!=directories[path]):raise ValueError('final history directory changed')
        for path in proof['absent']:
            if Path(path).exists() or Path(path).is_symlink():raise ValueError('final absent history dependency changed')
    check();return check
