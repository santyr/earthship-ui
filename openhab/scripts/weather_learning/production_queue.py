"""Durable work for confirmed production outputs under the existing monitor owner."""
from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
from itertools import islice
from pathlib import Path
import json,os,shutil,sqlite3,stat,tempfile
from household_job_budget import AdmissionDeferred
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .production_emissions import read_issue,read_emission,SCORE_OFFSETS
from .production_scoring import score_emitted,scoring_runtime
from .marginal_outcomes import captured_observations,observation_key

DATABASE='production-scores.sqlite3'
MAX_DATABASE_BYTES=256*1024**2
CONTRACT=dict(schema='earthship-confirmed-production-evaluation-contract/v1',score_offsets=list(SCORE_OFFSETS),maximum_label_attempts=48,maturity_seconds=120,arrival_allowance_days=7,automatic_actuation=False)
CONTRACT_SHA256=identity(CONTRACT)


def _producer():
    return identity(dict(files={name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('production_scoring.py','production_emissions.py','probabilistic.py','probabilistic_evaluation.py','marginal_outcomes.py')},runtime=scoring_runtime()))


def _paths(root):
    paths=list(islice(root.glob('*.json'),10001))
    if len(paths)>10000:raise ValueError('bounded production original inventory required')
    return sorted(paths)


class ProductionQueue:
    def __init__(self,state,*,db_path=None):
        self.state=state;self.db=state.root/DATABASE if db_path is None else Path(db_path)
        if not self.db.is_absolute() or self.db.parent.resolve()!=self.db.parent or not self.db.is_relative_to(state.root):
            raise ValueError('private production index namespace required')
        fd=os.open(self.db,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:raise ValueError('private owned production index required')
        finally:os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS emissions (key TEXT PRIMARY KEY,issue TEXT NOT NULL,published TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS targets (key TEXT PRIMARY KEY,emission TEXT NOT NULL,row TEXT NOT NULL,target TEXT NOT NULL,start TEXT NOT NULL,kind TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS targets_time ON targets(target,key)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (scope TEXT,key TEXT,retry TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(scope,key))')
            db.execute('CREATE TABLE IF NOT EXISTS scores (scope TEXT,key TEXT,target TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(scope,key))')
            db.execute('CREATE INDEX IF NOT EXISTS scores_time ON scores(scope,target,key)')
            db.execute('CREATE TABLE IF NOT EXISTS recovery (id INTEGER PRIMARY KEY CHECK(id=1),after_name TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        if shutil.disk_usage(self.state.root).free<32*1024**2:raise ValueError('production index disk headroom exhausted')
        db=sqlite3.connect(self.db,timeout=2)
        try:
            db.execute('PRAGMA cache_size=-2048');db.execute('PRAGMA synchronous=FULL');size=db.execute('PRAGMA page_size').fetchone()[0]
            if db.execute('PRAGMA max_page_count='+str(MAX_DATABASE_BYTES//size)).fetchone()[0]*size>MAX_DATABASE_BYTES:
                raise ValueError('production database capacity exceeded')
            with db:yield db
        finally:db.close()

    def register(self,pin):
        emission=read_emission(self.state,pin);issue=read_issue(self.state,emission['issue_sha256']).to_dict();rows={identity(r):r for r in issue['rows']}
        with self.connect() as db:
            prior=db.execute('SELECT issue,published FROM emissions WHERE key=?',(pin,)).fetchone()
            expected=(emission['issue_sha256'],emission['published_at'])
            if prior is not None and prior!=expected:raise ValueError('original production index identity differs')
            db.execute('INSERT OR IGNORE INTO emissions VALUES(?,?,?)',(pin,*expected))
            for ref in emission['score_rows']:
                row=rows[ref['row_sha256']];frame=row['forecast'];key=identity(dict(issue=emission['issue_sha256'],row=ref['row_sha256'],contract=CONTRACT_SHA256))
                # Repeated confirmation of the same original issue cannot create
                # additional independent forecast/observation support.
                db.execute('INSERT OR IGNORE INTO targets VALUES(?,?,?,?,?,?)',(key,pin,ref['row_sha256'],frame['target_end'],frame['target_start'],frame['kind']))
        return emission

    def recover(self,*,limit=8,guard=lambda:None):
        if type(limit) is not int or not 1<=limit<=16:raise ValueError('bounded production recovery required')
        paths=_paths(self.state.root/'production-emissions')
        with self.connect() as db:row=db.execute('SELECT after_name FROM recovery WHERE id=1').fetchone()
        after='' if row is None else row[0];chosen=[p for p in paths if p.name>after][:limit]
        if not chosen:chosen=paths[:limit]
        recovered=invalid=0
        for path in chosen:
            guard()
            with self.connect() as db:known=db.execute('SELECT 1 FROM emissions WHERE key=?',(path.stem,)).fetchone()
            if known is not None:continue
            try:self.register(path.stem);recovered+=1
            except (OSError,ValueError,KeyError,TypeError):invalid+=1
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO recovery VALUES(1,?)',('' if not chosen else chosen[-1].name,))
        return dict(inspected=len(chosen),recovered=recovered,invalid=invalid)

    def due(self,scope,now,limit):
        with self.connect() as db:
            return db.execute("SELECT t.key,t.emission,t.row,t.target,t.start,t.kind FROM targets t LEFT JOIN scores s ON s.scope=? AND s.key=t.key LEFT JOIN attempts a ON a.scope=? AND a.key=t.key WHERE s.key IS NULL AND t.target<=? AND (a.reason IS NULL OR a.reason!='expired') AND (a.retry IS NULL OR a.retry<=?) ORDER BY COALESCE(a.retry,t.target),t.target,t.key LIMIT ?",(scope,scope,(now-timedelta(minutes=2)).isoformat(),now.isoformat(),limit)).fetchall()

    def defer(self,scope,key,now,reason):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?,?)',(scope,key,(now+timedelta(hours=1)).isoformat(),reason))


def monitor_production(state,*,now,observation_policy_sha256,read_observation,limit=48,apply=False,clock=None,guard=lambda:None):
    now=utc(now);digest(observation_policy_sha256);clock=(lambda:now) if clock is None else clock
    if type(limit) is not int or not 0<=limit<=48 or type(apply) is not bool or not callable(read_observation):raise ValueError('bounded production observation allowance required')
    originals=_paths(state.root/'production-issues');emissions=_paths(state.root/'production-emissions')
    if not emissions and not (state.root/DATABASE).exists():
        return dict(status='not_enabled',scored=0,would_score=0,observations_attempted=0,completed_scores=0,pending=0,expired=0,prepared_not_confirmed=len(originals),withheld={})
    scope=identity(dict(observation_policy_sha256=observation_policy_sha256,contract_sha256=CONTRACT_SHA256,scoring_producer_sha256=_producer()))
    if not apply:
        with tempfile.TemporaryDirectory(prefix='production-monitor-preview-',dir=state.root) as directory:
            path=Path(directory)/DATABASE
            if (state.root/DATABASE).exists():
                with ProductionQueue(state).connect() as source:
                    dest=sqlite3.connect(path)
                    try:source.backup(dest)
                    finally:dest.close()
                path.chmod(0o600)
            return _monitor(ProductionQueue(state,db_path=path),scope,now,observation_policy_sha256,read_observation,limit,False,clock,guard,len(originals))
    return _monitor(ProductionQueue(state),scope,now,observation_policy_sha256,read_observation,limit,True,clock,guard,len(originals))


def _monitor(queue,scope,now,policy,read,limit,apply,clock,guard,prepared):
    recovery=queue.recover(guard=guard);attempted=completed=0;withheld={}
    def defer(key,reason):
        withheld[reason]=withheld.get(reason,0)+1;queue.defer(scope,key,now,reason)
    for key,pin,row,target,start,kind in queue.due(scope,now,limit):
        guard()
        try:
            emission=read_emission(queue.state,pin)
            if row not in {r['row_sha256'] for r in emission['score_rows']}:raise ValueError('original production work differs')
        except FileNotFoundError:defer(key,'missing_original');continue
        except (OSError,ValueError,KeyError,TypeError):defer(key,'invalid_original');continue
        work=dict(kind=kind,start=start,end=target);observation_pin=observation_key(work,policy)
        if now>instant(target)+timedelta(days=7) and not (queue.state.root/'weather-outcomes'/(observation_pin+'.marginal.json')).exists():
            defer(key,'expired');continue
        try:
            attempted+=1
            observations=captured_observations(queue.state,[work],now=now,observation_policy_sha256=policy,read=read,apply=apply,clock=clock,guard=guard)
            observation=observations.get(observation_pin)
            if observation is None:defer(key,'missing_outcome');continue
            if instant(observation.to_dict()['available_at'])>instant(target)+timedelta(days=7):defer(key,'expired');continue
            score=score_emitted(queue.state,emission_sha256=pin,row_sha256=row,observation=observation,assessed_at=max(now,utc(clock())))
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except (OSError,ValueError,KeyError,TypeError):defer(key,'outcome_unqualified');continue
        with queue.connect() as db:
            added=db.execute('INSERT OR IGNORE INTO scores VALUES(?,?,?,?)',(scope,key,target,canonical(score).decode())).rowcount
            db.execute('DELETE FROM attempts WHERE scope=? AND key=?',(scope,key))
        completed+=added
    guard();assessed=max(now,utc(clock()))
    with queue.connect() as db:
        total=db.execute('SELECT COUNT(*) FROM scores WHERE scope=?',(scope,)).fetchone()[0]
        valid=db.execute("SELECT COUNT(*) FROM scores WHERE scope=? AND json_extract(body,'$.status')='scored'",(scope,)).fetchone()[0]
        pending=db.execute("SELECT COUNT(*) FROM targets t LEFT JOIN scores s ON s.scope=? AND s.key=t.key LEFT JOIN attempts a ON a.scope=? AND a.key=t.key WHERE s.key IS NULL AND (a.reason IS NULL OR a.reason!='expired')",(scope,scope)).fetchone()[0]
        expired=db.execute("SELECT COUNT(*) FROM attempts WHERE scope=? AND reason='expired'",(scope,)).fetchone()[0]
        confirmed=db.execute('SELECT COUNT(DISTINCT issue) FROM emissions').fetchone()[0]
        capacity=dict(database_maximum_bytes=MAX_DATABASE_BYTES,database_allocated_bytes=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0],retention='originals and scores are not automatically pruned')
    from .production_reporting import summarize_production_scores,MAX_RECORDS,MAX_BYTES
    # Stream literal originals; keeping the SQLite strings, parsed full records
    # and normalized scoring rows simultaneously exhausts the512MiB owner cap.
    truncated=False
    with queue.connect() as db:
        cursor=db.execute('SELECT body FROM scores WHERE scope=? AND target>=? AND target<=? ORDER BY target DESC,key LIMIT ?',
            (scope,(assessed-timedelta(days=28)).isoformat(),assessed.isoformat(),MAX_RECORDS+1))
        def records():
            nonlocal truncated
            for index,row in enumerate(cursor):
                guard()
                if index==MAX_RECORDS:truncated=True;break
                yield json.loads(row[0])
        comparisons=summarize_production_scores(records(),policy=json.loads((Path(__file__).resolve().parents[3]/'docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json').read_bytes()),guard=guard)
    report=dict(schema='earthship-production-weather-performance/v1',status='applied' if apply else 'preview',generated_at=assessed.isoformat(),valid_until=(assessed+timedelta(hours=2)).isoformat(),scope_sha256=scope,
        scored=completed if apply else 0,would_score=0 if apply else completed,observations_attempted=attempted,completed_scores=valid,completed_diagnostics=total-valid,pending=pending,expired=expired,prepared_not_confirmed=max(0,prepared-confirmed),withheld=withheld,recovery=recovery,capacity=capacity,
        comparisons=comparisons,report_target_window_days=28,summary_truncated=truncated,arrival_deadline_basis='actual first observation acquisition within7days; later discovery allowed',parallel_shadow_required=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    report['report_sha256']=identity(report)
    if len(canonical(report))>MAX_BYTES:raise ValueError('bounded production performance report exceeded')
    if apply:queue.state._write(queue.state.root/'production-performance.json',report)
    return report
