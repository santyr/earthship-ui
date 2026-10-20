"""Bounded durable scoring work derived only from retained original issues.

The append cursor selects the first retained decision per local date, and the
predeclared TRAIN_OFFSETS population intersects actual issued rows. Report
lookback never controls this queue. Missing evidence produces dependencies,
never reconstructed forecasts, zero outcomes or an eligibility claim.
"""
from contextlib import contextmanager
from datetime import timedelta
import json,os,pathlib,shutil,sqlite3,stat

from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .shadow import TRAIN_OFFSETS,reconstruct_targets,_directory

ARRIVAL_ALLOWANCE=timedelta(days=7)
RETRY_DELAY=timedelta(hours=1)
MATURITY_DELAY=timedelta(minutes=2)


class PendingScores:
    def __init__(self,state,*,sensor_epoch,observation_policy_sha256,evaluation_version,evaluation_contract_sha256,db_path=None):
        from weather_temperature_evidence import sensor_epoch_id
        self.state=state;self.epoch=sensor_epoch_id(sensor_epoch)
        self.policy=digest(observation_policy_sha256);self.contract=digest(evaluation_contract_sha256)
        if not isinstance(evaluation_version,str) or not 1<=len(evaluation_version)<=128:raise ValueError('bounded evaluation version required')
        self.version=evaluation_version
        self.scope=identity(dict(sensor_epoch=self.epoch,observation_policy_sha256=self.policy,evaluation_version=self.version,evaluation_contract_sha256=self.contract))
        self.db=state.root/'pending-scores.sqlite3' if db_path is None else pathlib.Path(db_path)
        if not self.db.is_absolute() or self.db.parent.resolve()!=self.db.parent or not self.db.is_relative_to(state.root):raise ValueError('scoring index must remain within private shadow state')
        _directory(self.db.parent)
        fd=os.open(self.db,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('private owned scoring index required')
        finally:os.close(fd)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS cursors (scope TEXT PRIMARY KEY, source TEXT NOT NULL, sequence INTEGER NOT NULL, anchor TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS intake (scope TEXT, issue TEXT, state TEXT NOT NULL, retry TEXT NOT NULL, reason TEXT, PRIMARY KEY(scope,issue))')
            db.execute('CREATE INDEX IF NOT EXISTS intake_ready ON intake(scope,state,retry)')
            db.execute('CREATE TABLE IF NOT EXISTS daily_selection (scope TEXT, local_day TEXT, issue TEXT NOT NULL, PRIMARY KEY(scope,local_day))')
            db.execute('CREATE TABLE IF NOT EXISTS selection_changes (key TEXT PRIMARY KEY, scope TEXT, detected TEXT, event TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS work (scope TEXT, key TEXT PRIMARY KEY, issue TEXT NOT NULL, target TEXT NOT NULL, descriptor TEXT NOT NULL, state TEXT NOT NULL, retry TEXT NOT NULL, expires TEXT NOT NULL, reason TEXT, score TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS work_ready ON work(scope,state,retry,target)')
            db.execute('CREATE INDEX IF NOT EXISTS work_scores ON work(scope,state,target)')
            db.execute('CREATE INDEX IF NOT EXISTS work_window ON work(scope,target,issue)')

    @contextmanager
    def _connect(self):
        if shutil.disk_usage(self.state.root).free<32*1024**2:raise ValueError('scoring index disk headroom exhausted')
        db=sqlite3.connect(self.db,timeout=2,uri=True)
        try:
            db.execute('PRAGMA cache_size=-2048');db.execute('PRAGMA max_page_count=131072')
            db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        finally:db.close()

    def _descriptor(self,original,target):
        body=dict(evaluation_version=self.version,evaluation_contract_sha256=self.contract,
            issue_sha256=identity(original),target_at=target.target_at.isoformat(),
            observation_policy_sha256=self.policy,source_grid=target.grid_digest,sensor_epoch=self.epoch)
        return dict(body,work_key=identity(body),kind='temperature')

    def _selected(self,original,archive,site):
        payload=original['payload']
        if original['sensor_epoch']!=self.epoch:raise ValueError('original sensor epoch differs')
        targets=reconstruct_targets(archive.read(payload['source']['snapshotSha256']),instant(payload['decisionAt']),site)
        first=min(t.target_at for t in targets)
        by_at={t.target_at:t for t in targets};result=[]
        for row in payload['hours']:
            at=instant(row['at']);target=by_at.get(at)
            if target is None or row['rawC']!=target.mean_c:raise ValueError('original raw source differs')
            offset=(at-first).total_seconds()/3600+1
            if offset in TRAIN_OFFSETS:result.append((self._descriptor(original,target),target,row))
        return result

    def bootstrap(self,archive,*,site,now,limit=16,guard=lambda:None):
        """Advance at most 16 index rows and resolve at most 16 dependencies.

        All index rows advance the cursor, including other sensor epochs. A
        missing original is retried independently and cannot stall discovery.
        The source inode and exact last row anchor detect index replacement or
        rowid reset; rebootstrap is idempotent and does not delete scored work.
        """
        now=utc(now)
        if type(limit) is not int or not 1<=limit<=16:raise ValueError('bounded issue bootstrap required')
        source=self.state.issue_index_identity()
        with self._connect() as db:
            cursor=db.execute('SELECT source,sequence,anchor FROM cursors WHERE scope=?',(self.scope,)).fetchone()
            after=cursor[1] if cursor and cursor[0]==source and self.state.issue_index_anchor(cursor[1],cursor[2]) else 0
            rows=self.state.issue_index_page(after,limit=limit)
            for row in rows:
                if row['epoch']==self.epoch and self.state.first_daily_issue(row['digest']):
                    previous=db.execute('SELECT issue FROM daily_selection WHERE scope=? AND local_day=?',(self.scope,row['local_day'])).fetchone()
                    if previous is not None and previous[0]!=row['digest']:
                        event=dict(local_day=row['local_day'],previous_issue_sha256=previous[0],current_issue_sha256=row['digest'],detected_at=now.isoformat())
                        event_key=identity(dict(scope=self.scope,local_day=row['local_day'],previous=previous[0],current=row['digest']))
                        db.execute('INSERT OR IGNORE INTO selection_changes VALUES(?,?,?,?)',(event_key,self.scope,now.isoformat(),canonical(event).decode()))
                        db.execute("UPDATE work SET state=CASE WHEN score IS NULL THEN 'superseded' ELSE 'superseded_completed' END,reason='earlier_original_retained' WHERE scope=? AND issue=?",(self.scope,previous[0]))
                        db.execute("UPDATE intake SET state='superseded',reason='earlier_original_retained' WHERE scope=? AND issue=?",(self.scope,previous[0]))
                    db.execute('INSERT OR REPLACE INTO daily_selection VALUES(?,?,?)',(self.scope,row['local_day'],row['digest']))
                    db.execute('INSERT OR IGNORE INTO intake VALUES(?,?,?,?,?)',(self.scope,row['digest'],'pending',now.isoformat(),None))
            last=rows[-1] if rows else None
            db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?,?,?)',(self.scope,source,last['sequence'] if last else after,last['digest'] if last else (cursor[2] if after else None)))
            pending=db.execute("SELECT issue FROM intake WHERE scope=? AND state IN ('pending','missing_original','invalid_original') AND retry<=? ORDER BY retry,issue LIMIT ?",(self.scope,now.isoformat(),limit)).fetchall()
        resolved=dependencies=0
        for (name,) in pending:
            guard()
            try:
                if not self.state.first_daily_issue(name):
                    with self._connect() as db:db.execute("UPDATE intake SET state='superseded' WHERE scope=? AND issue=?",(self.scope,name))
                    continue
                original=self.state.read_issue(name)
                if instant(original['payload']['generatedAt'])>now:
                    with self._connect() as db:db.execute('UPDATE intake SET retry=? WHERE scope=? AND issue=?',(instant(original['payload']['generatedAt']).isoformat(),self.scope,name))
                    continue
                selected=self._selected(original,archive,site)
            except FileNotFoundError:status='missing_original'
            except (ValueError,KeyError,TypeError):status='invalid_original'
            else:
                with self._connect() as db:
                    for descriptor,target,row in selected:
                        ready=target.target_at+MATURITY_DELAY
                        db.execute('INSERT OR IGNORE INTO work VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (self.scope,descriptor['work_key'],name,descriptor['target_at'],canonical(descriptor).decode(),'pending',ready.isoformat(),(target.target_at+ARRIVAL_ALLOWANCE).isoformat(),None,None))
                    db.execute("UPDATE intake SET state='selected',reason=NULL WHERE scope=? AND issue=?",(self.scope,name))
                resolved+=1;continue
            with self._connect() as db:db.execute('UPDATE intake SET state=?,retry=?,reason=? WHERE scope=? AND issue=?',
                (status,(now+RETRY_DELAY).isoformat(),status,self.scope,name))
            dependencies+=1
        return dict(indexed=len(rows),resolved=resolved,dependencies=dependencies)

    def due(self,now,*,limit=64):
        now=utc(now)
        if type(limit) is not int or not 1<=limit<=64:raise ValueError('bounded due target batch required')
        with self._connect() as db:
            rows=db.execute("SELECT descriptor FROM work WHERE scope=? AND state='pending' AND retry<=? ORDER BY retry,target,key LIMIT ?",(self.scope,now.isoformat(),limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def load(self,work,archive,*,site):
        self._check_work(work)
        original=self.state.read_issue(work['issue_sha256'])
        if not self.state.first_daily_issue(work['issue_sha256']):raise ValueError('daily original superseded')
        for descriptor,target,row in self._selected(original,archive,site):
            if descriptor==work:return original,target,row
        raise ValueError('work does not match selected original target')

    def _check_work(self,work):
        if not isinstance(work,dict) or work.get('evaluation_contract_sha256')!=self.contract or work.get('observation_policy_sha256')!=self.policy or work.get('evaluation_version')!=self.version or work.get('sensor_epoch')!=self.epoch:raise ValueError('scoring work scope differs')
        with self._connect() as db:row=db.execute('SELECT descriptor FROM work WHERE scope=? AND key=?',(self.scope,work.get('work_key'))).fetchone()
        if row is None or json.loads(row[0])!=work:raise ValueError('unknown scoring work')

    def commit(self,work,score,*,validator):
        self._check_work(work);validator(score)
        if not isinstance(score,dict) or score.get('evaluation_key')!=work['work_key']:raise ValueError('score evaluation identity differs')
        raw=canonical(score).decode()
        if len(raw.encode())>64*1024:raise ValueError('bounded score record required')
        with self._connect() as db:
            previous=db.execute('SELECT score FROM work WHERE key=?',(work['work_key'],)).fetchone()[0]
            if previous is not None:
                if previous!=raw:raise ValueError('immutable evaluation score differs')
                return
            state='completed' if self.state.first_daily_issue(work['issue_sha256']) else 'superseded_completed'
            db.execute('UPDATE work SET score=?,state=?,reason=NULL WHERE key=?',(raw,state,work['work_key']))

    def defer(self,work,*,reason,now):
        self._check_work(work);now=utc(now)
        if reason not in ('quality_withheld','observation_missing','missing_original','invalid_original'):raise ValueError('explicit missing scoring dependency required')
        expires=instant(work['target_at'])+ARRIVAL_ALLOWANCE
        with self._connect() as db:db.execute("UPDATE work SET state=?,reason=?,retry=? WHERE key=? AND state='pending'",
            ('expired' if now>=expires else 'pending',reason,(now+RETRY_DELAY).isoformat(),work['work_key']))

    def iter_scores(self,start,end):
        start,end=utc(start),utc(end)
        if not start<end or end-start>timedelta(days=366):raise ValueError('bounded target display window required')
        # Keyset pagination bounds memory even when report support grows.
        after=''
        while True:
            with self._connect() as db:rows=db.execute("SELECT key,score,issue FROM work WHERE scope=? AND state='completed' AND target>=? AND target<? AND key>? ORDER BY key LIMIT 64",
                (self.scope,start.isoformat(),end.isoformat(),after)).fetchall()
            if not rows:return
            # Recheck the authoritative population, even if the append cursor has
            # not yet reached a newly retained earlier same-day original.
            daily={name:self.state.first_daily_issue(name) for name in {row[2] for row in rows}}
            for key,raw,name in rows:
                if daily[name]:yield json.loads(raw)
            after=rows[-1][0]

    def read_score(self,key):
        """Read retained historical results even after population supersession."""
        with self._connect() as db:row=db.execute('SELECT score FROM work WHERE scope=? AND key=?',(self.scope,digest(key))).fetchone()
        return None if row is None or row[0] is None else json.loads(row[0])

    def counts(self):
        with self._connect() as db:
            result=dict(db.execute('SELECT state,COUNT(*) FROM work WHERE scope=? GROUP BY state',(self.scope,)))
            intake=dict(db.execute('SELECT state,COUNT(*) FROM intake WHERE scope=? GROUP BY state',(self.scope,)))
            reasons=dict(db.execute("SELECT reason,COUNT(*) FROM work WHERE scope=? AND state IN ('pending','expired') AND reason IS NOT NULL GROUP BY reason",(self.scope,)))
        result['issues']=sum(intake.values())
        result['work_dependency_reasons']=reasons
        for name in ('missing_original','invalid_original'):result[name]=intake.get(name,0)
        return result

    def window_counts(self,start,end,*,now):
        """Count discovered canonical forecast instances in a target window.

        `eligible` means a real original/snapshot/native row passed enqueue
        validation; it does not claim an observation is available. Maturity,
        durable state and withheld reasons are separate, overlapping dimensions.
        Unknown originals cannot supply target rows or a complete denominator.
        SQLite aggregates and the source daily index avoid loading score bodies
        or scanning arbitrary files. Source-index attachment is read-only.
        """
        start,end,now=utc(start),utc(end),utc(now)
        if not start<end or end-start>timedelta(days=366):raise ValueError('bounded target coverage window required')
        mature=(now-MATURITY_DELAY).isoformat();clock=now.isoformat()
        source=self.state.issue_index_identity()
        columns=('sampled_issued','unique_target_times','eligible','matured','not_yet_mature','scored','pending','expired',
            'quality_withheld','observation_missing','missing_source_evidence','due')
        with self._connect() as db:
            db.execute('ATTACH DATABASE ? AS originals',(self.state.db.as_uri()+'?mode=ro',))
            db.execute('BEGIN')
            # NOT EXISTS uses issues_daily(epoch,local_day,issued,digest), the
            # exact same canonical first-original ordering as source selection.
            row=db.execute("""WITH canonical_work AS (
                SELECT w.* FROM work w JOIN originals.issues i ON i.digest=w.issue
                WHERE w.scope=? AND w.target>=? AND w.target<? AND i.epoch=?
                AND NOT EXISTS (SELECT 1 FROM originals.issues earlier
                    WHERE earlier.epoch=i.epoch AND earlier.local_day=i.local_day
                    AND (earlier.issued<i.issued OR (earlier.issued=i.issued AND earlier.digest<i.digest))))
                SELECT COUNT(*),COUNT(DISTINCT target),COUNT(*),
                    COALESCE(SUM(target<=?),0),COALESCE(SUM(target>?),0),
                    COALESCE(SUM(state='completed' AND score IS NOT NULL),0),
                    COALESCE(SUM(state='pending'),0),COALESCE(SUM(state='expired'),0),
                    COALESCE(SUM(score IS NULL AND reason='quality_withheld'),0),
                    COALESCE(SUM(score IS NULL AND reason='observation_missing'),0),
                    COALESCE(SUM(score IS NULL AND reason IN ('missing_original','invalid_original')),0),
                    COALESCE(SUM(state='pending' AND target<=? AND retry<=?),0)
                FROM canonical_work""",(self.scope,start.isoformat(),end.isoformat(),self.epoch,mature,mature,mature,clock)).fetchone()
            intake=dict(db.execute('SELECT state,COUNT(*) FROM intake WHERE scope=? GROUP BY state',(self.scope,)))
            cursor=db.execute('SELECT source,sequence,anchor FROM cursors WHERE scope=?',(self.scope,)).fetchone()
            valid_cursor=False
            if cursor and cursor[0]==source:
                anchor=db.execute('SELECT digest FROM originals.issues WHERE rowid=?',(cursor[1],)).fetchone()
                valid_cursor=(cursor[1]==0 and cursor[2] is None) or anchor==(cursor[2],)
            after=cursor[1] if valid_cursor else 0
            remaining=db.execute('SELECT COUNT(*) FROM originals.issues WHERE rowid>?',(after,)).fetchone()[0]
        return dict(zip(columns,row))|dict(
            count_basis='discovered_canonical_sampled_issue_target_forecast_instances',
            eligible_basis='retained_original_snapshot_and_native_row_validated_at_enqueue',
            reason_counts='unscored_last_attempt_reasons_overlap_pending_or_expired_state',
            start=start.isoformat(),end=end.isoformat(),assessed_at=clock,
            complete_population_totals=None,
            discovery=dict(indexed_cursor_caught_up=valid_cursor and remaining==0,
                source_discovery_complete=None,unindexed_issue_files='not_reconciled',
                cursor_status='valid' if valid_cursor else 'not_started' if cursor is None else 'requires_bounded_rebootstrap'),
            global_backlog=dict(unscanned_index_rows=remaining,intake_states=intake,
                target_totals_for_unresolved_originals=None))

    def source_dependencies(self):
        # A file written before the source index transaction is not silently
        # claimed as indexed. Discovery is deliberately index-only: automatic
        # filesystem reconciliation would be a separate recovery operation.
        with self._connect() as db:
            changes=db.execute('SELECT event FROM selection_changes WHERE scope=? ORDER BY detected DESC,key LIMIT 16',(self.scope,)).fetchall()
            count=db.execute('SELECT COUNT(*) FROM selection_changes WHERE scope=?',(self.scope,)).fetchone()[0]
        return dict(unindexed_issue_files='not_reconciled',source='retained_issue_append_index',arrival_allowance_days=7,
            current_population='earliest_retained_original_per_local_issue_date',superseded_scores='retained_excluded_from_current_population',
            selection_change_count=count,selection_changes=[json.loads(row[0]) for row in changes])
