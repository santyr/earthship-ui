"""Durable original shadow emissions and bounded scoring, never model refitting."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import json,os,shutil,sqlite3,stat,tempfile
from household_job_budget import AdmissionDeferred
from weather_source_files import _read as _read_bytes
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .shadow import _read,_directory
from .probabilistic import ForecastInput
from .probabilistic_issue import MarginalIssue,validate_marginal_issue,scoring_rows,CONTRACT_SHA256
from .probabilistic_artifacts import read_candidates
from .probabilistic_evaluation import _raw_score,score_retained_prediction
from .marginal_outcomes import captured_observations,observation_key,load_observation
from .worker import collector_lock

DATABASE='marginal-scores.sqlite3'
CACHE='marginal-candidates.json'
MAX_DATABASE_BYTES=64*1024**2
MAX_BYTES=16*1024**2


def _checked(value,key):
    if not isinstance(value,dict) or value.get(key)!=identity({k:v for k,v in value.items() if k!=key}):raise ValueError('unchanged original marginal object required')
    return value


def _producer():
    paths=[Path(__file__),Path(__file__).with_name('marginal_outcomes.py'),Path(__file__).with_name('probabilistic_evaluation.py'),Path(__file__).with_name('marginal_reporting.py')]
    return identity({p.name:sha256(p.read_bytes()).hexdigest() for p in paths})


def public_issue(value,*,policy):
    value=validate_marginal_issue(value,policy=policy);decision=instant(value['decision_at']);expiry=decision+timedelta(hours=2);rows=[]
    for source in value['source_originals'].values():expiry=min(expiry,instant(source['initialized_at'])+timedelta(hours=24))
    for row in value['rows']:
        f=row['forecast'];local={}
        for family,p in row['candidates']['marginals'].items():
            local[family]=None if p is None else {k:p[k] for k in ('mean','quantile_levels','quantiles','point_estimate','point_estimate_kind','model_sha256')}
        adaptive=row['candidates']['adaptive']
        rows.append(dict(kind=f['kind'],target_start=f['target_start'],target_end=f['target_end'],source_sha256=f['forecast_sha256'],raw=row['raw'],local=local,
            adaptive=None if adaptive is None else {k:adaptive.get(k) for k in ('value','candidate_used','model_sha256')},status=row['candidates']['status'],reason=row['candidates']['reason']))
    body=dict(schema='earthship-local-marginal-shadow-view/v1',issue_sha256=value['issue_sha256'],generated_at=value['decision_at'],valid_until=expiry.isoformat(),status=value['status'],rows=rows,
        contract_sha256=CONTRACT_SHA256,policy_sha256=value['policy_sha256'],issued=True,product='read_only_unselected_shadow',core_forecast_modified=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    body['report_sha256']=identity(body);return body


class MarginalQueue:
    def __init__(self,state,*,policy,db_path=None):
        from .probabilistic import _policy
        self.state=state;self.policy=_policy(policy);self.originals=state.root/'marginal-issues';self.emissions=state.root/'marginal-emissions'
        _directory(self.originals);_directory(self.emissions);self.db=state.root/DATABASE if db_path is None else Path(db_path)
        if not self.db.is_absolute() or self.db.parent.resolve()!=self.db.parent or not self.db.is_relative_to(state.root):raise ValueError('private marginal index namespace required')
        fd=os.open(self.db,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:raise ValueError('private owned marginal index required')
        finally:os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS issues (key TEXT PRIMARY KEY,digest TEXT NOT NULL,issued TEXT NOT NULL,emitted TEXT,emission_digest TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS targets (key TEXT PRIMARY KEY,issue TEXT NOT NULL,row_digest TEXT NOT NULL,target TEXT NOT NULL,start TEXT NOT NULL,kind TEXT NOT NULL,eligible INTEGER NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS targets_time ON targets(target,key)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (scope TEXT,key TEXT,retry TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(scope,key))')
            db.execute('CREATE TABLE IF NOT EXISTS scores (scope TEXT,key TEXT,target TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(scope,key))')
            db.execute('CREATE INDEX IF NOT EXISTS scores_window ON scores(scope,target,key)')
            db.execute('CREATE TABLE IF NOT EXISTS recovery (id INTEGER PRIMARY KEY CHECK(id=1),after_name TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        if shutil.disk_usage(self.state.root).free<32*1024**2:raise ValueError('marginal index disk headroom exhausted')
        db=sqlite3.connect(self.db,timeout=2)
        try:
            db.execute('PRAGMA cache_size=-2048');db.execute('PRAGMA synchronous=FULL');size=db.execute('PRAGMA page_size').fetchone()[0]
            if db.execute('PRAGMA max_page_count='+str(MAX_DATABASE_BYTES//size)).fetchone()[0]*size>MAX_DATABASE_BYTES:raise ValueError('marginal database capacity exceeded')
            with db:yield db
        finally:db.close()

    def _original(self,key,*,indexed=True):
        digest(key);wrapper=_checked(_read(self.originals/(key+'.json'),MAX_BYTES),'wrapper_sha256')
        if (wrapper.get('schema')!='earthship-retained-marginal-issue/v1' or wrapper.get('storage_key')!=key or wrapper.get('automatic_actuation') is not False):raise ValueError('original marginal wrapper required')
        issue=validate_marginal_issue(wrapper['issue'],policy=self.policy)
        view=_checked(wrapper['public_view'],'report_sha256')
        if view['issue_sha256']!=key or view['policy_sha256']!=issue['policy_sha256'] or view['contract_sha256']!=CONTRACT_SHA256:raise ValueError('original public marginal view differs')
        if issue['issue_sha256']!=key or set(wrapper['model_artifacts'])!=set(issue['bundle_originals']):raise ValueError('original candidate artifact references differ')
        if indexed:
            with self.connect() as db:row=db.execute('SELECT digest FROM issues WHERE key=?',(key,)).fetchone()
            if row!=(wrapper['wrapper_sha256'],):raise ValueError('original marginal index generation differs')
        for pin,artifact in wrapper['model_artifacts'].items():
            if read_candidates(self.state,artifact,policy=self.policy,require_current=False).to_dict()!=issue['bundle_originals'][pin]:raise ValueError('original candidate model artifact differs')
        return wrapper

    def _emission(self,key,wrapper):
        value=_checked(_read(self.emissions/(key+'.json'),65536),'emission_sha256');issue=wrapper['issue']
        if (value.get('schema') not in ('earthship-confirmed-marginal-emission/v1','earthship-confirmed-marginal-emission/v2') or value.get('issue_sha256')!=key or value.get('wrapper_sha256')!=wrapper['wrapper_sha256'] or
                value.get('report_sha256')!=wrapper['public_view']['report_sha256'] or value.get('contract_sha256')!=CONTRACT_SHA256 or value.get('automatic_actuation') is not False or
                not instant(issue['decision_at'])<=instant(value['cache_write_completed_at'])<instant(wrapper['public_view']['valid_until'])):raise ValueError('original marginal emission differs')
        if value['schema']=='earthship-confirmed-marginal-emission/v2' and value.get('cache_bytes_sha256')!=sha256(canonical(wrapper['public_view'])).hexdigest():raise ValueError('original marginal emission byte binding differs')
        return value

    def _register(self,wrapper,emission=None):
        key=wrapper['storage_key'];issue=wrapper['issue'];completed=None if emission is None else emission['cache_write_completed_at'];pin=None if emission is None else emission['emission_sha256']
        with self.connect() as db:
            previous=db.execute('SELECT digest,emitted,emission_digest FROM issues WHERE key=?',(key,)).fetchone()
            if previous is not None and (previous[0]!=wrapper['wrapper_sha256'] or previous[1] is not None and emission is not None and previous[1:]!=(completed,pin)):raise ValueError('original marginal generation differs')
            db.execute('INSERT OR IGNORE INTO issues VALUES(?,?,?,?,?)',(key,wrapper['wrapper_sha256'],issue['decision_at'],completed,pin))
            if emission is not None:db.execute('UPDATE issues SET emitted=?,emission_digest=? WHERE key=?',(completed,pin,key))
            for row in scoring_rows(issue):
                f=row['forecast'];work=identity(dict(issue=key,row=row['row_sha256'],contract=CONTRACT_SHA256))
                eligible=int(completed is not None and (instant(f['target_end'])>instant(completed) if f['kind']=='temperature' else instant(f['target_start'])>=instant(completed)))
                db.execute('INSERT OR IGNORE INTO targets VALUES(?,?,?,?,?,?,?)',(work,key,row['row_sha256'],f['target_end'],f['target_start'],f['kind'],eligible))
                if emission is not None:db.execute('UPDATE targets SET eligible=? WHERE key=?',(eligible,work))

    def retain(self,issue,*,model_artifacts):
        if not isinstance(issue,MarginalIssue) or not isinstance(model_artifacts,dict) or len(model_artifacts)>12:raise ValueError('original prepared marginal issue and bounded artifacts required')
        value=validate_marginal_issue(issue.to_dict(),policy=self.policy,replay=True);key=value['issue_sha256']
        if set(model_artifacts)!=set(value['bundle_originals']):raise ValueError('all original candidate artifacts required')
        for pin,artifact in model_artifacts.items():
            if read_candidates(self.state,artifact,policy=self.policy,require_current=False).to_dict()!=value['bundle_originals'][pin]:raise ValueError('original fitted artifact differs')
        wrapper=dict(schema='earthship-retained-marginal-issue/v1',storage_key=key,issue=value,model_artifacts=model_artifacts,public_view=public_issue(value,policy=self.policy),automatic_actuation=False);wrapper['wrapper_sha256']=identity(wrapper)
        self.state._write(self.originals/(key+'.json'),wrapper,immutable=True);self._register(wrapper);return key

    def confirm(self,key,*,clock,not_before=None):
        wrapper=self._original(key);expected=wrapper['public_view']
        cache_bytes=_read_bytes(self.state.root/CACHE,MAX_BYTES)
        if cache_bytes!=canonical(expected):raise ValueError('actual marginal cache byte readback differs')
        try:emission=self._emission(key,wrapper)
        except FileNotFoundError:
            completed=utc(clock())
            if not max(instant(expected['generated_at']),instant(expected['generated_at']) if not_before is None else utc(not_before))<=completed<instant(expected['valid_until']):raise ValueError('actual marginal publication clock outside original lifetime')
            emission=dict(schema='earthship-confirmed-marginal-emission/v2',cache_bytes_sha256=sha256(cache_bytes).hexdigest(),issue_sha256=key,wrapper_sha256=wrapper['wrapper_sha256'],report_sha256=expected['report_sha256'],cache_write_completed_at=completed.isoformat(),contract_sha256=CONTRACT_SHA256,automatic_actuation=False)
            emission['emission_sha256']=identity(emission);self.state._write(self.emissions/(key+'.json'),emission,immutable=True)
        self._register(wrapper,emission);return key

    def publish(self,issue,*,model_artifacts,clock=lambda:datetime.now(timezone.utc)):
        with collector_lock(self.state.root/'marginal-publish.lock'):
            self.recover(clock=clock);key=self.retain(issue,model_artifacts=model_artifacts);report=self._original(key)['public_view'];before=utc(clock())
            if not instant(report['generated_at'])<=before<instant(report['valid_until']):raise ValueError('marginal view expired before publication')
            self.state._write(self.state.root/CACHE,report);return self.confirm(key,clock=clock,not_before=before)

    def load(self,key):
        value=self._original(key);emission=self._emission(key,value)
        with self.connect() as db:row=db.execute('SELECT emitted,emission_digest FROM issues WHERE key=?',(key,)).fetchone()
        if row!=(emission['cache_write_completed_at'],emission['emission_sha256']):raise ValueError('original marginal emission generation differs')
        return value['issue'],emission

    def recover(self,*,limit=16,clock=lambda:datetime.now(timezone.utc),reconcile_cache=True):
        if type(limit) is not int or not 1<=limit<=16:raise ValueError('bounded marginal recovery required')
        paths=sorted(self.originals.glob('*.json'))
        if len(paths)>10000:raise ValueError('bounded marginal original capacity exceeded')
        with self.connect() as db:cursor=db.execute('SELECT after_name FROM recovery WHERE id=1').fetchone()
        after='' if cursor is None else cursor[0];selected=[p for p in paths if p.name>after][:limit]
        if not selected:selected=paths[:limit]
        recovered=invalid=0
        for path in selected:
            try:
                wrapper=self._original(path.stem,indexed=False)
                try:emission=self._emission(path.stem,wrapper)
                except FileNotFoundError:emission=None
                with self.connect() as db:old=db.execute('SELECT digest,emission_digest FROM issues WHERE key=?',(path.stem,)).fetchone()
                expected=(wrapper['wrapper_sha256'],None if emission is None else emission['emission_sha256'])
                if old!=expected:self._register(wrapper,emission);recovered+=1
            except (OSError,ValueError,KeyError,TypeError):invalid+=1
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO recovery VALUES(1,?)',('' if not selected else selected[-1].name,))
        if reconcile_cache:
            try:
                cached=_read(self.state.root/CACHE,MAX_BYTES);key=cached['issue_sha256']
                with self.connect() as db:known=db.execute('SELECT emitted FROM issues WHERE key=?',(key,)).fetchone()
                if known==(None,):self.confirm(key,clock=clock)
            except (OSError,ValueError,KeyError,TypeError):pass
        return dict(inspected=len(selected),recovered=recovered,invalid=invalid)

    def summary(self):
        with self.connect() as db:
            return dict(issues=db.execute('SELECT COUNT(*) FROM issues').fetchone()[0],confirmed=db.execute('SELECT COUNT(*) FROM issues WHERE emitted IS NOT NULL').fetchone()[0],targets=db.execute('SELECT COUNT(*) FROM targets').fetchone()[0],late_emission_targets=db.execute('SELECT COUNT(*) FROM targets t JOIN issues i ON i.key=t.issue WHERE i.emitted IS NOT NULL AND t.eligible=0').fetchone()[0],database_maximum_bytes=MAX_DATABASE_BYTES,database_allocated_bytes=db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0],retention='originals and scores are not automatically pruned')

    def due(self,scope,now,limit):
        with self.connect() as db:
            return db.execute('SELECT t.key,t.issue,t.row_digest,t.target FROM targets t JOIN issues i ON i.key=t.issue AND i.emitted IS NOT NULL LEFT JOIN scores s ON s.scope=? AND s.key=t.key LEFT JOIN attempts a ON a.scope=? AND a.key=t.key WHERE t.eligible=1 AND s.key IS NULL AND t.target<=? AND (a.retry IS NULL OR a.retry<=?) ORDER BY COALESCE(a.retry,t.target),t.target,t.key LIMIT ?',(scope,scope,(now-timedelta(minutes=2)).isoformat(),now.isoformat(),limit)).fetchall()

    def defer(self,scope,key,now,reason):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?,?)',(scope,key,(now+timedelta(hours=1)).isoformat(),reason))


def _score(issue,emission,row,outcome):
    from .probabilistic_retained import prepare_marginal_source
    body=load_observation(outcome.to_dict()).to_dict();raw=dict(row['forecast']);raw.pop('input_sha256');frame=ForecastInput(**raw)
    if (body['kind'],body['target_start'],body['target_end'])!=(frame.kind,frame.target_start,frame.target_end):raise ValueError('matching original marginal observation required')
    source=prepare_marginal_source(issue['source_originals'][frame.forecast_sha256],assessed_at=instant(issue['decision_at']));original=source.forecast(frame.kind,target=instant(frame.target_end),quality=body['quality'],origin=instant(frame.origin))
    bundle=issue['bundle_originals'].get(row['candidates']['bundle_sha256']);parent=frame.cohort_sha256 if bundle is None or bundle.get('partition') is None else bundle['partition']['parent_cohort_sha256']
    compatible=original is not None and original.cohort_sha256==parent;local={}
    for family,prediction in row['candidates']['marginals'].items():
        if prediction is not None and prediction['input_sha256']!=frame.input_sha256:raise ValueError('original marginal prediction input differs')
        local[family]=None if prediction is None or not compatible else score_retained_prediction(prediction,body['value'])
    adaptive=row['candidates']['adaptive'];adaptive_score=None
    if compatible and adaptive and adaptive['candidate_used']:adaptive_score=dict(absolute_error=abs(adaptive['value']-body['value']),signed_error=adaptive['value']-body['value'])
    value=dict(schema='earthship-original-emitted-marginal-score/v1',contract_sha256=CONTRACT_SHA256,issue_sha256=issue['issue_sha256'],emission_sha256=emission['emission_sha256'],row_sha256=row['row_sha256'],forecast=asdict(frame),bundle_sha256=row['candidates']['bundle_sha256'],
        configured_bundle_sha256s=sorted(issue['bundle_originals']),model_set_sha256=identity(sorted(issue['bundle_originals'])),scoring_producer_sha256=_producer(),emitted_at=emission['cache_write_completed_at'],observation={k:v for k,v in body.items() if k!='original'},raw=_raw_score(frame,body['value']),local=local,adaptive=adaptive_score,measurement_cohort_compatible=compatible,
        fallback_reason=row['candidates']['reason'] if compatible else 'observed_measurement_cohort_changed',issued=True,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    value['score_sha256']=identity(value);return value


def monitor_marginals(state,*,now,policy,observation_policy_sha256,read_observation,limit=8,apply=False,clock=None,guard=lambda:None):
    now=utc(now);digest(observation_policy_sha256);clock=(lambda:now) if clock is None else clock
    if type(limit) is not int or not 0<=limit<=8 or type(apply) is not bool or not callable(read_observation):raise ValueError('bounded explicit marginal monitor required')
    if not (state.root/DATABASE).exists():return dict(status='not_enabled',scored=0,would_score=0,observations_attempted=0,completed_scores=0,withheld={})
    scope=identity(dict(policy=observation_policy_sha256,contract=CONTRACT_SHA256,scoring_producer=_producer()))
    if not apply:
        with tempfile.TemporaryDirectory(prefix='marginal-preview-',dir=state.root) as directory:
            source=MarginalQueue(state,policy=policy);path=Path(directory)/DATABASE
            with source.connect() as old:
                new=sqlite3.connect(path)
                try:old.backup(new)
                finally:new.close()
            path.chmod(0o600)
            return _monitor(MarginalQueue(state,policy=policy,db_path=path),scope,now,observation_policy_sha256,read_observation,limit,False,clock,guard)
    return _monitor(MarginalQueue(state,policy=policy),scope,now,observation_policy_sha256,read_observation,limit,True,clock,guard)


def _monitor(queue,scope,now,policy,read,limit,apply,clock,guard):
    guard();queue.recover(clock=clock,reconcile_cache=apply);withheld={};attempted=completed=0;cache={}
    def defer(key,reason):withheld[reason]=withheld.get(reason,0)+1;queue.defer(scope,key,now,reason)
    for key,name,rowpin,target in queue.due(scope,now,limit):
        guard()
        try:
            if name not in cache:cache[name]=queue.load(name)
            issue,emission=cache[name];row=next(r for r in scoring_rows(issue) if r['row_sha256']==rowpin)
        except FileNotFoundError:defer(key,'missing_original');continue
        except (OSError,ValueError,KeyError,TypeError,StopIteration):defer(key,'invalid_original');continue
        f=row['forecast'];work=dict(kind=f['kind'],start=f['target_start'],end=f['target_end'])
        try:
            attempted+=1;captured=captured_observations(queue.state,[work],now=now,observation_policy_sha256=policy,read=read,apply=apply,clock=clock,guard=guard)
            outcome=captured.get(observation_key(work,policy));assessed=max(now,utc(clock()))
            if outcome is None:defer(key,'missing_outcome');continue
            ready=instant(outcome.to_dict()['available_at'])
            if ready>instant(target)+timedelta(days=7):defer(key,'outcome_arrived_late');continue
            if ready>assessed:raise ValueError('actual marginal observation not available')
            score=_score(issue,emission,row,outcome)
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except (OSError,ValueError,KeyError,TypeError):defer(key,'outcome_unqualified');continue
        with queue.connect() as db:
            inserted=db.execute('INSERT OR IGNORE INTO scores VALUES(?,?,?,?)',(scope,key,target,canonical(score).decode())).rowcount
            db.execute('DELETE FROM attempts WHERE scope=? AND key=?',(scope,key))
        completed+=inserted
    guard();assessed=max(now,utc(clock()));capacity=queue.summary()
    with queue.connect() as db:
        total=db.execute('SELECT COUNT(*) FROM scores WHERE scope=?',(scope,)).fetchone()[0]
        pending=db.execute('SELECT COUNT(*) FROM targets t JOIN issues i ON i.key=t.issue AND i.emitted IS NOT NULL LEFT JOIN scores s ON s.scope=? AND s.key=t.key WHERE t.eligible=1 AND s.key IS NULL',(scope,)).fetchone()[0]
        records=db.execute('SELECT body FROM scores WHERE scope=? AND target>=? AND target<=? ORDER BY target DESC,key LIMIT 10001',(scope,(assessed-timedelta(days=28)).isoformat(),assessed.isoformat())).fetchall()
    from .marginal_reporting import summarize_scores
    comparisons=summarize_scores([json.loads(r[0]) for r in records[:10000]],policy=queue.policy,guard=guard)
    result=dict(schema='earthship-marginal-performance/v1',status='applied' if apply else 'preview',generated_at=assessed.isoformat(),valid_until=(assessed+timedelta(hours=2)).isoformat(),scope_sha256=scope,scored=completed if apply else 0,would_score=0 if apply else completed,observations_attempted=attempted,completed_scores=total,pending=pending,prepared_not_confirmed=capacity['issues']-capacity['confirmed'],withheld=withheld,capacity=capacity,arrival_deadline_basis='actual first observation acquisition within7days; later discovery allowed',comparisons=comparisons,report_target_window_days=28,summary_truncated=len(records)>10000,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    result['report_sha256']=identity(result)
    if apply:queue.state._write(queue.state.root/'marginal-performance.json',result)
    return result
