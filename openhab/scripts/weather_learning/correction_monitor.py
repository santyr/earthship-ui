"""Bounded original wind/proxy diagnostics inside the existing monitor owner.

The caller supplies the shared deadline and remaining observation budget. This
module neither fits models nor promotes sensor, physical or actuator authority.
"""
from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json,os,shutil,sqlite3,stat
from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc
from weather_radiation_history import RadiationHistoryUnavailable
from .correction_performance import procedure,policy_reports,summarize

VERSION='earthship-issued-correction-evaluation/v2'
CONTRACT=dict(version=VERSION,interval='complete_future_hour',population=dict(wind_m_s='every_retained_wind_issue',
    irradiance_w_m2='first_indexed_verified_conditioned_delivery_per_site_date'),maturity_seconds=120,
    arrival_allowance_days=7,weighting='equal_local_target_dates_equal_targets_equal_original_forecasts',qualification='diagnostic_only')
CONTRACT_SHA256=identity(CONTRACT)
FIELDS={'schema','kind','issued_at','completed_at','timezone','source_sha256','model_sha256','policy_sha256','producer_sha256','evidence','targets','automatic_actuation','issue_sha256'}


def validate_issue(value):
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!='earthship-issued-correction/v1' or
        value['kind'] not in CONTRACT['population'] or value['automatic_actuation'] is not False or
        value['issue_sha256']!=identity({k:v for k,v in value.items() if k!='issue_sha256'}) or len(canonical(value))>4*1024**2):
        raise ValueError('bounded original correction issue required')
    for key in ('source_sha256','model_sha256','policy_sha256','producer_sha256'):digest(value[key])
    issued,completed=map(instant,(value['issued_at'],value['completed_at']));ZoneInfo(value['timezone'])
    if not issued<=completed<issued+timedelta(minutes=2):raise ValueError('causal original completion required')
    rows=value['targets']
    if not isinstance(rows,list) or not 1<=len(rows)<=336:raise ValueError('bounded original correction targets required')
    times=[]
    for row in rows:
        if set(row)!={'start','end','raw','corrected','regime'}:raise ValueError('closed original correction target required')
        start,end=map(instant,(row['start'],row['end']));times.append(start)
        if not completed<=start<end or end-start!=timedelta(hours=1) or start.minute or start.second or start.microsecond or end>issued+timedelta(hours=360):raise ValueError('causal complete future correction interval required')
        if row['regime'] not in ('all','daylight','night'):raise ValueError('declared correction regime required')
        for key in ('raw','corrected'):
            if row[key] is not None and (not finite(row[key]) or row[key]<0):raise ValueError('nonnegative original prediction required')
        if row['corrected'] is not None and row['raw'] is None:raise ValueError('correction requires matched raw target')
    if times!=sorted(set(times)):raise ValueError('unique ordered correction targets required')
    procedure(value)
    return value


class CorrectionStore:
    """Immutable originals and score/state commit share one durable transaction."""
    def __init__(self,state,*,timeout=2):
        self.timeout=timeout
        self.root=Path(state.root);self.db=self.root/'correction-monitor.sqlite3'
        from .shadow import _directory
        _directory(self.root)
        fd=os.open(self.db,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('private owned correction index required')
        finally:os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS originals (sequence INTEGER PRIMARY KEY, name TEXT UNIQUE, kind TEXT, issued TEXT, completed TEXT, day TEXT, value TEXT, UNIQUE(kind,issued))')
            db.execute('CREATE TABLE IF NOT EXISTS work (key TEXT PRIMARY KEY, scope TEXT, issue TEXT, target TEXT, state TEXT, retry TEXT, expires TEXT, reason TEXT, score TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS correction_due ON work(scope,state,retry)')
            db.execute('CREATE TABLE IF NOT EXISTS cursors (source TEXT PRIMARY KEY,value TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS objects (name TEXT PRIMARY KEY,value TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS intake_failures (scope TEXT,name TEXT,sequence INTEGER,retry TEXT,reason TEXT,PRIMARY KEY(scope,name))')

    @contextmanager
    def connect(self):
        if shutil.disk_usage(self.root).free<32*1024**2:raise ValueError('correction disk headroom exhausted')
        db=sqlite3.connect(self.db,timeout=getattr(self,'timeout',2))
        try:
            db.execute('PRAGMA cache_size=-2048');db.execute('PRAGMA max_page_count=32768');db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        finally:db.close()

    def retain_object(self,value):
        raw=canonical(value);name=identity(value)
        if len(raw)>4*1024**2:raise ValueError('bounded frozen correction object required')
        with self.connect() as db:
            previous=db.execute('SELECT value FROM objects WHERE name=?',(name,)).fetchone()
            if previous is not None and previous!=(raw.decode(),):raise ValueError('immutable correction object differs')
            db.execute('INSERT OR IGNORE INTO objects VALUES(?,?)',(name,raw.decode()))
        return name

    def read_object(self,name):
        with self.connect() as db:row=db.execute('SELECT value FROM objects WHERE name=?',(digest(name),)).fetchone()
        if row is None:raise FileNotFoundError('original correction object missing')
        value=json.loads(row[0])
        if identity(value)!=name:raise ValueError('original correction object changed')
        return value

    def retain(self,original):
        value=validate_issue(original);raw=canonical(value).decode();day=instant(value['issued_at']).astimezone(ZoneInfo(value['timezone'])).date().isoformat()
        with self.connect() as db:
            old=db.execute('SELECT name,value FROM originals WHERE kind=? AND issued=?',(value['kind'],value['issued_at'])).fetchone()
            if old:
                if old!=(value['issue_sha256'],raw):raise ValueError('conflicting immutable correction decision')
                return value['issue_sha256']
            if db.execute('SELECT COUNT(*) FROM originals').fetchone()[0]>=10000:raise ValueError('correction original capacity exhausted')
            db.execute('INSERT INTO originals(name,kind,issued,completed,day,value) VALUES(?,?,?,?,?,?)',
                (value['issue_sha256'],value['kind'],value['issued_at'],value['completed_at'],day,raw))
        return value['issue_sha256']

    def read_issue(self,name):
        with self.connect() as db:row=db.execute('SELECT value FROM originals WHERE name=?',(digest(name),)).fetchone()
        if row is None:raise FileNotFoundError('original correction missing')
        value=validate_issue(json.loads(row[0]))
        if value['issue_sha256']!=name:raise ValueError('original correction identity differs')
        for key in ('model_object_sha256','selection_object_sha256','producer_object_sha256'):
            if key in value['evidence']:self.read_object(value['evidence'][key])
        return value

    def prepare(self,scope,now,guard):
        # Failed originals retain a separate retry cursor. Reserve at least half
        # each bounded intake batch for newer rows so corrupt evidence cannot
        # indefinitely block independent originals.
        with self.connect() as db:
            cursor=db.execute('SELECT value FROM cursors WHERE source=?',('intake:'+scope,)).fetchone();after=int(cursor[0]) if cursor else 0
            retry=db.execute('SELECT o.sequence,o.name,o.kind,o.day FROM intake_failures f JOIN originals o ON o.name=f.name WHERE f.scope=? AND f.retry<=? ORDER BY f.retry,f.sequence LIMIT 8',(scope,now.isoformat())).fetchall()
            rows=retry+db.execute('SELECT sequence,name,kind,day FROM originals WHERE sequence>? ORDER BY sequence LIMIT ?',(after,16-len(retry))).fetchall()
        for seq,name,kind,day in rows:
            guard()
            try:original=self.read_issue(name)
            except (OSError,ValueError,KeyError,TypeError) as error:
                guard()
                with self.connect() as db:
                    db.execute('INSERT OR REPLACE INTO intake_failures VALUES(?,?,?,?,?)',(scope,name,seq,(now+timedelta(hours=1)).isoformat(),type(error).__name__))
                    if seq>after:
                        after=seq;db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)',('intake:'+scope,str(after)))
                continue
            if instant(original['completed_at'])>now:
                with self.connect() as db:
                    db.execute('INSERT OR REPLACE INTO intake_failures VALUES(?,?,?,?,?)',(scope,name,seq,original['completed_at'],'original_not_yet_available'))
                    if seq>after:
                        after=seq;db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)',('intake:'+scope,str(after)))
                continue
            with self.connect() as db:
                first=db.execute('SELECT name FROM originals WHERE kind=? AND day=? ORDER BY sequence LIMIT 1',(kind,day)).fetchone()[0]
                if kind!='irradiance_w_m2' or first==name:
                    for row in original['targets']:
                        target=instant(row['end']);key=identity(dict(scope=scope,issue=name,start=row['start'],end=row['end']))
                        db.execute('INSERT OR IGNORE INTO work VALUES(?,?,?,?,?,?,?,?,?)',(key,scope,name,row['end'],'pending',(target+timedelta(minutes=2)).isoformat(),(target+timedelta(days=7)).isoformat(),None,None))
                db.execute('DELETE FROM intake_failures WHERE scope=? AND name=?',(scope,name))
                if seq>after:
                    after=seq;db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)',('intake:'+scope,str(after)))


def retain_wind_issue(state,value,*,model,selection,snapshot):
    """Commit issued hours, selected artifact and producing bytes before pointer."""
    from .weather_response import validate_model
    from . import historical_serving
    validate_model(model)
    issue=instant(value['issued_at'])
    if snapshot['historical'] is not False or not instant(snapshot['ingestion_completed_at'])<=issue:raise ValueError('original available operational wind source required')
    sources={}
    for module in (historical_serving,__import__(__name__,fromlist=['']),__import__('weather_learning.weather_response',fromlist=['']),__import__('weather_learning.contracts',fromlist=['']),__import__('weather_learning.weights',fromlist=[''])):
        path=Path(module.__file__);raw=path.read_bytes()
        if len(raw)>262144:raise ValueError('bounded wind producer required')
        sources[path.name]=dict(sha256=sha256(raw).hexdigest(),utf8=raw.decode())
    store=CorrectionStore(state)
    from weather_source_files import _read as original_bytes
    raw_model=original_bytes(Path(selection['model_path']),4*1024**2)
    if sha256(raw_model).hexdigest()!=selection['model_file_sha256'] or json.loads(raw_model)!=model:raise ValueError('original wind model bytes changed')
    model_ref=store.retain_object(dict(file_sha256=selection['model_file_sha256'],utf8=raw_model.decode()))
    selection_ref=store.retain_object(selection);producer_ref=store.retain_object(sources)
    body=dict(schema='earthship-issued-correction/v1',kind='wind_m_s',issued_at=value['issued_at'],completed_at=value['generated_at'],timezone=snapshot['site']['timezone'],
        source_sha256=value['source_snapshot_sha256'],model_sha256=model['model_sha256'],policy_sha256=selection['selection_sha256'],producer_sha256=identity(sources),
        evidence=dict(public_view=value,model_object_sha256=model_ref,selection_object_sha256=selection_ref,producer_object_sha256=producer_ref,source_available_at=snapshot['ingestion_completed_at'],
            measurement_target='hour_mean_local_station_wind_m_s',measurement_health_qualified=False),
        targets=[dict(start=r['start'],end=r['end'],raw=r['raw_m_s'],corrected=r['local_m_s'],regime='all') for r in value['hours']],automatic_actuation=False)
    cells=sorted({(p['latitude'],p['longitude']) for p in snapshot.get('points',[]) if p['variable']=='wind_speed_10m'})
    body['evidence']['procedure']=dict(schema='earthship-correction-procedure/v1',
        method_policy_sha256=identity(dict(rule='original_multiplicative_site_gain',target=value['target'],baseline=value['baseline'],model_schema=model['schema'],
            numerical_sources={name:row['sha256'] for name,row in sources.items() if name in ('weather_response.py','contracts.py','weights.py')})),
        training_policy_sha256=None,selection_policy_sha256=identity(dict(rule='explicit_original_improved_historical_gain',maximum_model_age_days=14,
            original_runtime_bound=True,fallback='unavailable_without_selected_original')),
        source_grid_sha256=None if not cells else identity(dict(provider='weathernext3',site=snapshot['site'],cells=cells,variable='wind_speed_10m',period_seconds=0)))
    body['issue_sha256']=identity(body);return store.retain(body)


def _metrics(errors):
    from math import fsum,sqrt
    return dict(count=len(errors),mae=None if not errors else fsum(abs(e) for e in errors)/len(errors),
        bias=None if not errors else fsum(errors)/len(errors),rmse=None if not errors else sqrt(fsum(e*e for e in errors)/len(errors)))


def monitor_corrections(state,*,now,observation_policy_sha256,read_wind,read_solar,limit,apply=False,guard=lambda:None,discover=None,clock=None):
    """Consume at most the caller's remaining GLOBAL observation budget.

    Reader returns a retained-outcome capsule with complete interval identity,
    original receipts and source clocks; None means missing, never zero.
    Preview uses a SQLite backup and never changes originals/cursors/scores.
    """
    import tempfile
    now=utc(now);digest(observation_policy_sha256)
    if type(limit) is not int or not 0<=limit<=64 or type(apply) is not bool:raise ValueError('bounded shared correction budget required')
    if not apply:
        with tempfile.TemporaryDirectory(prefix='correction-preview-') as folder:
            preview=type('Preview',(),{'root':Path(folder)})();temporary=CorrectionStore(preview)
            source_path=Path(state.root)/'correction-monitor.sqlite3'
            if source_path.exists():
                source=CorrectionStore(state)
                with source.connect() as a,temporary.connect() as b:a.backup(b)
            return monitor_corrections(preview,now=now,observation_policy_sha256=observation_policy_sha256,read_wind=read_wind,
                read_solar=read_solar,limit=limit,apply=True,guard=guard,discover=discover,clock=clock)
    store=CorrectionStore(state);dependencies=[]
    if discover is not None:
        with store.connect() as db:cursor=db.execute('SELECT value FROM cursors WHERE source=?',('native-delivery',)).fetchone()
        cursor=None if cursor is None else json.loads(cursor[0])
        try:
            page,next_cursor=discover(cursor,limit=16,guard=guard,store=store)
            if len(page)>16:raise ValueError('bounded correction discovery required')
            for original in page:guard();store.retain(original)
            with store.connect() as db:db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)',('native-delivery',canonical(next_cursor).decode()))
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
            guard();dependencies.append(dict(component='native_discovery',reason=type(error).__name__))
    scope=identity(dict(contract=CONTRACT_SHA256,observation_policy_sha256=observation_policy_sha256));store.prepare(scope,now,guard)
    # Reserve a quarter of available work for proxy targets. Unused shares
    # may be borrowed, but combined reader calls never exceed this job budget.
    proxy_share=0 if limit<2 else max(1,limit//4);shares={'wind_m_s':limit-proxy_share,'irradiance_w_m2':proxy_share}
    due=[]
    with store.connect() as db:
        for kind,share in shares.items():
            due.extend(db.execute("SELECT w.key,w.issue,w.target,w.expires FROM work w JOIN originals o ON o.name=w.issue WHERE w.scope=? AND w.state='pending' AND w.retry<=? AND o.kind=? ORDER BY w.retry,w.target,w.key LIMIT ?",(scope,now.isoformat(),kind,share)).fetchall())
        if len(due)<limit:
            candidates=db.execute("SELECT key,issue,target,expires FROM work WHERE scope=? AND state='pending' AND retry<=? ORDER BY retry,target,key LIMIT ?",(scope,now.isoformat(),limit)).fetchall()
            keys={r[0] for r in due}
            due.extend(r for r in candidates if r[0] not in keys)
            due=due[:limit]
    attempted=0;attempted_by_kind={kind:0 for kind in shares}
    for key,name,target,expires in due:
        guard()
        try:
            original=store.read_issue(name);row=next(r for r in original['targets'] if r['end']==target)
        except (OSError,ValueError,KeyError,TypeError,StopIteration) as error:
            guard()
            with store.connect() as db:
                db.execute("UPDATE work SET state=?,retry=?,reason=? WHERE key=? AND state='pending'",('expired' if now>=instant(expires) else 'pending',(now+timedelta(hours=1)).isoformat(),'original_dependency_'+type(error).__name__,key))
            continue
        work=dict(row,kind=original['kind'],issue_sha256=name);reason=None;score=None
        if row['raw'] is None:reason='original_forecast_missing'
        else:
            attempted+=1;attempted_by_kind[original['kind']]+=1
            try:
                label=(read_wind if original['kind']=='wind_m_s' else read_solar)(work,now);guard()
                assessed=now if clock is None else utc(clock())
                if not now<=assessed<=now+timedelta(seconds=90):raise ValueError('bounded actual observation assessment clock required')
                if label is None:reason='observation_missing'
                elif not instant(row['end'])<=instant(label['available_at'])<=instant(expires):reason='observation_arrival_outside_allowance'
                elif (label['start']!=row['start'] or label['end']!=row['end'] or not instant(row['end'])<=instant(label['assessed_at'])<=assessed or instant(label['available_at'])>instant(label['assessed_at']) or
                      not finite(label['value']) or label['value']<0 or not isinstance(label['original'],dict)):reason='quality_withheld'
                else:
                    digest(label['source_sha256'])
                    if original['kind']=='irradiance_w_m2' and label['measurement_health_qualified'] is not True:reason='quality_withheld'
                    else:
                        score=dict(evaluation_key=key,evaluation_version=VERSION,evaluation_contract_sha256=CONTRACT_SHA256,issue_sha256=name,
                            kind=original['kind'],issued_at=original['issued_at'],procedure=procedure(original),start=row['start'],end=row['end'],raw=row['raw'],candidate=row['corrected'],outcome=label,
                            source_sha256=original['source_sha256'],model_sha256=original['model_sha256'],policy_sha256=original['policy_sha256'],producer_sha256=original['producer_sha256'],
                            observation_policy_sha256=observation_policy_sha256,timezone=original['timezone'],regime=row['regime'],automatic_actuation=False)
                        score['score_sha256']=identity(score)
                        if len(canonical(score))>4*1024**2:raise ValueError('bounded original correction outcome required')
            except (ValueError,KeyError,TypeError,OSError,RadiationHistoryUnavailable) as error:
                guard();reason=type(error).__name__
        with store.connect() as db:
            if score is not None:db.execute("UPDATE work SET score=?,state='completed',reason=NULL WHERE key=? AND state='pending'",(canonical(score).decode(),key))
            else:db.execute("UPDATE work SET state=?,retry=?,reason=? WHERE key=? AND state='pending'",('unrecoverable_original' if reason=='original_forecast_missing' else 'expired' if now>=instant(expires) else 'pending',(now+timedelta(hours=1)).isoformat(),reason,key))
    # Output stays bounded; totals remain durable even when detail is capped.
    with store.connect() as db:
        from .pending_scores import backlog_summary
        backlog=backlog_summary(db,scope,now);backlog['target_clock']='interval_end'
        states=dict(db.execute('SELECT state,COUNT(*) FROM work WHERE scope=? GROUP BY state',(scope,)))
        intake_dependencies=dict(db.execute('SELECT reason,COUNT(*) FROM intake_failures WHERE scope=? GROUP BY reason',(scope,)))
        # Pending work without an assessment has no withholding reason yet.
        # Its population remains counted in states and the known-work backlog.
        reasons=dict(db.execute("SELECT reason,COUNT(*) FROM work WHERE scope=? AND state!='completed' AND reason IS NOT NULL GROUP BY reason",(scope,)))
        total_scores=db.execute("SELECT COUNT(*) FROM work WHERE scope=? AND state='completed' AND target>=? AND target<=?",(scope,(now-timedelta(days=7)).isoformat(),now.isoformat())).fetchone()[0]
        native_dependencies=[]
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='native_replay'").fetchone():native_dependencies=[dict(reason=reason,count=count) for reason,count in db.execute("SELECT r.reason,COUNT(*) FROM native_replay r JOIN native_refs n ON n.name=r.name LEFT JOIN originals o ON o.issued=n.issued AND o.kind='irradiance_w_m2' WHERE r.state='dependency' AND o.name IS NULL GROUP BY r.reason")]
        scores=[json.loads(r[0]) for r in db.execute("SELECT score FROM work WHERE scope=? AND state='completed' AND target>=? AND target<=? ORDER BY target DESC LIMIT 2048",(scope,(now-timedelta(days=7)).isoformat(),now.isoformat()))]
    valid_scores=[];score_dependencies={}
    for score in scores:
        if (not isinstance(score,dict) or score.get('evaluation_version')!=VERSION or
                score.get('evaluation_contract_sha256')!=CONTRACT_SHA256 or
                score.get('score_sha256')!=identity({k:v for k,v in score.items() if k!='score_sha256'})):
            score_dependencies['invalid_score_identity']=score_dependencies.get('invalid_score_identity',0)+1
        else:valid_scores.append(score)
    scores=valid_scores
    cohorts={}
    for score in scores:
        cohort=(score['kind'],score['source_sha256'],score['model_sha256'],score['policy_sha256'],score['producer_sha256'],score['regime'])
        cohorts.setdefault(cohort,[]).append(score)
    reports=[]
    for cohort,rows in sorted(cohorts.items()):
        reports.append(dict(kind=cohort[0],source_sha256=cohort[1],model_sha256=cohort[2],policy_sha256=cohort[3],producer_sha256=cohort[4],regime=cohort[5],scope='artifact_source_snapshot_selection_and_producer',
            **summarize(rows),measurement_health_qualified=cohort[0]!='wind_m_s'))
    generated=now if clock is None else utc(clock())
    if not now<=generated<=now+timedelta(seconds=90):raise ValueError('bounded correction report completion clock required')
    report=dict(schema='earthship-correction-performance/v2',generated_at=generated.isoformat(),evaluation_version=VERSION,evaluation_contract_sha256=CONTRACT_SHA256,
        observations_attempted=attempted,observations_attempted_by_kind=attempted_by_kind,observation_budget=limit,reserved_kind_shares=shares,states=states,known_work_backlog=backlog,intake_dependencies=intake_dependencies,withheld_reasons=reasons,score_dependencies=score_dependencies,cohorts=reports,policy_cohorts=policy_reports(scores),calibration_qualified=False,sampling=CONTRACT['population'],
        historical_gaps=['wind_issues_overwritten_before_immutable_retention'],dependencies=dependencies,native_original_dependencies=native_dependencies,native_discovery=getattr(discover,'last_status',None),report_target_window_days=7,report_score_limit=2048,report_total_scored_pairs=total_scores,report_scores_truncated=total_scores>len(scores),
        physical_calibration_qualified=False,distribution_calibration_qualified=False,release_authorized=False,automatic_actuation=False)
    report['projection_coverage']=dict(artifact_cohorts_total=len(report['cohorts']),procedure_cohorts_total=len(report['policy_cohorts']),
        artifact_cohorts_omitted=0,procedure_cohorts_omitted=0,maximum_bytes=64*1024,original_score_records='retained_in_private_durable_index')
    while len(canonical(report))>64*1024-128:
        if report['cohorts']:
            report['cohorts'].pop();report['projection_coverage']['artifact_cohorts_omitted']+=1
        elif report['policy_cohorts']:
            report['policy_cohorts'].pop();report['projection_coverage']['procedure_cohorts_omitted']+=1
        else:raise ValueError('bounded correction diagnostic summary required')
    report['report_sha256']=identity(report);return report


def native_delivery_paths(root,*,now,guard):
    """Only ten declared UTC directories, never a recursive archive walk."""
    from .shadow import _directory
    root=Path(root);_directory(root);paths=[]
    for offset in range(10):
        guard();folder=root/('origins-'+(utc(now)-timedelta(days=offset)).strftime('%Y%m%d'))
        if not folder.exists():continue
        _directory(folder)
        for path in folder.glob('*.native-provisional-delivery-v2.json'):
            if len(paths)>=4096:raise ValueError('bounded native reference inventory required')
            paths.append(path)
    return sorted(paths)


def retain_native_delivery_reference(state,path,*,indexed_at,timezone_name='America/Denver',origin='publisher_indexed'):
    """Retain one lightweight delivery reference; never replay in a publisher."""
    from .shadow import _read
    if origin not in ('publisher_indexed','historical_header_bootstrap'):raise ValueError('declared native index availability required')
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved native delivery required')
    body=_read(path,65536);pin=digest(body['delivery_sha256'])
    if body.get('schema')!='earthship-provisional-thermal-delivery/v2' or pin!=identity({k:v for k,v in body.items() if k!='delivery_sha256'}) or path.name!=pin+'.native-provisional-delivery-v2.json':raise ValueError('unchanged original delivery required')
    capture=Path(body['capture_path'])
    suffixes={'.native-provisional-origin-v2.json':('earthship-provisional-thermal-origin/v2','earthship-provisional-thermal-origin/v3'),
        '.native-provisional-origin-v4.json':('earthship-provisional-thermal-origin/v4',),
        '.native-provisional-origin-v5.json':('earthship-provisional-thermal-origin/v5',)}
    versions=next((versions for suffix,versions in suffixes.items() if capture.name==digest(body['capture_sha256'])+suffix),None)
    if capture.parent!=path.parent or versions is None:raise ValueError('original capture must remain with delivery')
    if origin=='historical_header_bootstrap':
        original=_read(capture,6*1024**2)
        if original.get('capture_sha256')!=body['capture_sha256'] or identity({k:v for k,v in original.items() if k!='capture_sha256'})!=body['capture_sha256']:
            raise ValueError('historical capture hash differs from delivery')
        if original.get('schema') not in versions:raise ValueError('historical capture version and suffix differ')
        # Old raw-only native packages are real delivered forecasts, but are
        # outside this correction population and cannot consume its daily slot.
        if original.get('schema') not in ('earthship-provisional-thermal-origin/v3','earthship-provisional-thermal-origin/v5'):return None
    issued=instant(body['issued_at']);indexed=utc(indexed_at)
    if indexed<issued:raise ValueError('native reference unavailable before original issue')
    day=issued.astimezone(ZoneInfo(timezone_name)).date().isoformat();store=state if isinstance(state,CorrectionStore) else CorrectionStore(state)
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS native_refs (sequence INTEGER PRIMARY KEY,name TEXT UNIQUE,path TEXT,issued TEXT,day TEXT,indexed TEXT,origin TEXT,header TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS native_daily (day TEXT PRIMARY KEY,name TEXT)')
        previous=db.execute('SELECT path,header FROM native_refs WHERE name=?',(pin,)).fetchone();raw=canonical(body).decode()
        if previous is not None:
            if previous!=(str(path),raw):raise ValueError('immutable native delivery reference differs')
            return pin
        if db.execute('SELECT COUNT(*) FROM native_refs').fetchone()[0]>=10000:raise ValueError('native reference capacity exhausted')
        db.execute('INSERT INTO native_refs(name,path,issued,day,indexed,origin,header) VALUES(?,?,?,?,?,?,?)',(pin,str(path),issued.isoformat(),day,indexed.isoformat(),origin,raw))
        db.execute('INSERT OR IGNORE INTO native_daily VALUES(?,?)',(day,pin))
    return pin


# This fixed outside-model program imports numerical modules only AFTER its
# explicitly supplied stage source closure is checked. It never imports a
# model path found inside an untrusted capture and never fits or publishes.
_NATIVE_REPLAY_CHILD=r'''
import hashlib,json,os,pathlib,stat,sys,time
request=json.loads(pathlib.Path(sys.argv[1]).read_text());stage=pathlib.Path(request['stage']);root=stage/'sources';deadline=request['deadline']
def guard():
 if time.monotonic()>=deadline:raise TimeoutError('correction original-producer deadline elapsed')
def verify():
 guard()
 for name,pin in request['source_manifest'].items():
  guard();p=root/name;s=p.lstat()
  if p.resolve()!=p or not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_mode&0o022 or s.st_size>2*1024**2 or hashlib.sha256(p.read_bytes()).hexdigest()!=pin:raise ValueError('original producer source changed')
verify();sys.path.insert(0,str(root/'openhab/scripts'))
from household_cycle import load_cycle_delivery
from native_model_serving_receipt import load_serving_selection,read_serving_model
from household.codec import canonical,identity
from household.control_contracts import instant
from thermal_model.installed_shade_origin import _forecast_forcing,_origin_actions
selection=load_serving_selection(stage,expected_deployment_sha256=request['deployment_sha256'],assessed_at=instant(request['header']['issued_at']),guard=guard)
model=read_serving_model(selection,assessed_at=instant(request['header']['issued_at']),guard=guard)
header=request['header'];issue=instant(header['issued_at']);path=request['delivery_path']
archive=load_cycle_delivery(dict(status='published',delivery_verified=True,origin_path=header['capture_path'],delivery_path=path),issue=issue,guard=guard,
 expected_artifact_sha256=header['artifact_sha256'],expected_capture_sha256=header['capture_sha256'],serving_model=model)
capture=archive['capture'];context=capture.get('weather_conditioning')
if context is None:raise ValueError('delivered native issue has no conditioning')
from household.thermal_weather_conditioning import apply_conditioning
if pathlib.Path(apply_conditioning.__code__.co_filename).resolve()!=root/'openhab/scripts/household/thermal_weather_conditioning.py':raise ValueError('conditioning bound to another producer')
from thermal_model.installed_shade_published_origin import _receipt
available=instant(capture['inputs_available_at']);published=max(_receipt(receipt,item)[1] for item,receipt in header['receipts'].items());inputs=capture['inputs']
actions=_origin_actions(inputs['action_snapshot'],issue,allow_removed=capture['candidate']['fit']['model_rule'] in ('earthship-native-joint-shade-dynamics/v3','earthship-native-irradiance-shade-dynamics/v4'))
raw=_forecast_forcing(inputs['forecast'],issue,available,actions);initial=capture['output']['initial']['outdoor_f']
corrected=apply_conditioning(raw,context,issue=issue,available=available,initial_outdoor_f=initial)
from datetime import timedelta
positions={p['at']:p for p in context['midpoint_positions']};hours=[]
for row in context['rows']:
 end=instant(row['at']);start=end-timedelta(hours=1)
 if start<published:continue
 # A complete interior five-minute step has exactly this ending-hour mean
 # in both preserved endpoint and corrected interval numerical producers.
 interior=[r.radiation_wm2 for r in corrected if start<=r.at-timedelta(minutes=5) and r.at<=end]
 if not interior or max(interior)-min(interior)>1e-8:raise ValueError('original conditioned hour cannot be recovered exactly')
 p=positions[(end-timedelta(minutes=30)).isoformat()]
 hours.append(dict(start=start.isoformat(),end=end.isoformat(),raw=row['radiationWm2'],corrected=interior[0],regime='daylight' if p['elevation_degrees']>0 else 'night'))
archive['verify_unchanged']();verify()
value=dict(hours=hours,issued_at=capture['issued_at'],completed_at=published.isoformat(),timezone=context['timezone'],
 source_sha256=context['forecast_sha256'],model_sha256=context['admission']['models']['irradiance_w_m2']['model_sha256'],
 policy_sha256=context['selection']['selection_sha256'],producer_sha256=identity(request['source_manifest']),
 evidence=dict(capture_sha256=capture['capture_sha256'],capture_path=header['capture_path'],delivery_sha256=header['delivery_sha256'],delivery_path=path,
 artifact_sha256=header['artifact_sha256'],runtime_sha256=header['runtime_sha256'],conditioning=context,initial_outdoor_f=initial,
 deployment_sha256=request['deployment_sha256'],source_manifest=request['source_manifest'],selection_population='first_indexed_verified_delivery_per_site_date'))
encoded=canonical(value)
if len(encoded)>256*1024:raise ValueError('bounded replayed correction required')
fd=os.open(sys.argv[2],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(encoded)
'''


class NativeCorrectionDiscovery:
    """Bounded header bootstrap plus explicitly pinned original-stage replay.

    Sampling commits the first indexed delivery before observing outcomes; it
    does not claim the earliest delivery among every historical archive file.
    """
    def __init__(self,state,*,stage,deployment_sha256,now,deadline):
        self.state=state;self.stage=Path(stage);self.pin=digest(deployment_sha256);self.now=utc(now);self.deadline=deadline

    def __call__(self,cursor,*,limit=16,guard=lambda:None,store=None):
        import tempfile,subprocess,time
        import household_cycle_deploy as deploy
        from household_forecast_score import read_score_dispatch
        from .shadow import _read
        if type(limit) is not int or not 1<=limit<=16:raise ValueError('bounded native header page required')
        guard();record=deploy.verify_stage(self.stage,expected_deployment_sha256=self.pin)
        dispatch=read_score_dispatch(self.stage,deployment_sha256=self.pin,guard=guard)
        selections=[dict(stage=str(self.stage),deployment_sha256=self.pin)]+dispatch['historical'];stages=[];roots=set()
        for selection in selections:
            guard();stage=Path(selection['stage']);verified=deploy.verify_stage(stage,expected_deployment_sha256=selection['deployment_sha256'])
            cycle=json.loads(deploy._bytes(stage/'cycle.json',private=True,maximum=8192));config=json.loads(deploy._bytes(cycle['forecast_config'],private=True,maximum=8192))
            roots.add(config['evidence_directory']);stages.append((selection,verified,config))
        store=CorrectionStore(self.state) if store is None else store
        inventory=sorted({path for root in roots for path in native_delivery_paths(root,now=self.now,guard=guard)})
        if len(inventory)>4096:raise ValueError('bounded aggregate native delivery inventory required')
        after='' if cursor is None else cursor['after'];publisher_cursors={} if cursor is None else dict(cursor.get('publishers',{}))
        admitted=0
        for root in sorted(roots):
            guard();published=_publisher_references(Path(root),after=publisher_cursors.get(root),limit=limit-admitted)
            for sequence,path,indexed,source_id,anchor in published:
                retain_native_delivery_reference(store,path,indexed_at=instant(indexed),origin='publisher_indexed')
                publisher_cursors[root]=dict(sequence=sequence,source=source_id,anchor=anchor);admitted+=1
        page=[p for p in inventory if str(p)>after][:limit-admitted]
        not_conditioned=0
        for path in page:
            guard()
            if retain_native_delivery_reference(store,path,indexed_at=self.now,origin='historical_header_bootstrap') is None:not_conditioned+=1
        self.last_status=dict(inventory_files=len(inventory),publisher_references=admitted,historical_headers_examined=len(page),raw_only_excluded=not_conditioned,
            header_backlog=sum(str(p)>(str(page[-1]) if page else after) for p in inventory),selection='first_indexed_verified_conditioned_delivery_per_site_date')
        # Empty bootstrap still services publisher-indexed references.
        with store.connect() as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='native_refs'").fetchone()
            db.execute('CREATE TABLE IF NOT EXISTS native_replay (name TEXT PRIMARY KEY,state TEXT,retry TEXT,reason TEXT)')
            refs=[] if not exists else db.execute('SELECT n.name,n.path,n.header,n.origin,n.indexed FROM native_refs n JOIN native_daily d ON d.name=n.name LEFT JOIN originals o ON o.issued=n.issued AND o.kind=? LEFT JOIN native_replay r ON r.name=n.name WHERE o.name IS NULL AND (r.retry IS NULL OR r.retry<=?) ORDER BY n.sequence LIMIT 1',('irradiance_w_m2',self.now.isoformat())).fetchall()
        receipts=[]
        for pin,path,raw,origin,indexed in refs:
            guard();header=json.loads(raw)
            association_path=Path(header['capture_path']).parent/(header['capture_sha256']+'.native-serving-model-binding-v1.json')
            try:
                association=_read(association_path,8192)
                if (association.get('schema')!='earthship-native-serving-model-binding/v1' or association.get('automatic_actuation') is not False or
                    association.get('binding_sha256')!=identity({k:v for k,v in association.items() if k!='binding_sha256'}) or
                    any(association.get(k)!=header[k] for k in ('capture_sha256','artifact_sha256','runtime_sha256','issued_at'))):raise ValueError('original native serving association differs')
            except (OSError,ValueError,KeyError,TypeError):
                with store.connect() as db:db.execute('INSERT OR REPLACE INTO native_replay VALUES(?,?,?,?)',(pin,'dependency',(self.now+timedelta(hours=1)).isoformat(),'original_serving_association_unavailable'))
                continue
            matches=[v for v in stages if str(v[0]['stage'])==association['stage'] and v[0]['deployment_sha256']==association['deployment_sha256'] and v[2]['runtime_sha256']==header['runtime_sha256'] and v[2]['artifact_sha256']==header['artifact_sha256']]
            if not matches:
                with store.connect() as db:db.execute('INSERT OR REPLACE INTO native_replay VALUES(?,?,?,?)',(pin,'dependency',(self.now+timedelta(hours=1)).isoformat(),'matching_original_producer_unavailable'))
                continue
            selection,verified,config=matches[0];stage=Path(selection['stage'])
            if _read(Path(path),65536)!=header:raise ValueError('indexed native delivery changed')
            with tempfile.TemporaryDirectory(prefix='native-correction-',dir=store.root) as temporary:
                request=Path(temporary)/'request.json';result=Path(temporary)/'result.json'
                body=dict(stage=str(stage),deployment_sha256=selection['deployment_sha256'],source_manifest=verified['source_manifest'],header=header,delivery_path=path,deadline=self.deadline)
                fd=os.open(request,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,'wb') as f:f.write(canonical(body))
                remaining=self.deadline-time.monotonic()
                if remaining<=1:raise TimeoutError('native correction deadline elapsed')
                completed=subprocess.run(['/usr/bin/python3','-P','-c',_NATIVE_REPLAY_CHILD,str(request),str(result)],
                    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','EARTHSHIP_QUALIFICATION_FIT':'0','EARTHSHIP_REMOTE_QUALIFICATION_FIT':'0','PYTHONPATH':str(stage/'sources/openhab/scripts')+':/home/sat/Solar_PV/analytics/src'},
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=remaining)
                guard()
                if completed.returncode:
                    with store.connect() as db:db.execute('INSERT OR REPLACE INTO native_replay VALUES(?,?,?,?)',(pin,'dependency',(self.now+timedelta(hours=1)).isoformat(),'original_replay_unavailable'))
                    continue
                replayed=_read(result,256*1024)
            if deploy.verify_stage(stage,expected_deployment_sha256=selection['deployment_sha256'])!=verified:raise ValueError('native stage changed during correction replay')
            body={k:v for k,v in replayed.items() if k!='hours'}
            body.update(schema='earthship-issued-correction/v1',kind='irradiance_w_m2',targets=replayed['hours'],automatic_actuation=False)
            body['evidence'].update(index_origin=origin,indexed_at=indexed,
                procedure=dict(schema='earthship-correction-procedure/v1',
                    method_policy_sha256=identity(dict(rule='exact_original_conditioned_proxy_replay',kind='irradiance_w_m2',producer_sha256=body['producer_sha256'])),
                    training_policy_sha256=None,selection_policy_sha256=None,source_grid_sha256=None))
            body['issue_sha256']=identity(body);receipts.append(validate_issue(body))
        return receipts,dict(after=str(page[-1]) if page else after,publishers=publisher_cursors)


def index_native_delivery_safely(settings,path,*,indexed_at,guard):
    """Optional diagnostic intake must never invalidate verified delivery."""
    import sys
    try:
        guard();store=CorrectionStore(type('State',(),{'root':Path(settings['evidence_directory'])})(),timeout=.025)
        retain_native_delivery_reference(store,path,indexed_at=indexed_at)
        return True
    except Exception as error:
        print(json.dumps(dict(status='native_correction_reference_unavailable',reason=type(error).__name__,automatic_actuation=False)),file=sys.stderr)
        return False


def wind_outcome(rows,*,start,assessed_at,source_available_at,unit):
    """Existing numeric station target, explicitly without sensor-health proof."""
    from .weather_response import wind_hour
    if unit!='mph':raise ValueError('original station wind mph required')
    start,assessed_at,source_available_at=map(utc,(start,assessed_at,source_available_at));end=start+timedelta(hours=1)
    if not end<=assessed_at or source_available_at>assessed_at:raise ValueError('mature available original wind required')
    original=dict(unit=unit,rows=[[utc(at).isoformat(),value] for at,value in rows])
    result=wind_hour(rows,start=start)
    if result['mean_m_s'] is None:return None
    return dict(start=start.isoformat(),end=end.isoformat(),assessed_at=assessed_at.isoformat(),available_at=source_available_at.isoformat(),
        value=result['mean_m_s'],source_sha256=identity(original),measurement_health_qualified=False,original=original,
        coverage_seconds=result['covered_seconds'],target='hour_mean_local_station_wind_m_s')


def solar_outcome(source,*,start):
    """Use the existing receipt-validated lux proxy, never physical GHI labels."""
    from .solar_shadow import _source
    source=_source(source);start=utc(start);end=start+timedelta(hours=1)
    if not instant(source['start'])<=start<end<=instant(source['end']):raise ValueError('matching native proxy interval required')
    row=next((r for r in source['hourly'] if instant(r['end'])==end),None)
    if row is None:raise ValueError('complete original proxy hour required')
    return dict(start=start.isoformat(),end=end.isoformat(),assessed_at=source['assessed_at'],available_at=source['available_at'],value=row['proxy_wh_m2'],
        source_sha256=source['source_sha256'],measurement_health_qualified=True,original=source,target='ending_hour_local_lux_proxy_w_m2',metrology_calibrated=False)


def _publisher_references(root,*,after,limit):
    """Read the existing publisher index without creating or modifying it."""
    if limit<=0:return []
    path=Path(root)/'correction-monitor.sqlite3'
    if not path.exists():return []
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>128*1024**2:raise ValueError('private bounded publisher reference index required')
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.025)
        try:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='native_refs'").fetchone() is None:return []
            source_id=f'{info.st_dev}:{info.st_ino}';sequence=0
            if after is not None:
                if not isinstance(after,dict) or set(after)!={'sequence','source','anchor'} or type(after['sequence']) is not int or after['sequence']<0:raise ValueError('bounded original reference cursor required')
                anchor=db.execute('SELECT name FROM native_refs WHERE sequence=?',(after['sequence'],)).fetchone()
                if after['source']==source_id and anchor==(after['anchor'],):sequence=after['sequence']
            rows=db.execute('SELECT sequence,path,indexed,name FROM native_refs WHERE sequence>? ORDER BY sequence LIMIT ?',(sequence,limit)).fetchall()
            current=path.lstat()
            if (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('publisher reference index changed while reading')
            return [(seq,ref,indexed,source_id,name) for seq,ref,indexed,name in rows]
        finally:db.close()
    finally:os.close(fd)
