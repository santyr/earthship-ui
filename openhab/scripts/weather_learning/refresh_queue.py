"""Bounded durable all-publication originals and independently scoped scores.

This namespace never consults or rewrites the first-daily-issue selection. Input
originals are fsynced before transactional registration; restart recovery retries
missing dependencies, without rebuilding a prediction from a later forecast.
"""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from household_job_budget import AdmissionDeferred
from pathlib import Path
import json,os,shutil,sqlite3,stat,tempfile
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .features import TemperatureOutcome
from .near_term_correction import replay_near_correction
from .refresh_evaluation import _checked,_freeze
from .refresh_scoring import CONTRACT_SHA256,_producer,compile_refresh_decision,score_refresh_target,summarize_refresh_scores,validate_refresh_score
from .shadow import _directory,_read
from .worker import collector_lock

DATABASE='refresh-scores.sqlite3'
MAX_DATABASE_BYTES=64*1024**2
MAX_ORIGINAL_BYTES=16*1024**2


def _prepared(value):
    _checked(value,'record_sha256');return _freeze({k:v for k,v in value.items() if k!='record_sha256'})


class RefreshQueue:
    def __init__(self,state,*,db_path=None):
        self.state=state;self.originals=state.root/'refresh-issues';_directory(self.originals)
        self.db=state.root/DATABASE if db_path is None else Path(db_path)
        if not self.db.is_absolute() or self.db.parent.resolve()!=self.db.parent or not self.db.is_relative_to(state.root):
            raise ValueError('private refresh database namespace required')
        fd=os.open(self.db,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:
                raise ValueError('private owned refresh index required')
        finally:os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS decisions (key TEXT PRIMARY KEY,digest TEXT NOT NULL,issued TEXT NOT NULL,completed TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS decisions_time ON decisions(issued,key)')
            db.execute('CREATE TABLE IF NOT EXISTS targets (key TEXT PRIMARY KEY,issue TEXT NOT NULL,target TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS targets_time ON targets(target,key)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (scope TEXT,key TEXT,retry TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(scope,key))')
            db.execute('CREATE TABLE IF NOT EXISTS scores (scope TEXT,key TEXT,target TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(scope,key))')
            db.execute('CREATE INDEX IF NOT EXISTS scores_window ON scores(scope,target,key)')
            db.execute('CREATE TABLE IF NOT EXISTS recovery (id INTEGER PRIMARY KEY CHECK(id=1),after_name TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        if shutil.disk_usage(self.state.root).free<32*1024**2:raise ValueError('refresh database disk headroom exhausted')
        db=sqlite3.connect(self.db,timeout=2)
        try:
            db.execute('PRAGMA cache_size=-2048');db.execute('PRAGMA synchronous=FULL')
            size=db.execute('PRAGMA page_size').fetchone()[0]
            maximum=db.execute('PRAGMA max_page_count='+str(MAX_DATABASE_BYTES//size)).fetchone()[0]
            if maximum*size>MAX_DATABASE_BYTES:raise ValueError('refresh database capacity exceeded')
            with db:yield db
        finally:db.close()

    def _wrapper(self,key,*,indexed=True):
        digest(key);value=_read(self.originals/(key+'.json'),MAX_ORIGINAL_BYTES);_checked(value,'wrapper_sha256')
        if (value['schema']!='earthship-retained-refresh-decision/v1' or value['storage_key']!=key
                or value['automatic_actuation'] is not False):raise ValueError('original refresh wrapper differs')
        _checked(value['decision'],'record_sha256')
        if indexed:
            with self.connect() as db:row=db.execute('SELECT digest FROM decisions WHERE key=?',(key,)).fetchone()
            if row!=(value['wrapper_sha256'],):raise ValueError('original refresh index generation differs')
        return value

    def _register(self,value):
        key=value['storage_key'];record=value['decision'];_checked(value,'wrapper_sha256');_checked(record,'record_sha256')
        if record['contract_sha256']!=CONTRACT_SHA256:raise ValueError('original refresh score contract differs')
        with self.connect() as db:
            previous=db.execute('SELECT digest FROM decisions WHERE key=?',(key,)).fetchone()
            if previous is not None and previous!=(value['wrapper_sha256'],):raise ValueError('original refresh index generation differs')
            db.execute('INSERT OR IGNORE INTO decisions VALUES (?,?,?,?)',(key,value['wrapper_sha256'],record['decision_at'],record['publication_completed_at']))
            for row in record['targets']:
                work=identity(dict(issue=key,target=row['target_at'],contract=CONTRACT_SHA256))
                db.execute('INSERT OR IGNORE INTO targets VALUES (?,?,?)',(work,key,row['target_at']))

    def retain(self,attempt,result,*,archive,site,near=None,clock=lambda:datetime.now(timezone.utc)):
        now=utc(clock());key=identity(dict(attempt=attempt['attempt_sha256'],result=result['result_sha256'],contract=CONTRACT_SHA256,producer=_producer()))
        with collector_lock(self.state.root/'refresh.lock'):
            path=self.originals/(key+'.json')
            if path.exists():
                value=self._wrapper(key,indexed=False)
                if value['attempt']!=attempt or value['result']!=result or value['decision']['near']!=(None if near is None else near.to_dict()):
                    raise ValueError('retained original refresh inputs changed')
                self._register(value);return key
            if near is not None:replay_near_correction(near,archive=archive,site=site)
            with self.connect() as db:
                previous=db.execute('SELECT key FROM decisions WHERE issued<? AND completed<=? ORDER BY issued DESC,key LIMIT 1',
                    (attempt['started_at'],attempt['started_at'])).fetchone()
            previous_key=None if previous is None else previous[0]
            prior=None if previous_key is None else _prepared(self._wrapper(previous_key)['decision'])
            record=compile_refresh_decision(attempt,result,archive=archive,site=site,near=near,previous=prior,clock=lambda:now).to_dict()
            value=dict(schema='earthship-retained-refresh-decision/v1',storage_key=key,attempt=attempt,result=result,
                previous_storage_key=previous_key,decision=record,automatic_actuation=False)
            value['wrapper_sha256']=identity(value)
            self.state._write(path,value,immutable=True)
            self._register(value)
        return key

    def recover(self,*,limit=16):
        if type(limit) is not int or not 1<=limit<=16:raise ValueError('bounded refresh recovery required')
        paths=sorted(self.originals.glob('*.json'))
        if len(paths)>10000:raise ValueError('bounded refresh original capacity exceeded')
        with self.connect() as db:row=db.execute('SELECT after_name FROM recovery WHERE id=1').fetchone()
        after='' if row is None else row[0];selected=[p for p in paths if p.name>after][:limit]
        if not selected:selected=paths[:limit]
        recovered=invalid=0
        for path in selected:
            try:
                value=self._wrapper(path.stem,indexed=False)
                with self.connect() as db:existed=db.execute('SELECT 1 FROM decisions WHERE key=?',(path.stem,)).fetchone()
                self._register(value);recovered+=existed is None
            except (OSError,ValueError,KeyError,TypeError):invalid+=1
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO recovery VALUES(1,?)',('' if not selected else selected[-1].name,))
        return dict(inspected=len(selected),recovered=recovered,invalid=invalid)

    def load(self,key,*,archive,site):
        value=self._wrapper(key);record=value['decision'];near=None
        if record['near'] is not None:
            near=_prepared(record['near']);replay_near_correction(near,archive=archive,site=site)
        previous=value['previous_storage_key']
        prior=None if previous is None else _prepared(self._wrapper(previous)['decision'])
        rebuilt=compile_refresh_decision(value['attempt'],value['result'],archive=archive,site=site,near=near,
            previous=prior,clock=lambda:instant(record['compiled_at'])).to_dict()
        # Keep the original producer identity, while proving every source/value
        # and policy selection through the same versioned replay contract.
        def scientific(v):return {k:x for k,x in v.items() if k not in ('producer_sha256','record_sha256')}
        if scientific(rebuilt)!=scientific(record):raise ValueError('original retained refresh prediction differs')
        return _prepared(record)

    def summary(self):
        with self.connect() as db:
            return dict(decisions=db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],targets=db.execute('SELECT COUNT(*) FROM targets').fetchone()[0],
                database_maximum_bytes=MAX_DATABASE_BYTES,database_allocated_bytes=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0],
                retention='no automatic pruning of original decisions or scores')

    def due(self,scope,now,limit):
        with self.connect() as db:
            return db.execute('SELECT t.key,t.issue,t.target FROM targets t LEFT JOIN scores s ON s.scope=? AND s.key=t.key '
                'LEFT JOIN attempts a ON a.scope=? AND a.key=t.key WHERE s.key IS NULL AND t.target<=? AND (a.retry IS NULL OR a.retry<=?) '
                'ORDER BY COALESCE(a.retry,t.target),t.target,t.key LIMIT ?',(scope,scope,(now-timedelta(minutes=2)).isoformat(),now.isoformat(),limit)).fetchall()

    def defer(self,scope,key,now,reason):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?,?)',(scope,key,(now+timedelta(hours=1)).isoformat(),reason))


def monitor_refresh(state,*,archive,site,now,sensor_epoch,observation_policy_sha256,read_outcomes,limit=8,apply=False,guard=lambda:None,clock=None):
    """At most32 qualified point attempts; preview writes only a temporary copy."""
    from weather_temperature_evidence import sensor_epoch_id
    now=utc(now);epoch=sensor_epoch_id(sensor_epoch);policy=digest(observation_policy_sha256)
    if type(limit) is not int or not 0<=limit<=32 or type(apply) is not bool or not callable(read_outcomes):raise ValueError('bounded explicit refresh monitor required')
    scope=identity(dict(epoch=epoch,policy=policy,quality='qualified_receipt_v2',contract=CONTRACT_SHA256))
    assessment_clock=(lambda:now) if clock is None else clock
    if not (state.root/DATABASE).exists():return dict(status='not_enabled',scored=0,would_score=0,observations_attempted=0,completed_scores=0,withheld={})
    if not apply:
        with tempfile.TemporaryDirectory(prefix='refresh-preview-',dir=state.root) as directory:
            source=RefreshQueue(state);path=Path(directory)/DATABASE
            with source.connect() as old:
                new=sqlite3.connect(path)
                try:old.backup(new)
                finally:new.close()
            path.chmod(0o600)
            return _monitor(RefreshQueue(state,db_path=path),archive,site,scope,now,epoch,policy,read_outcomes,limit,False,guard,assessment_clock)
    return _monitor(RefreshQueue(state),archive,site,scope,now,epoch,policy,read_outcomes,limit,True,guard,assessment_clock)


def _monitor(queue,archive,site,scope,now,epoch,policy,read_outcomes,limit,apply,guard,clock):
    guard();queue.recover();withheld={};cache={};selected=[]
    def defer(key,reason):
        withheld[reason]=withheld.get(reason,0)+1;queue.defer(scope,key,now,reason)
    for key,issue,target in queue.due(scope,now,limit):
        guard()
        try:
            if issue not in cache:cache[issue]=queue.load(issue,archive=archive,site=site)
            selected.append((key,cache[issue],instant(target)))
        except FileNotFoundError:defer(key,'missing_original')
        except (OSError,ValueError,KeyError,TypeError):defer(key,'invalid_original')
    outcomes={}
    if selected:
        guard()
        try:outcomes=read_outcomes(sorted({at for _,_,at in selected}),now)
        except (TimeoutError,MemoryError,AdmissionDeferred):raise
        except Exception:outcomes={}
    assessed=max(now,utc(clock()));completed=0
    for key,record,at in selected:
        guard();outcome=outcomes.get(at)
        if outcome is None:defer(key,'missing_outcome');continue
        try:
            if not isinstance(outcome,TemperatureOutcome) or outcome.sensor_epoch!=epoch or utc(outcome.assessed_at)>assessed:
                raise ValueError('matching qualified current epoch required')
            score=score_refresh_target(record,target_at=at,outcome=outcome,observation_policy_sha256=policy,measurement_quality='qualified_receipt_v2')
        except (ValueError,KeyError,TypeError):defer(key,'outcome_unqualified');continue
        with queue.connect() as db:db.execute('INSERT OR IGNORE INTO scores VALUES(?,?,?,?)',(scope,key,at.isoformat(),canonical(score).decode()))
        completed+=1
    with queue.connect() as db:
        count=db.execute('SELECT COUNT(*) FROM scores WHERE scope=?',(scope,)).fetchone()[0]
        rows=db.execute('SELECT body FROM scores WHERE scope=? AND target>=? AND target<=? ORDER BY target,key LIMIT 10001',
            (scope,(now-timedelta(days=7)).isoformat(),now.isoformat())).fetchall()
        pending=db.execute('SELECT COUNT(*) FROM targets t LEFT JOIN scores s ON s.scope=? AND s.key=t.key WHERE s.key IS NULL',(scope,)).fetchone()[0]
    if len(rows)>10000:raise ValueError('bounded refresh report window exceeded')
    report=summarize_refresh_scores([validate_refresh_score(json.loads(raw)) for (raw,) in rows])
    result=dict(status='applied' if apply else 'preview',generated_at=assessed.isoformat(),valid_until=(assessed+timedelta(hours=2)).isoformat(),scored=completed if apply else 0,would_score=0 if apply else completed,
        observations_attempted=len(selected),completed_scores=count,pending=pending,withheld=withheld,report=report,capacity=queue.summary(),
        arrival_deadline_basis='original outcome availability within7days; discovery may be later',report_target_window_days=7,
        probability_claim=False,automatic_actuation=False)
    if len(canonical(result))>512*1024:raise ValueError('bounded refresh performance report required')
    if apply:queue.state._write(queue.state.root/'refresh-performance.json',result)
    return result



def captured_refresh_outcomes(state,targets,*,assessed_at,sensor_epoch,observation_policy_sha256,read_temperature,apply,clock):
    """Retain the first actual native-reader acquisition once per target/cohort.

    The private capture is the authoritative native-adapter metadata, including
    its original snapshot SHA, not a later query masquerading as past knowledge.
    Each forecast of that measured target reuses the same acquisition clock.
    """
    from .features import _jsonable,local_temperature_outcome
    from weather_temperature_evidence import sensor_epoch_id
    epoch=sensor_epoch_id(sensor_epoch);policy=digest(observation_policy_sha256);assessed_at=utc(assessed_at)
    if type(apply) is not bool or not isinstance(targets,list) or len(targets)>32:raise ValueError('bounded explicit refresh outcome capture required')
    captured={};missing=[];keys={}
    for target in targets:
        at=utc(target);key=identity(dict(target=at.isoformat(),epoch=epoch,policy=policy));keys[at]=key
        try:value=_read(state.root/'weather-outcomes'/(key+'.refresh.json'),65536)
        except FileNotFoundError:missing.append(at);continue
        _checked(value,'capture_sha256')
        if (value['schema']!='earthship-refresh-native-observation/v1' or value['target_at']!=at.isoformat()
                or value['sensor_epoch']!=epoch or value['observation_policy_sha256']!=policy or value['target_key']!=key):
            raise ValueError('original captured refresh observation differs')
        captured[at]=value
    requested=max(assessed_at,utc(clock()))
    metadata=read_temperature(missing,assessed_at) if missing else {}
    acquired=max(requested,utc(clock()))
    for at in missing:
        point=metadata.get(at)
        if point is None:continue
        try:local_temperature_outcome(point,target_at=at,assessed_at=acquired,sensor_epoch=epoch)
        except (ValueError,KeyError,TypeError):continue
        value=dict(schema='earthship-refresh-native-observation/v1',target_key=keys[at],target_at=at.isoformat(),
            sensor_epoch=epoch,observation_policy_sha256=policy,requested_at=requested.isoformat(),acquired_at=acquired.isoformat(),
            native_metadata=_jsonable(point),source='existing_native_temperature_v2_reader',automatic_actuation=False)
        value['capture_sha256']=identity(value)
        if apply:state._write(state.root/'weather-outcomes'/(keys[at]+'.refresh.json'),value,immutable=True)
        captured[at]=value
    result={}
    for at,value in captured.items():
        point=dict(value['native_metadata'])
        for field in ('receivedAt','storedAt','validUntil'):point[field]=instant(point[field])
        ready=instant(value['acquired_at'])
        if not instant(value['requested_at'])<=ready<=acquired:raise ValueError('original capture acquisition clocks differ')
        outcome=local_temperature_outcome(point,target_at=at,assessed_at=acquired,sensor_epoch=epoch)
        result[at]=replace(outcome,available_at=max(at,ready))
    return result
