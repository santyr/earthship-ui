"""Private content-addressed originals and transactional eligibility index."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,os,pathlib,sqlite3,tempfile,stat
from contextlib import contextmanager
from .contracts import canonical,identity,instant,validate_snapshot

class Archive:
    def __init__(self,root):
        self.root=pathlib.Path(root)
        if not self.root.is_absolute():raise ValueError('absolute private archive path required')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_mode&0o077:
            raise ValueError('private archive directory required')
        self.objects=self.root/'objects';self.objects.mkdir(mode=0o700,exist_ok=True)
        self.db=self.root/'index.sqlite3'
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (digest TEXT PRIMARY KEY, initialized TEXT NOT NULL, first_seen TEXT NOT NULL, completed TEXT NOT NULL, historical INTEGER NOT NULL)')
        os.chmod(self.db,0o600)

    @classmethod
    def open_readonly(cls,root,*,allow_missing=False):
        """Open an existing index; an optional absent source stays unavailable."""
        if type(allow_missing) is not bool:raise ValueError('explicit missing-source policy required')
        value=cls.__new__(cls);value.root=pathlib.Path(root)
        if not value.root.is_absolute() or value.root.resolve()!=value.root:
            raise ValueError('resolved private archive required')
        value.objects=value.root/'objects';value.db=value.root/'index.sqlite3';value.readonly=True
        value.missing=False
        try:
            for path,directory in ((value.root,True),(value.objects,True),(value.db,False)):
                info=path.lstat()
                if (info.st_uid!=os.getuid() or info.st_mode&0o077 or
                        not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
                    raise ValueError('owned private read-only archive required')
        except FileNotFoundError:
            if not allow_missing:raise
            value.missing=True
        if not value.missing:
            with value._connect() as db:db.execute('SELECT digest FROM snapshots LIMIT 0')
        return value

    @contextmanager
    def _connect(self):
        readonly=getattr(self,'readonly',False)
        connection=sqlite3.connect(self.db.as_uri()+'?mode=ro' if readonly else self.db,timeout=2,uri=readonly)
        try:
            with connection:yield connection
        finally:connection.close()

    def store_snapshot(self,snapshot):
        if getattr(self,'readonly',False):raise ValueError('read-only archive cannot store snapshots')
        # Validation and canonical copy precede any mutation of archive state.
        raw=canonical(validate_snapshot(snapshot));value=json.loads(raw);name=sha256(raw).hexdigest()
        destination=self.objects/(name+'.json')
        if destination.exists():
            if destination.read_bytes()!=raw:raise ValueError('immutable archive object differs')
        else:
            fd,temporary=tempfile.mkstemp(prefix='.snapshot-',dir=self.objects)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                try:os.link(temporary,destination)
                except FileExistsError:
                    if destination.read_bytes()!=raw:raise ValueError('immutable archive collision')
                directory=os.open(self.objects,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(directory)
                finally:os.close(directory)
            finally:os.unlink(temporary)
        with self._connect() as db:
            db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?)',(name,instant(value['initialized_at']).isoformat(),
                instant(value['first_seen_at']).isoformat(),instant(value['ingestion_completed_at']).isoformat(),int(value['historical'])))
        return name

    def read(self,name):
        from .contracts import digest
        digest(name);path=self.objects/(name+'.json')
        if path.is_symlink() or path.stat().st_size>8*1024*1024:raise ValueError('archive object refused')
        raw=path.read_bytes()
        if sha256(raw).hexdigest()!=name:raise ValueError('archive object digest mismatch')
        value=validate_snapshot(json.loads(raw))
        return value|{'snapshot_sha256':name}

    def completed_run(self,initialized_at,*,horizon,required,as_of):
        """Reuse one complete original run without renewing its availability."""
        initialized=instant(initialized_at);as_of=as_of.astimezone(timezone.utc)
        if type(horizon) is not int or not 1<=horizon<=360 or not required:
            raise ValueError('bounded complete native run required')
        if getattr(self,'missing',False):return None
        with self._connect() as db:
            rows=db.execute('SELECT digest FROM snapshots WHERE historical=0 AND initialized=? AND completed<=? ORDER BY completed,digest LIMIT 256',
                (initialized.isoformat(),as_of.isoformat())).fetchall()
        for (name,) in rows:
            value=self.read(name)
            if instant(value['initialized_at'])!=initialized or instant(value['ingestion_completed_at'])>as_of:
                raise ValueError('original run availability differs from index')
            index={(p['variable'],p['statistic'],instant(p['valid_at'])):p['value'] for p in value['points']}
            if all(index.get((variable,statistic,initialized+timedelta(hours=hour))) is not None
                    for variable,statistic in required for hour in range(1,horizon+1)):
                return value
        return None

    def completed_profile(self,initialized_at,*,capability,horizon,as_of,site,guard=lambda:None):
        """Exact requested statistics, native originals and original availability.

        A mean-only or smaller profile never becomes an expanded cache hit.
        Malformed optional candidates cannot hide another valid original.
        """
        from .capabilities import CapabilityProfile,profile_coverage
        from .config import Site
        if not isinstance(capability,CapabilityProfile) or horizon not in capability.horizons or not isinstance(site,Site):
            raise ValueError('declared capability cache request required')
        initialized=instant(initialized_at);as_of=as_of.astimezone(timezone.utc)
        if getattr(self,'missing',False):return None
        required={tuple(band.rsplit('_',1)) for _,band in capability.bands}
        with self._connect() as db:
            rows=db.execute('SELECT digest FROM snapshots WHERE historical=0 AND initialized=? AND completed<=? ORDER BY completed,digest LIMIT 256',
                (initialized.isoformat(),as_of.isoformat())).fetchall()
        for (name,) in rows:
            guard()
            try:
                value=self.read(name)
                if instant(value['initialized_at'])!=initialized or value['site']!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):continue
                found={(p['variable'],p['statistic']) for p in value['points']}
                if not required<=found:continue
                complete=profile_coverage(value,capability,decision=as_of,horizon=horizon)['status']=='complete'
            except (OSError,ValueError,KeyError,TypeError):continue
            guard()
            if complete:return value
        return None

    def eligible_snapshot(self,decision_at,target_end,*,required_variables=None,max_age=timedelta(hours=24)):
        if any(not isinstance(x,datetime) or x.utcoffset() is None for x in (decision_at,target_end)):
            raise ValueError('aware serving clocks required')
        decision_at=decision_at.astimezone(timezone.utc);target_end=target_end.astimezone(timezone.utc)
        if not decision_at<target_end or not timedelta(0)<max_age<=timedelta(hours=24):raise ValueError('bounded freshness/horizon required')
        if getattr(self,'missing',False):return None
        # Only indexed, completely committed objects may replace a previous issue.
        with self._connect() as db:
            rows=db.execute('SELECT digest FROM snapshots WHERE historical=0 AND first_seen<=? AND completed<=? AND initialized>=? ORDER BY initialized DESC,completed DESC,digest LIMIT 256',
                (decision_at.isoformat(),decision_at.isoformat(),(decision_at-max_age).isoformat())).fetchall()
        for (name,) in rows:
            value=self.read(name);points=value['points']
            variables=required_variables if required_variables is not None else {x['variable'] for x in points}
            if not variables:raise ValueError('nonempty required variable set required')
            ok=True
            for variable in variables:
                available={instant(p['valid_at']) for p in points if p['variable']==variable and p['statistic']=='mean' and p['value'] is not None}
                # Require each hourly target through the requested horizon, with no gap bridging.
                first=(decision_at.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1))
                needed_end=target_end.replace(minute=0,second=0,microsecond=0)
                if needed_end<target_end:needed_end+=timedelta(hours=1)
                at=first
                while at<=needed_end:
                    if at not in available:ok=False;break
                    at+=timedelta(hours=1)
                if not available or target_end>max(available):ok=False
                if not ok:break
            if ok:return value
        return None
