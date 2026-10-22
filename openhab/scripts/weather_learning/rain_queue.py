"""Confirmed read-only rain originals and bounded delayed scoring; never fitting."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from math import fsum
import json,os,shutil,sqlite3,stat,tempfile
from household_job_budget import AdmissionDeferred
from weather_source_files import _read as original_bytes
from .contracts import canonical,identity,digest,instant,finite
from .evidence import utc
from .shadow import _read,_directory
from .rain_calibration import _policy,PRODUCTS
from .rain_issues import RainIssue
from .rain_history import RainAcquisition
from .rain_two_part import numerical_sources,lead_scope
from .source_bundle import capture_sources
from .worker import collector_lock

DATABASE='rain-scores.sqlite3'
CACHE='rain-candidates.json'
MAX_DATABASE_BYTES=64*1024**2
MAX_BYTES=16*1024**2
CONTRACT=dict(schema='earthship-rain-shadow-evaluation-contract/v1',maturity_seconds=120,arrival_allowance_days=7,
              population='byte_confirmed_future_interval_shadows',weights='equal_local_dates_then_intervals_then_original_versions',selection=False)
CONTRACT_SHA256=identity(CONTRACT)
ROOT=Path(__file__).resolve().parents[3]


def _checked(value,key):
    if not isinstance(value,dict) or value.get(key)!=identity({k:v for k,v in value.items() if k!=key}):raise ValueError('unchanged original rain object required')
    return value


def public_view(issues):
    rows=[];generated=max(instant(i['prepared_at']) for i in issues);expiry=generated+timedelta(hours=2)
    for issue in issues:
        f=issue['forecast'];expiry=min(expiry,instant(f['initialized_at'])+timedelta(hours=24));local=issue['local_prediction']
        rows.append(dict(issue_sha256=issue['issue_sha256'],start=f['start'],end=f['end'],hours=f['hours'],interval_kind=f['interval_kind'],raw_means_mm=f['products_mm'],local=local,
                         source_available_at=f['actual_source_available_at'],initialized_at=f['initialized_at'],availability_basis=f['availability_basis']))
    value=dict(schema='earthship-rain-shadow-view/v1',generated_at=generated.isoformat(),valid_until=expiry.isoformat(),rows=rows,
               product='read_only_unselected_interval_rain_shadow',native_google_probability=False,probability_calibration_qualified=False,physical_calibration_qualified=False,core_forecast_modified=False,automatic_actuation=False)
    value['report_sha256']=identity(value);return value


class RainQueue:
    def __init__(self,state,*,policy,db_path=None):
        self.state=state;self.policy=_policy(policy);self.originals=state.root/'rain-issues';self.emissions=state.root/'rain-emissions';self.producers=state.root/'rain-producers';self.acquisitions=state.root/'rain-acquisitions'
        for p in (self.originals,self.emissions,self.producers,self.acquisitions):_directory(p)
        self.db=state.root/DATABASE if db_path is None else Path(db_path)
        if not self.db.is_absolute() or self.db.parent.resolve()!=self.db.parent or not self.db.is_relative_to(state.root):raise ValueError('private rain index namespace required')
        fd=os.open(self.db,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:raise ValueError('private owned rain index required')
        finally:os.close(fd)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS bundles (key TEXT PRIMARY KEY,digest TEXT,emitted TEXT,receipt TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS work (key TEXT PRIMARY KEY,bundle TEXT,ordinal INTEGER,start TEXT,end TEXT,eligible INTEGER)')
            db.execute('CREATE INDEX IF NOT EXISTS rain_due ON work(eligible,end,key)')
            db.execute('CREATE TABLE IF NOT EXISTS scores (scope TEXT,key TEXT,body TEXT,PRIMARY KEY(scope,key))')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (scope TEXT,key TEXT,retry TEXT,reason TEXT,expired INTEGER,PRIMARY KEY(scope,key))')
            db.execute('CREATE TABLE IF NOT EXISTS recovery (id INTEGER PRIMARY KEY CHECK(id=1),after_name TEXT)')

    @contextmanager
    def connect(self):
        if shutil.disk_usage(self.state.root).free<32*1024**2:raise ValueError('rain index disk headroom exhausted')
        db=sqlite3.connect(self.db,timeout=2)
        try:
            db.execute('PRAGMA cache_size=-2048');db.execute('PRAGMA synchronous=FULL');size=db.execute('PRAGMA page_size').fetchone()[0];db.execute('PRAGMA max_page_count='+str(MAX_DATABASE_BYTES//size))
            with db:yield db
        finally:db.close()

    def original(self,key):
        digest(key);value=_checked(_read(self.originals/(key+'.json'),MAX_BYTES),'wrapper_sha256')
        if value.get('schema')!='earthship-retained-rain-shadow/v1' or value['wrapper_sha256']!=key or value.get('automatic_actuation') is not False:raise ValueError('original rain wrapper required')
        issues=[RainIssue(canonical(i)).to_dict() for i in value['issues']]
        if not 1<=len(issues)<=32 or any(i['mode']!='prospective_shadow' or i['policy_original']!=self.policy for i in issues):raise ValueError('original prospective rain population required')
        if public_view(issues)!=value['public_view']:raise ValueError('original rain view differs')
        producer=_checked(_read(self.producers/(value['producer_sha256']+'.json'),MAX_BYTES),'producer_sha256')
        if producer['producer_sha256']!=value['producer_sha256']:raise ValueError('original rain producer differs')
        pins={n:sha256(r['utf8'].encode()).hexdigest() for n,r in producer['sources'].items()}
        if any(pins[n]!=r['sha256'] for n,r in producer['sources'].items()) or any(i['producer_sources']!=pins for i in issues):raise ValueError('literal rain producing bytes differ')
        return value

    def emission(self,key,wrapper):
        value=_checked(_read(self.emissions/(key+'.json'),65536),'emission_sha256');view=wrapper['public_view'];at=instant(value['cache_write_completed_at'])
        if (value.get('schema')!='earthship-confirmed-rain-emission/v1' or value.get('wrapper_sha256')!=key or value.get('cache_bytes_sha256')!=sha256(canonical(view)).hexdigest() or
                value.get('contract_sha256')!=CONTRACT_SHA256 or not instant(view['generated_at'])<=at<instant(view['valid_until'])):raise ValueError('original rain emission differs')
        return value

    def _register(self,wrapper,emission=None):
        key=wrapper['wrapper_sha256'];at=None if emission is None else emission['cache_write_completed_at'];pin=None if emission is None else emission['emission_sha256']
        with self.connect() as db:
            old=db.execute('SELECT digest,emitted,receipt FROM bundles WHERE key=?',(key,)).fetchone()
            if old and (old[0]!=key or old[1] is not None and at is not None and old[1:]!=(at,pin)):raise ValueError('rain index generation differs')
            db.execute('INSERT OR IGNORE INTO bundles VALUES(?,?,?,?)',(key,key,at,pin))
            if emission is not None:db.execute('UPDATE bundles SET emitted=?,receipt=? WHERE key=?',(at,pin,key))
            for ordinal,issue in enumerate(wrapper['issues']):
                f=issue['forecast'];work=identity(dict(bundle=key,issue=issue['issue_sha256'],contract=CONTRACT_SHA256));eligible=int(at is not None and instant(at)<instant(f['start']))
                db.execute('INSERT OR IGNORE INTO work VALUES(?,?,?,?,?,?)',(work,key,ordinal,f['start'],f['end'],eligible))
                if emission is not None:db.execute('UPDATE work SET eligible=? WHERE key=?',(eligible,work))

    def retain(self,issues):
        if not isinstance(issues,list) or not 1<=len(issues)<=32 or any(type(i) is not RainIssue for i in issues):raise ValueError('bounded typed rain issue bundle required')
        values=[RainIssue(i.content).to_dict() for i in issues]
        if any(i['mode']!='prospective_shadow' or i['policy_original']!=self.policy for i in values):raise ValueError('prospective rain originals and policy required')
        sources=capture_sources(ROOT);pins={n:sha256(raw).hexdigest() for n,raw in sources.items()}
        if any(i['producer_sources']!=pins for i in values):raise ValueError('original rain producer must be retained without source substitution')
        producer=dict(schema='earthship-original-rain-producer/v1',sources={n:dict(sha256=pins[n],utf8=raw.decode()) for n,raw in sources.items()});producer['producer_sha256']=identity(producer);pp=self.producers/(producer['producer_sha256']+'.json')
        if not pp.exists():self.state._write(pp,producer,immutable=True)
        elif _read(pp,MAX_BYTES)!=producer:raise ValueError('immutable rain producer differs')
        wrapper=dict(schema='earthship-retained-rain-shadow/v1',issues=values,producer_sha256=producer['producer_sha256'],public_view=public_view(values),automatic_actuation=False);wrapper['wrapper_sha256']=identity(wrapper);key=wrapper['wrapper_sha256'];p=self.originals/(key+'.json')
        if not p.exists():self.state._write(p,wrapper,immutable=True)
        elif _read(p,MAX_BYTES)!=wrapper:raise ValueError('immutable rain original differs')
        self._register(wrapper);return key

    def confirm(self,key,*,clock,not_before=None):
        wrapper=self.original(key);view=wrapper['public_view']
        if original_bytes(self.state.root/CACHE,MAX_BYTES)!=canonical(view):raise ValueError('actual rain cache byte readback differs')
        try:emission=self.emission(key,wrapper)
        except FileNotFoundError:
            at=utc(clock())
            if not max(instant(view['generated_at']),instant(view['generated_at']) if not_before is None else utc(not_before))<=at<instant(view['valid_until']):raise ValueError('actual rain cache publication outside lifetime')
            emission=dict(schema='earthship-confirmed-rain-emission/v1',wrapper_sha256=key,cache_bytes_sha256=sha256(canonical(view)).hexdigest(),cache_write_completed_at=at.isoformat(),contract_sha256=CONTRACT_SHA256,automatic_actuation=False);emission['emission_sha256']=identity(emission);self.state._write(self.emissions/(key+'.json'),emission,immutable=True)
        self._register(wrapper,emission);return key

    def publish(self,issues,*,clock=lambda:datetime.now(timezone.utc)):
        with collector_lock(self.state.root/'rain-publish.lock'):
            self.recover(clock=clock);key=self.retain(issues);view=self.original(key)['public_view'];before=utc(clock())
            if not instant(view['generated_at'])<=before<instant(view['valid_until']):raise ValueError('rain view expired before publication')
            self.state._write(self.state.root/CACHE,view);return self.confirm(key,clock=clock,not_before=before)

    def load_bundle(self,key):
        wrapper=self.original(key);emission=self.emission(key,wrapper)
        with self.connect() as db:row=db.execute('SELECT emitted,receipt FROM bundles WHERE key=?',(key,)).fetchone()
        if row!=(emission['cache_write_completed_at'],emission['emission_sha256']):raise ValueError('original rain emission generation differs')
        return wrapper,emission

    def recover(self,*,clock=lambda:datetime.now(timezone.utc),reconcile_cache=True):
        paths=sorted(self.originals.glob('*.json'))
        if len(paths)>10000:raise ValueError('rain original capacity exhausted')
        with self.connect() as db:cursor=db.execute('SELECT after_name FROM recovery WHERE id=1').fetchone()
        selected=[p for p in paths if p.name>('' if cursor is None else cursor[0])][:16] or paths[:16];invalid=0
        for p in selected:
            try:
                wrapper=self.original(p.stem)
                try:emission=self.emission(p.stem,wrapper)
                except FileNotFoundError:emission=None
                self._register(wrapper,emission)
            except (OSError,ValueError,KeyError,TypeError):invalid+=1
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO recovery VALUES(1,?)',('' if not selected else selected[-1].name,))
        if reconcile_cache:
            try:
                cached=_read(self.state.root/CACHE,MAX_BYTES)
                for p in selected:
                    w=self.original(p.stem)
                    if w['public_view']==cached:self.confirm(p.stem,clock=clock);break
            except (OSError,ValueError,KeyError,TypeError):pass
        return dict(inspected=len(selected),invalid=invalid)

    def summary(self):
        with self.connect() as db:return dict(bundles=db.execute('SELECT COUNT(*) FROM bundles').fetchone()[0],confirmed=db.execute('SELECT COUNT(*) FROM bundles WHERE emitted IS NOT NULL').fetchone()[0],targets=db.execute('SELECT COUNT(*) FROM work').fetchone()[0],late_emission_targets=db.execute('SELECT COUNT(*) FROM work w JOIN bundles b ON b.key=w.bundle WHERE b.emitted IS NOT NULL AND w.eligible=0').fetchone()[0],database_maximum_bytes=MAX_DATABASE_BYTES)


def _score(issue,emission,observation,scope):
    o=observation.to_dict();f=issue['forecast'];compatible=o['cohort_sha256']==issue['observation_cohort_sha256'];actual=o['observed_mm'];width=o['boundary_uncertainty_mm'];raw={}
    if f['common_complete_targets']:
        for head in PRODUCTS:
            e=f['products_mm'][head]-actual;raw[head]=dict(forecast_mm=f['products_mm'][head],absolute_error_mm=abs(e),signed_error_mm=e,squared_error_mm=e*e,mae_lower_mm=max(0.,abs(e)-width/2),mae_upper_mm=abs(e)+width/2)
    local=dict(issue['local_prediction'])
    if not compatible:local.update(status='insufficient_evidence',reason='measurement_cohort_changed',probability_wet=None,mean_depth_mm=None,conditional_wet_mean_mm=None)
    label=o['event']['event_label'];p=local['probability_wet'];local['brier']=None if p is None or label is None else (p-label)**2
    from zoneinfo import ZoneInfo
    day=(instant(f['end'])-timedelta(microseconds=1)).astimezone(ZoneInfo(f['site']['timezone'])).date().isoformat()
    value=dict(schema='earthship-original-emitted-rain-score/v1',scope_sha256=scope,issue_sha256=issue['issue_sha256'],emission_sha256=emission['emission_sha256'],emitted_at=emission['cache_write_completed_at'],start=f['start'],end=f['end'],date=day,interval_kind=f['interval_kind'],lead_scope_hours=lead_scope(f),grid_sha256=f['grid_sha256'],timezone=f['site']['timezone'],availability_basis=f['availability_basis'],local_model_sha256=None if issue['model'] is None else issue['model']['model_sha256'],gain_model_sha256=None if issue['gain_model'] is None else issue['gain_model']['model_sha256'],original_producer_sha256=identity(issue['producer_sources']),policy_sha256=issue['policy_original']['policy_sha256'],observation={k:o[k] for k in ('observation_sha256','observed_mm','boundary_uncertainty_mm','available_at','cohort_sha256','event')},raw=raw,local=local,gain_prediction_mm=issue['gain_prediction_mm'] if compatible else None,measurement_cohort_compatible=compatible,issued=True,probability_calibration_qualified=False,automatic_actuation=False)
    value['score_sha256']=identity(value);return value


def _comparisons(records):
    groups={}
    for r in records:
        _checked(r,'score_sha256')
        if r.get('schema')!='earthship-original-emitted-rain-score/v1' or r.get('issued') is not True or r.get('probability_calibration_qualified') is not False:raise ValueError('original emitted rain score required')
        if not r['raw']:continue
        context={k:r[k] for k in ('interval_kind','lead_scope_hours','grid_sha256','timezone','availability_basis','local_model_sha256','gain_model_sha256','original_producer_sha256','policy_sha256')}
        context['measurement_cohort_sha256']=r['observation']['cohort_sha256']
        key=identity(context);groups.setdefault(key,(context,[]))[1].append(r)
    output={}
    for key,(context,rows) in groups.items():
        dates={}
        for row in rows:dates.setdefault(row['date'],{}).setdefault((row['start'],row['end']),[]).append(row)
        weighted=[]
        for targets in dates.values():
            for versions in targets.values():
                weighted.extend((r,1/len(dates)/len(targets)/len(versions)) for r in versions)
        def mean(value):
            usable=[(value(r),w) for r,w in weighted if finite(value(r))]
            return None if not usable else fsum(v*w for v,w in usable)/fsum(w for v,w in usable)
        def loss(prediction):return mean(lambda r:None if not finite(prediction(r)) else abs(prediction(r)-r['observation']['observed_mm']))
        values={head:mean(lambda r:r['raw'][head]['absolute_error_mm']) for head in PRODUCTS}
        raw_metrics={head:dict(mae_mm=values[head],rmse_mm=mean(lambda r:r['raw'][head]['squared_error_mm'])**.5,signed_bias_mm=mean(lambda r:r['raw'][head]['signed_error_mm']),mae_lower_mm=mean(lambda r:r['raw'][head]['mae_lower_mm']),mae_upper_mm=mean(lambda r:r['raw'][head]['mae_upper_mm'])) for head in PRODUCTS}
        local=dict(predicted_records=sum(finite(r['local']['mean_depth_mm']) for r in rows),mae_mm=loss(lambda r:r['local']['mean_depth_mm']),
                   brier=mean(lambda r:r['local']['brier']),
                   training_only_climatology_brier=mean(lambda r:None if r['local']['brier'] is None or r['local']['climatology_probability'] is None else (r['local']['climatology_probability']-r['observation']['event']['event_label'])**2),
                   fallback_mae_mm=loss(lambda r:r['local']['mean_depth_mm'] if finite(r['local']['mean_depth_mm']) else r['raw'][PRODUCTS[0]]['forecast_mm']))
        gain=dict(predicted_records=sum(finite(r['gain_prediction_mm']) for r in rows),mae_mm=loss(lambda r:r['gain_prediction_mm']))
        output[key]=dict(context=context,records=len(rows),independent_target_dates=len(dates),raw_mae_mm=values,raw=raw_metrics,local=local,gain=gain)
    return dict(records=len(records),cohorts=output,weighting=CONTRACT['weights'],probability_calibration_qualified=False,selection=False,automatic_actuation=False)


def monitor_rain(state,*,now,policy,observation_policy_sha256,read_acquisition,limit=8,apply=False,clock=None,guard=lambda:None):
    now=utc(now);digest(observation_policy_sha256);clock=(lambda:now) if clock is None else clock
    if type(limit) is not int or not 0<=limit<=8 or type(apply) is not bool or not callable(read_acquisition):raise ValueError('bounded explicit rain monitor required')
    if not (state.root/DATABASE).exists():return dict(status='not_enabled',scored=0,would_score=0,observations_attempted=0)
    if not apply:
        with tempfile.TemporaryDirectory(prefix='rain-preview-',dir=state.root) as folder:
            path=Path(folder)/DATABASE;source=sqlite3.connect('file:'+str(state.root/DATABASE)+'?mode=ro',uri=True);target=sqlite3.connect(path)
            try:source.backup(target)
            finally:source.close();target.close()
            path.chmod(0o600);return _monitor(RainQueue(state,policy=policy,db_path=path),now,observation_policy_sha256,read_acquisition,limit,False,clock,guard)
    return _monitor(RainQueue(state,policy=policy),now,observation_policy_sha256,read_acquisition,limit,True,clock,guard)


def _monitor(queue,now,policy,read,limit,apply,clock,guard):
    scope=identity(dict(policy=policy,contract=CONTRACT_SHA256,producer=numerical_sources()));queue.recover(clock=clock,reconcile_cache=apply);attempted=completed=0;withheld={}
    def defer(key,reason,expired=False):
        withheld[reason]=withheld.get(reason,0)+1
        with queue.connect() as db:db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?,?,?)',(scope,key,(now+timedelta(hours=1)).isoformat(),reason,int(expired)))
    with queue.connect() as db:
        due=db.execute('SELECT w.key,w.bundle,w.ordinal,w.start,w.end FROM work w LEFT JOIN scores s ON s.scope=? AND s.key=w.key LEFT JOIN attempts a ON a.scope=? AND a.key=w.key WHERE w.eligible=1 AND w.end<=? AND s.key IS NULL AND (a.key IS NULL OR a.expired=0 AND a.retry<=?) ORDER BY w.end,w.key LIMIT ?',(scope,scope,(now-timedelta(seconds=120)).isoformat(),now.isoformat(),limit)).fetchall()
    for key,bundle,ordinal,start,end in due:
        guard()
        try:wrapper,emission=queue.load_bundle(bundle);issue=wrapper['issues'][ordinal]
        except FileNotFoundError:defer(key,'missing_original');continue
        except (OSError,ValueError,KeyError,TypeError,IndexError):defer(key,'invalid_original');continue
        work=dict(start=start,end=end);name=identity(dict(work=work,policy=policy));path=queue.state.root/'weather-outcomes'/(name+'.rain.json');expires=instant(end)+timedelta(days=7)
        try:
            try:acquisition=RainAcquisition(canonical(_read(path,MAX_BYTES)))
            except FileNotFoundError:
                if max(now,utc(clock()))>expires:defer(key,'arrival_deadline_expired',True);continue
                before=max(now,utc(clock()));attempted+=1;acquisition=read(work,before);guard();after=max(now,utc(clock()))
                if acquisition is None:defer(key,'missing_outcome');continue
                if type(acquisition) is not RainAcquisition:raise ValueError('typed original rain acquisition required')
                acquisition=RainAcquisition(acquisition.content);a=acquisition.to_dict()
                if not before<=instant(a['request']['requested_at'])<=instant(a['request']['received_at'])<=after:raise ValueError('actual rain acquisition clock differs')
                if apply:
                    p=queue.acquisitions/(a['acquisition_sha256']+'.json')
                    if not p.exists():queue.state._write(p,a,immutable=True)
            a=acquisition.to_dict()
            if (a['request']['start'],a['request']['end'])!=(start,end):raise ValueError('rain acquisition interval differs')
            observation=acquisition.observation()
            if observation is None:defer(key,'unqualified_outcome');continue
            available=instant(observation.to_dict()['available_at'])
            if available>expires:defer(key,'outcome_arrived_late',True);continue
            if available>max(now,utc(clock())):raise ValueError('future rain outcome refused')
            if apply and not path.exists():queue.state._write(path,a,immutable=True)
            score=_score(issue,emission,observation,scope)
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except (OSError,ValueError,KeyError,TypeError):defer(key,'invalid_acquisition');continue
        with queue.connect() as db:
            inserted=db.execute('INSERT OR IGNORE INTO scores VALUES(?,?,?)',(scope,key,canonical(score).decode())).rowcount;db.execute('DELETE FROM attempts WHERE scope=? AND key=?',(scope,key))
        completed+=inserted
    guard();capacity=queue.summary();assessed=max(now,utc(clock()))
    with queue.connect() as db:
        total=db.execute('SELECT COUNT(*) FROM scores WHERE scope=?',(scope,)).fetchone()[0];expired=db.execute('SELECT COUNT(*) FROM attempts WHERE scope=? AND expired=1',(scope,)).fetchone()[0]
        pending=db.execute('SELECT COUNT(*) FROM work w LEFT JOIN scores s ON s.scope=? AND s.key=w.key LEFT JOIN attempts a ON a.scope=? AND a.key=w.key WHERE w.eligible=1 AND s.key IS NULL AND (a.key IS NULL OR a.expired=0)',(scope,scope)).fetchone()[0]
        records=[json.loads(r[0]) for r in db.execute('SELECT s.body FROM scores s JOIN work w ON w.key=s.key WHERE s.scope=? AND w.end>=? AND w.end<=? ORDER BY w.end DESC,w.key LIMIT 10001',(scope,(assessed-timedelta(days=28)).isoformat(),assessed.isoformat())).fetchall()]
    result=dict(schema='earthship-rain-performance/v1',status='applied' if apply else 'preview',generated_at=assessed.isoformat(),valid_until=(assessed+timedelta(hours=2)).isoformat(),scope_sha256=scope,scored=completed if apply else 0,would_score=0 if apply else completed,observations_attempted=attempted,completed_scores=total,pending=pending,expired=expired,prepared_not_confirmed=capacity['bundles']-capacity['confirmed'],capacity=capacity,withheld=withheld,comparisons=_comparisons(records[:10000]),summary_truncated=len(records)>10000,report_target_window_days=28,probability_calibration_qualified=False,automatic_actuation=False)
    result['report_sha256']=identity(result)
    if apply:queue.state._write(queue.state.root/'rain-performance.json',result)
    return result
