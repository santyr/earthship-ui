"""Durable verification of original emitted marginals, with no fit or promotion.

The fixed lead sample is independent of outcomes. Discovery/assessment may be
late; the seven-day limit applies to original observation availability only.
The new namespace cannot reinterpret or replace legacy point-score receipts.
"""
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json,os,shutil,sqlite3,stat,tempfile
from household_job_budget import AdmissionDeferred
from .capability_publish import MAX_BYTES,validate_capability_report
from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc
from .features import TemperatureOutcome,local_temperature_outcome
from .shadow import _directory,_read

OFFSETS=(1,3,6,12,24,48,72,120,168,240,336)
CONTRACT=dict(schema='earthship-raw-temperature-verification/v1',offsets_from_first_future_hour=OFFSETS,
    maturity_minutes=2,arrival_allowance_days=7,maximum_attempts=8,
    quantile_tolerance_c=1e-9,
    population='every_retained_supplemental_issue_at_predeclared_leads',
    weights='equal_local_target_dates_then_equal_targets_then_equal_issued_forecasts',
    scores='pinball_p10_p90_IS80_inclusive_coverage_width_mean_MAE_WIS_only_with_actual_median')
CONTRACT_SHA256=identity(CONTRACT)
DATABASE='capability-scores.sqlite3'
MAX_DATABASE_BYTES=64*1024**2

def temperature_range_score(report,row,outcome,*,observation_policy_sha256):
    """Score a literal original row against one qualified, timely local label."""
    from weather_temperature_evidence import sensor_epoch_id
    report=validate_capability_report(report);policy=digest(observation_policy_sha256)
    if row not in report['groups']['temperature']['hours'] or row['range_status']!='available':
        raise ValueError('original emitted range required')
    at=instant(row['valid_at'])
    if (not isinstance(outcome,TemperatureOutcome) or utc(outcome.target_at)!=at or not finite(outcome.value_c) or
            not at<=utc(outcome.available_at)<=min(utc(outcome.assessed_at),at+timedelta(days=7))):
        raise ValueError('matching mature timely original local observation required')
    sensor_epoch_id(outcome.sensor_epoch);digest(outcome.receipt_digest)
    y=outcome.value_c;low,high=row['p10_c'],row['p90_c'];width=max(0,high-low)
    interval=width+10*max(0,low-y)+10*max(0,y-high)
    def pinball(q,p):return (p-(y<q))*(y-q)
    source=next(s for s in report['sources'] if s['snapshot_sha256']==row['source_sha256'])
    value=dict(schema='earthship-raw-temperature-score/v1',contract_sha256=CONTRACT_SHA256,
        issue_sha256=report['report_sha256'],issued_at=report['generated_at'],target_at=at.isoformat(),
        local_target_date=at.astimezone(ZoneInfo(report['timezone'])).date().isoformat(),source=source,
        issued={k:v for k,v in row.items() if k.endswith('_c')},
        observation=dict(value_c=y,available_at=utc(outcome.available_at).isoformat(),receipt_sha256=outcome.receipt_digest,
            sensor_epoch=outcome.sensor_epoch,policy_sha256=policy),assessed_at=utc(outcome.assessed_at).isoformat(),
        mean_absolute_error_c=abs(y-row['mean_c']),p10_pinball_c=pinball(low,.1),p90_pinball_c=pinball(high,.9),
        interval_score_80_c=interval,width_c=width,covered_80=low-1e-9<=y<=high+1e-9,
        wis_c=None if row['p50_c'] is None else (.5*abs(y-row['p50_c'])+.1*interval)/1.5,
        local_coverage_qualified=False,automatic_actuation=False)
    value['score_sha256']=identity(value)
    return value

class CapabilityScores:
    def __init__(self,state,*,db_path=None):
        self.state=state;self.db=state.root/DATABASE if db_path is None else Path(db_path)
        if not self.db.is_absolute() or self.db.parent.resolve()!=self.db.parent or not self.db.is_relative_to(state.root):
            raise ValueError('private capability index namespace required')
        _directory(self.db.parent)
        fd=os.open(self.db,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:
                raise ValueError('private owned capability index required')
        finally:os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS issues (digest TEXT PRIMARY KEY, issued TEXT NOT NULL, published INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS targets (key TEXT PRIMARY KEY, issue TEXT NOT NULL, target TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS targets_due ON targets(target,key)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (scope TEXT, key TEXT, retry TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(scope,key))')
            db.execute('CREATE TABLE IF NOT EXISTS scores (scope TEXT, key TEXT, target TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(scope,key))')
            db.execute('CREATE INDEX IF NOT EXISTS scores_window ON scores(scope,target,key)')

    @contextmanager
    def connect(self):
        if shutil.disk_usage(self.state.root).free<32*1024**2:raise ValueError('capability index disk headroom exhausted')
        db=sqlite3.connect(self.db,timeout=2)
        try:
            db.execute('PRAGMA cache_size=-2048');db.execute('PRAGMA synchronous=FULL')
            pagesize=db.execute('PRAGMA page_size').fetchone()[0]
            maximum=db.execute('PRAGMA max_page_count='+str(MAX_DATABASE_BYTES//pagesize)).fetchone()[0]
            if maximum*pagesize>MAX_DATABASE_BYTES:raise ValueError('capability index capacity exceeded')
            with db:yield db
        finally:db.close()

    def register(self,value):
        value=validate_capability_report(value);name=value['report_sha256']
        original=_read(self.state.root/'capability-issues'/(name+'.json'),MAX_BYTES)
        if original!=value:raise ValueError('retained capability original differs')
        issued=instant(value['generated_at']);first=issued.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO issues VALUES (?,?,0)',(name,issued.isoformat()))
            for row in value['groups']['temperature']['hours']:
                at=instant(row['valid_at']);offset=(at-first).total_seconds()/3600+1
                if row['range_status']=='available' and offset in OFFSETS:
                    key=identity(dict(issue=name,target=at.isoformat(),contract_sha256=CONTRACT_SHA256))
                    db.execute('INSERT OR IGNORE INTO targets VALUES (?,?,?)',(key,name,at.isoformat()))

    def confirm(self,value):
        """Only successful atomic cache publication makes prepared work due."""
        if _read(self.state.root/'weather-capabilities.json',MAX_BYTES)!=value:
            raise ValueError('published capability cache differs')
        with self.connect() as db:
            db.execute('UPDATE issues SET published=1 WHERE digest=?',(value['report_sha256'],))

    def recover_latest(self):
        # A crash after cache fsync and before index confirmation must not lose
        # original work. The single publisher reconciles before replacing it.
        try:
            value=validate_capability_report(_read(self.state.root/'weather-capabilities.json',MAX_BYTES))
            self.register(value);self.confirm(value);return True
        except (OSError,ValueError,KeyError,TypeError):return False

    def due(self,scope,now,limit):
        with self.connect() as db:
            return db.execute('SELECT t.key,t.issue,t.target FROM targets t JOIN issues i ON i.digest=t.issue AND i.published=1 LEFT JOIN scores s ON s.scope=? AND s.key=t.key '
                'LEFT JOIN attempts a ON a.scope=? AND a.key=t.key WHERE s.key IS NULL AND t.target<=? '
                'AND (a.retry IS NULL OR a.retry<=?) ORDER BY t.target,t.key LIMIT ?',
                (scope,scope,(now-timedelta(minutes=2)).isoformat(),now.isoformat(),limit)).fetchall()

    def defer(self,scope,key,now,reason):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?,?)',
            (scope,key,(now+timedelta(hours=1)).isoformat(),reason))

def _summarize(scores):
    groups={}
    metrics=('mean_absolute_error_c','p10_pinball_c','p90_pinball_c','interval_score_80_c','width_c','covered_80','wis_c')
    for s in scores:
        cohort=dict(grid_sha256=s['source']['grid_sha256'],sensor_epoch=s['observation']['sensor_epoch'],
            observation_policy_sha256=s['observation']['policy_sha256'],contract_sha256=CONTRACT_SHA256)
        key=identity(cohort);group=groups.setdefault(key,dict(cohort=cohort,rows=[]));group['rows'].append(s)
    result=[]
    for key,group in sorted(groups.items()):
        days={}
        for s in group['rows']:days.setdefault(s['local_target_date'],{}).setdefault(s['target_at'],[]).append(s)
        average={}
        for metric in metrics:
            by_day=[]
            for targets in days.values():
                by_target=[]
                for rows in targets.values():
                    values=[s[metric] for s in rows if s[metric] is not None]
                    if values:by_target.append(sum(values)/len(values))
                if by_target:by_day.append(sum(by_target)/len(by_target))
            average['coverage_80' if metric=='covered_80' else metric]=sum(by_day)/len(by_day) if by_day else None
        result.append(dict(cohort_sha256=key,**group['cohort'],issued_forecast_rows=len(group['rows']),
            independent_targets=sum(map(len,days.values())),independent_local_dates=len(days),raw_range=average,
            median_scored_rows=sum(s['wis_c'] is not None for s in group['rows']),local_coverage_qualified=False))
    return result

def monitor_capabilities(state,*,now,sensor_epoch,observation_policy_sha256,read_temperature,limit=8,apply=False,guard=lambda:None):
    """At most eight local label attempts; preview copies the private index."""
    from weather_temperature_evidence import sensor_epoch_id
    now=utc(now);epoch=sensor_epoch_id(sensor_epoch);policy=digest(observation_policy_sha256)
    if type(limit) is not int or not 0<=limit<=8 or type(apply) is not bool:raise ValueError('bounded explicit capability assessment required')
    scope=identity(dict(sensor_epoch=epoch,observation_policy_sha256=policy,contract_sha256=CONTRACT_SHA256))
    guard()
    if not (state.root/DATABASE).exists():
        return dict(status='not_enabled',observations_attempted=0,scored=0,pending=0,cohorts=[],local_coverage_qualified=False)
    if not apply:
        # SQLite backup includes committed rows without copying an active journal.
        with tempfile.TemporaryDirectory(prefix='capability-preview-',dir=state.root) as directory:
            source=CapabilityScores(state);path=Path(directory)/DATABASE
            with source.connect() as old:
                new=sqlite3.connect(path)
                try:old.backup(new)
                finally:new.close()
            path.chmod(0o600)
            return _monitor(CapabilityScores(state,db_path=path),scope,now,epoch,policy,read_temperature,limit,False,guard)
    return _monitor(CapabilityScores(state),scope,now,epoch,policy,read_temperature,limit,True,guard)

def _monitor(queue,scope,now,epoch,policy,read_temperature,limit,apply,guard):
    withheld={};attempted=scored=0
    guard();queue.recover_latest();guard()
    def defer(key,reason):
        withheld[reason]=withheld.get(reason,0)+1;queue.defer(scope,key,now,reason)
    for key,name,target in queue.due(scope,now,limit):
        guard();at=instant(target)
        try:
            original=validate_capability_report(_read(queue.state.root/'capability-issues'/(digest(name)+'.json'),MAX_BYTES))
            if original['report_sha256']!=name:raise ValueError('original issue identity differs')
            row=next(row for row in original['groups']['temperature']['hours'] if instant(row['valid_at'])==at)
        except FileNotFoundError:defer(key,'missing_original');continue
        except (OSError,ValueError,KeyError,TypeError,StopIteration):defer(key,'invalid_original');continue
        try:
            attempted+=1;metadata=read_temperature([at],now);guard()
            if not isinstance(metadata,dict):raise ValueError('qualified observation mapping required')
            if at not in metadata:defer(key,'observation_missing');continue
            outcome=local_temperature_outcome(metadata[at],target_at=at,assessed_at=now,sensor_epoch=epoch)
            score=temperature_range_score(original,row,outcome,observation_policy_sha256=policy)
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception:guard();defer(key,'quality_withheld');continue
        with queue.connect() as db:
            db.execute('INSERT OR IGNORE INTO scores VALUES (?,?,?,?)',(scope,key,target,canonical(score).decode()))
            db.execute('DELETE FROM attempts WHERE scope=? AND key=?',(scope,key))
        scored+=1
    guard()
    with queue.connect() as db:
        pending=db.execute('SELECT COUNT(*) FROM targets t JOIN issues i ON i.digest=t.issue AND i.published=1 LEFT JOIN scores s ON s.scope=? AND s.key=t.key WHERE s.key IS NULL',(scope,)).fetchone()[0]
        unconfirmed=db.execute('SELECT COUNT(*) FROM issues WHERE published=0').fetchone()[0]
        rows=db.execute('SELECT body FROM scores WHERE scope=? AND target>=? AND target<=? ORDER BY target,key LIMIT 10001',
            (scope,(now-timedelta(days=28)).isoformat(),now.isoformat())).fetchall()
        total=db.execute('SELECT COUNT(*) FROM scores WHERE scope=?',(scope,)).fetchone()[0]
        capacity=dict(allocated_bytes=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0],maximum_bytes=MAX_DATABASE_BYTES)
    scores=[json.loads(row[0]) for row in rows[:10000]]
    report=dict(schema='earthship-capability-performance/v1',generated_at=now.isoformat(),valid_until=(now+timedelta(hours=2)).isoformat(),
        contract=CONTRACT,contract_sha256=CONTRACT_SHA256,scope_sha256=scope,observations_attempted=attempted,scored=scored,
        pending=pending,prepared_not_confirmed=unconfirmed,total_retained_scores=total,withheld=withheld,cohorts=_summarize(scores),
        report_window_days=28,summarized_rows=len(scores),summary_truncated=len(rows)>10000,database=capacity,
        local_coverage_qualified=False,automatic_actuation=False,release_authorized=False)
    report['report_sha256']=identity(report)
    if len(canonical(report))>MAX_BYTES:raise ValueError('bounded capability verification report required')
    if apply:queue.state._write(queue.state.root/'capability-performance.json',report)
    return report
