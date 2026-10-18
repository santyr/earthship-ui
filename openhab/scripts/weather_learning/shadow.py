"""Prospective shadow inference and separately scheduled candidate training."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import json,os,pathlib,re,shutil,sqlite3,stat,tempfile
from zoneinfo import ZoneInfo

from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .features import temperature_targets,local_temperature_outcome,training_pair
from .publish import seal_payload,validate_payload,publish_bundle
from .training import fit_bias,fit_residual,validate_artifact,TemperaturePredictor
from .worker import collector_lock

# One original decision per local date; fixed native-hour offsets chosen before
# outcomes. At most 40 targets/day, never more than the model's 20,000-pair bound.
TRAIN_OFFSETS=frozenset([*range(1,25),36,48,60,72,*range(96,361,24)])


def _directory(path):
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    info=path.stat()
    if path.is_symlink() or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('private owned shadow directory required')


def _read(path,limit):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>limit:raise ValueError('private bounded shadow object required')
        with os.fdopen(descriptor,'rb',closefd=False) as stream:raw=stream.read(limit+1)
    finally:os.close(descriptor)
    if len(raw)>limit:raise ValueError('shadow object too large')
    return json.loads(raw)


class ShadowStore:
    def __init__(self,root):
        self.root=pathlib.Path(root)
        if not self.root.is_absolute():raise ValueError('absolute private shadow state path required')
        _directory(self.root)
        for name in ('models','issues'):_directory(self.root/name)
        self.db=self.root/'issues.sqlite3'
        with self._connect() as db:db.execute('CREATE TABLE IF NOT EXISTS issues (digest TEXT PRIMARY KEY, issued TEXT, completed TEXT, local_day TEXT, epoch TEXT)')
        os.chmod(self.db,0o600)

    @contextmanager
    def _connect(self):
        connection=sqlite3.connect(self.db,timeout=2)
        try:
            with connection:yield connection
        finally:connection.close()

    def _write(self,path,value,*,immutable=False):
        raw=canonical(value)
        if len(raw)>16*1024**2 or shutil.disk_usage(self.root).free<len(raw)+32*1024**2:raise ValueError('shadow disk headroom exhausted')
        count=used=0
        for directory in ('issues','models'):
            for item in (self.root/directory).glob('*.json'):
                count+=1;used+=item.stat().st_size
                if count>=10000 or used+len(raw)>2*1024**3:raise ValueError('shadow state capacity exhausted')
        fd,temporary=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            if immutable:
                try:os.link(temporary,path)
                except FileExistsError:
                    if _read(path,16*1024**2)!=value:raise ValueError('immutable shadow object differs')
            else:os.replace(temporary,path)
            directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            try:os.unlink(temporary)
            except FileNotFoundError:pass

    def install_model(self,model,*,fitted_at):
        validate_artifact(model);fitted_at=utc(fitted_at)
        if instant(model['cutoff'])>fitted_at:raise ValueError('fitting completed before source cutoff')
        value=dict(schema='earthship-weather-shadow-model-receipt/v1',model=model,fitted_at=fitted_at.isoformat())
        name=identity(value)
        self._write(self.root/'models'/(name+'.json'),value,immutable=True)
        self._write(self.root/'current-model.json',dict(receipt_sha256=name))

    def current_model(self):
        path=self.root/'current-model.json'
        if not path.exists():return None
        pointer=_read(path,1024)
        if not isinstance(pointer,dict) or set(pointer)!={'receipt_sha256'}:raise ValueError('closed model pointer required')
        name=digest(pointer['receipt_sha256']);value=_read(self.root/'models'/(name+'.json'),16*1024**2)
        if identity(value)!=name or set(value)!={'schema','model','fitted_at'} or value['schema']!='earthship-weather-shadow-model-receipt/v1':raise ValueError('model receipt differs')
        validate_artifact(value['model'])
        if instant(value['model']['cutoff'])>instant(value['fitted_at']):raise ValueError('model receipt clocks invalid')
        return value

    def retain_issue(self,payload,*,sensor_epoch,code_revision,incumbent_original=None):
        from weather_temperature_evidence import sensor_epoch_id
        validate_payload(payload)
        if payload['status']!='READY':raise ValueError('only a real shadow forecast can become an issue')
        epoch=sensor_epoch_id(sensor_epoch)
        if not isinstance(code_revision,str) or not re.fullmatch('[0-9a-f]{40}',code_revision):raise ValueError('immutable serving revision required')
        if (payload['incumbent'] is None)!=(incumbent_original is None) or (incumbent_original is not None and identity(incumbent_original)!=payload['incumbent']['sourceSha256']):raise ValueError('retained incumbent control differs')
        value=dict(schema='earthship-weather-shadow-issue/v1',sensor_epoch=epoch,code_revision=code_revision,payload=payload,incumbent_original=incumbent_original)
        name=identity(value);self._write(self.root/'issues'/(name+'.json'),value,immutable=True)
        day=instant(payload['decisionAt']).astimezone(ZoneInfo(payload['source']['timezone'])).date().isoformat()
        with self._connect() as db:db.execute('INSERT OR IGNORE INTO issues VALUES(?,?,?,?,?)',(name,payload['decisionAt'],payload['generatedAt'],day,epoch))
        return name

    def training_issues(self,start,end,*,sensor_epoch):
        start,end=map(utc,(start,end))
        if not start<end or end-start>timedelta(days=366):raise ValueError('bounded training issue range required')
        with self._connect() as db:
            # Rank before the rolling lower bound so a partial oldest date
            # cannot substitute a later issue. A 366-day interval can touch 367
            # local dates; retain the latest 366 original daily decisions.
            rows=db.execute('SELECT digest FROM (SELECT digest,issued FROM (SELECT digest,issued,ROW_NUMBER() OVER (PARTITION BY local_day ORDER BY issued,digest) AS n FROM issues WHERE issued<? AND completed<=? AND epoch=?) WHERE n=1 AND issued>=? ORDER BY issued DESC LIMIT 366) ORDER BY issued',
                (end.isoformat(),end.isoformat(),sensor_epoch,start.isoformat())).fetchall()
        result=[]
        for (name,) in rows:
            digest(name);value=_read(self.root/'issues'/(name+'.json'),256*1024)
            if identity(value)!=name or not isinstance(value,dict) or set(value)!={'schema','sensor_epoch','code_revision','payload','incumbent_original'} or value['schema']!='earthship-weather-shadow-issue/v1' or value['sensor_epoch']!=sensor_epoch:
                raise ValueError('original shadow issue differs')
            payload=validate_payload(value['payload'])
            if not start<=instant(payload['decisionAt'])<end or instant(payload['generatedAt'])>end:raise ValueError('issue index clocks differ')
            result.append(value)
        return result


def reconstruct_targets(snapshot,issued_at,site):
    if snapshot.get('site')!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):raise ValueError('authoritative source site differs')
    return temperature_targets(snapshot,issued_at=issued_at)


def empty_model_summary(status='UNTRAINED'):
    return dict(status=status,sha256=None,fittedAt=None,trainingEnd=None,sampleCount=0,targetDates=0,validation=None)


def shadow_once(archive,state,*,now,site,sensor_epoch,code_revision,horizon=336,clock=lambda:datetime.now(timezone.utc),put_state=None,incumbent=None):
    now=utc(now)
    if type(horizon) is not int or not 1<=horizon<=336:raise ValueError('bounded shadow horizon required')
    with collector_lock(state.root/'shadow.lock'):
        end=now+timedelta(hours=horizon)
        end=end.replace(minute=0,second=0,microsecond=0)+(timedelta(hours=1) if end.minute or end.second or end.microsecond else timedelta())
        snapshot=archive.eligible_snapshot(now,end,required_variables={'station_head_temperature_2m'})
        source=None;hours=[];model=empty_model_summary();status='UNAVAILABLE';reason='NO_ELIGIBLE_SOURCE';inc_meta=None;inc_values={};inc_original=None
        if snapshot is not None:
            targets=[target for target in reconstruct_targets(snapshot,now,site) if target.target_at<=end]
            source=dict(snapshotSha256=snapshot['snapshot_sha256'],runId=snapshot['run_id'],initializedAt=snapshot['initialized_at'],firstSeenAt=snapshot['first_seen_at'],ingestedAt=snapshot['ingestion_completed_at'],timezone=site.timezone)
            predictor=None;status='READY';reason='UNTRAINED'
            try:
                receipt=state.current_model()
                if receipt is not None and receipt['model']['sample_count']:
                    if instant(receipt['fitted_at'])>now:raise ValueError('model receipt is after issue')
                    predictor=TemperaturePredictor(receipt['model'])
                    for target in targets:predictor.predict(target,sensor_epoch=sensor_epoch)
                    fitted=receipt['model'];model=dict(status='SHADOW_ONLY',sha256=fitted['artifact_sha256'],fittedAt=receipt['fitted_at'],trainingEnd=fitted['training_end'],sampleCount=fitted['sample_count'],targetDates=fitted['target_dates'],validation=None);reason='NONE'
            except (ValueError,OSError,KeyError,TypeError):model=empty_model_summary('UNAVAILABLE');predictor=None;reason='MODEL_UNAVAILABLE'
            if incumbent is not None:
                inc_meta,inc_values,inc_original=incumbent
            for target in targets:
                hours.append(dict(at=target.target_at.isoformat(),rawC=target.mean_c,localC=None if predictor is None else predictor.predict(target,sensor_epoch=sensor_epoch)['value_c'],incumbentC=inc_values.get(target.target_at)))
        payload=seal_payload(dict(version=1,schema='earthship-weather-provider-shadow/v1',provider='weathernext3',mode='shadow',generatedAt=utc(clock()).isoformat(),decisionAt=now.isoformat(),status=status,reason=reason,source=source,model=model,incumbent=inc_meta,hours=hours,automaticActuation=False))
        if status=='READY':state.retain_issue(payload,sensor_epoch=sensor_epoch,code_revision=code_revision,incumbent_original=inc_original)
        if put_state is not None:publish_bundle(payload,put_state)
        return payload


def train_once(archive,state,*,reader,site,sensor_epoch,cutoff,code_revision,apply=False,days=90,algorithm='bias',clock=lambda:datetime.now(timezone.utc)):
    cutoff=utc(cutoff)
    if type(apply) is not bool or type(days) is not int or not 1<=days<=366 or algorithm not in ('bias','residual'):raise ValueError('bounded explicit shadow fitting required')
    with collector_lock(state.root/'train.lock'):
        issues=state.training_issues(cutoff-timedelta(days=days),cutoff,sensor_epoch=sensor_epoch)
        selected=[]
        for issue in issues:
            payload=issue['payload'];snapshot=archive.read(payload['source']['snapshotSha256'])
            targets=reconstruct_targets(snapshot,instant(payload['decisionAt']),site)
            first=targets[0].target_at if targets else cutoff
            retained={instant(row['at']) for row in payload['hours']}
            selected.extend(target for target in targets if target.target_at in retained and target.target_at<=cutoff and int((target.target_at-first).total_seconds()/3600)+1 in TRAIN_OFFSETS)
        metadata=reader(sorted({target.target_at for target in selected}),cutoff) if selected else {}
        pairs=[];withheld=0
        for target in selected:
            row=metadata.get(target.target_at)
            if row is None:withheld+=1;continue
            outcome=local_temperature_outcome(row,target_at=target.target_at,assessed_at=cutoff,sensor_epoch=sensor_epoch)
            pairs.append(training_pair(target,outcome))
        result=dict(status='NO_ELIGIBLE_PAIRS',selected_issues=len(issues),pairs=len(pairs),withheld=withheld,applied=False,automatic_actuation=False)
        if pairs:
            fit=fit_bias if algorithm=='bias' else fit_residual
            model=fit(pairs,cutoff=cutoff,code_revision=code_revision)
            if apply:state.install_model(model,fitted_at=utc(clock()))
            result.update(status='CANDIDATE_FITTED',model_sha256=model['artifact_sha256'],applied=apply)
        return result
