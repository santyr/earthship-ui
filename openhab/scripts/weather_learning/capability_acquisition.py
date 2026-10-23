"""Optional statistics share the core collector's owner and hard budgets.

The original snapshot schema stays unchanged. Each requested profile is a
separate native original, with actual band and request-profile identities.
No automatic eviction, interpolation, account changes or probability claims.
"""
from datetime import timedelta
from pathlib import Path
import os,tempfile
from household_job_budget import AdmissionDeferred
from .capabilities import PROFILES,profile_coverage
from .contracts import canonical,digest,identity,instant
from .features import prospective_snapshot
from .transport import AccessRefused,BoundedTransport

class Backoff:
    def __init__(self,root):
        self.path=Path(root)/'.capability-backoff.json'
        self.value=dict(schema='earthship-capability-backoff/v1',entries={},quota_failures=0,quota_retry_at=None)
        if self.path.exists():
            from .shadow import _read
            self.value=_read(self.path,16384)
        v=self.value
        if (not isinstance(v,dict) or set(v)!={'schema','entries','quota_failures','quota_retry_at'} or
                v['schema']!='earthship-capability-backoff/v1' or not isinstance(v['entries'],dict) or len(v['entries'])>6 or
                type(v['quota_failures']) is not int or not 0<=v['quota_failures']<=3):raise ValueError('bounded optional backoff required')
        if v['quota_retry_at'] is not None:instant(v['quota_retry_at'])
        for key,row in v['entries'].items():
            if not isinstance(row,dict) or set(row)!={'profile','profile_sha256','horizon','initialized_at','attempts','last_at','retry_at','status','reason'}:
                raise ValueError('closed optional retry state required')
            p=PROFILES[row['profile']]
            if key!=p.name+':'+str(row['horizon']) or not p.remote_allowed or not p.optional or row['horizon'] not in p.horizons:
                raise ValueError('declared optional retry identity required')
            digest(row['profile_sha256'])
            for field in ('initialized_at','last_at','retry_at'):instant(row[field])
            if type(row['attempts']) is not int or not 1<=row['attempts']<=2:raise ValueError('bounded optional attempts required')
            if row['status'] not in ('collected','unavailable','rejected','deferred') or row['reason'] not in ('new_original','partial_delivery','invalid_optional_source','quota_restriction','provider_unavailable','shared_budget'):
                raise ValueError('known optional retry outcome required')

    def previous(self,p,horizon):return self.value['entries'].get(p.name+':'+str(horizon))
    def refusal(self,p,run,horizon,now):
        quota=self.value['quota_retry_at']
        if quota is not None and now<instant(quota):return 'quota_backoff',quota
        old=self.previous(p,horizon)
        if old is None or old['profile_sha256']!=p.signature:return None,None
        init=instant(run['start_time']);prior=instant(old['initialized_at'])
        if init<prior:return 'source_regressed',None
        if init>prior:return None,None
        if old['attempts']>=p.attempts:return 'attempt_limit',None
        if now<instant(old['retry_at']):return 'retry_backoff',old['retry_at']
        return None,None

    def record(self,p,run,horizon,now,status,reason):
        # These explicit alternative profiles share two mutable retry slots. Preserve
        # unrelated cooldowns and global quota state; no forecast originals are pruned.
        family={'uncertainty-v1','uncertainty-complete-v1'}
        if p.name in family:
            self.value['entries']={k:v for k,v in self.value['entries'].items() if v['profile'] not in family-{p.name}}
        old=self.previous(p,horizon)
        attempts=old['attempts'] if old and old['profile_sha256']==p.signature and instant(old['initialized_at'])==instant(run['start_time']) else 0
        if reason=='quota_restriction':
            v=self.value;v['quota_failures']=min(3,v['quota_failures']+1)
            v['quota_retry_at']=(now+timedelta(hours=(1,6,24)[v['quota_failures']-1])).isoformat()
        elif status=='collected':self.value.update(quota_failures=0,quota_retry_at=None)
        retry=self.value['quota_retry_at'] if reason=='quota_restriction' else (now+timedelta(minutes=15)).isoformat()
        self.value['entries'][p.name+':'+str(horizon)]=dict(profile=p.name,profile_sha256=p.signature,horizon=horizon,
            initialized_at=instant(run['start_time']).isoformat(),attempts=min(p.attempts,attempts+1),last_at=now.isoformat(),
            retry_at=retry,status=status,reason=reason)
        self.write()
        return retry

    def write(self):
        raw=canonical(self.value)
        if len(raw)>16384:raise ValueError('bounded optional retry state required')
        fd,temporary=tempfile.mkstemp(prefix='.profile-retry-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
            os.replace(temporary,self.path)
            directory=os.open(self.path.parent,os.O_DIRECTORY|os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            try:os.unlink(temporary)
            except FileNotFoundError:pass

def _budget_reason(transport):
    if not isinstance(transport,BoundedTransport):return 'unverified_transport'
    if transport.policy.max_bytes>8*1024**2 or transport.policy.max_seconds>75 or transport.policy.max_attempts>2:return 'unsupported_budget'
    if transport.requests>=32:return 'request_budget'
    if transport.bytes_received>=transport.policy.max_bytes:return 'transfer_budget'
    if transport.clock()-transport.started>=transport.policy.max_seconds:return 'deadline_budget'
    return None

def collect_profiles(reader,archive,*,runs,profiles,clock,retain,capacity):
    transport=getattr(reader,'transport',None);groups=[];shared_stop=None
    try:backoff=Backoff(archive.root)
    except (OSError,ValueError,KeyError,TypeError):backoff=None
    def cache_guard():
        if not isinstance(transport,BoundedTransport):raise AccessRefused('unverified cache deadline')
        if transport.clock()-transport.started>=min(75,transport.policy.max_seconds):raise AccessRefused('optional cache deadline exhausted')
    for p in profiles:
        applicable=[(run,horizon) for run,horizon in runs if horizon in p.horizons]
        if not applicable:
            groups.append(dict(profile=p.name,profile_sha256=p.signature,horizon=runs[0][1],status='deferred',reason='full_run_only',
                normalized=False,consumed=False,snapshot_sha256=None,declared_consumer=p.consumer,retry_at=None))
            continue
        for run,horizon in applicable:
            now=clock();initialized=instant(run['start_time'])
            item=dict(profile=p.name,profile_sha256=p.signature,horizon=horizon,initialized_at=initialized.isoformat(),
                snapshot_sha256=None,status='deferred',reason=None,normalized=False,consumed=False,
                declared_consumer=p.consumer,retry_at=None)
            groups.append(item)
            try:
                # Cache reuse needs no transfer headroom or new availability.
                cache_guard()
                cached=archive.completed_profile(run['start_time'],capability=p,horizon=horizon,as_of=now,site=reader.site,guard=cache_guard)
                if cached is not None:
                    item.update(status='cached',reason='exact_original_profile',normalized=True,snapshot_sha256=cached['snapshot_sha256'],
                        available_at=cached['ingestion_completed_at'],actual_band_signature=_actual_bands(cached));continue
                if now>=initialized+timedelta(hours=24):item['reason']='source_expired';continue
                if backoff is None:item['reason']='backoff_state_invalid';continue
                if shared_stop is not None:item['reason']=shared_stop;continue
                item['reason']=_budget_reason(transport)
                if item['reason'] is not None:shared_stop=item['reason'];continue
                refused,retry=backoff.refusal(p,run,horizon,now)
                if refused is not None:item.update(reason=refused,retry_at=retry);continue
                room=capacity()
                if (room['objects']>=room['object_limit'] or room['remaining_bytes']<8*1024**2 or room['free_bytes']<16*1024**2):
                    item['reason']='archive_capacity';continue
                def validate(value):
                    body=prospective_snapshot(value,issued_at=clock())
                    if body['site']!=dict(latitude=reader.site.latitude,longitude=reader.site.longitude,timezone=reader.site.timezone):
                        raise ValueError('optional authoritative site differs')
                    actual={('station' if s['collection'].endswith('0p05deg') else 'gridded'):tuple(s['payload']['region'][0][4:]) for s in body['source_originals']}
                    if not actual or any(grid not in p.bands_by_grid or bands!=p.bands_by_grid[grid] for grid,bands in actual.items()):
                        raise ValueError('fetched optional bands differ from request')
                    if len(body['points'])>len(p.bands)*horizon:raise ValueError('optional point budget exceeded')
                try:
                    value,name=retain(run,horizon,selected_bands=p.bands_by_grid,use_cache=False,validate_fetched=validate,allow_partial=True)
                    coverage=profile_coverage(value,p,decision=clock(),horizon=horizon);complete=coverage['status']=='complete'
                    status,reason=('collected','new_original') if complete else ('unavailable','partial_delivery')
                    item.update(status=status,reason=reason,normalized=True,snapshot_sha256=name,
                        available_at=value['ingestion_completed_at'],actual_band_signature=_actual_bands(value),missing_bands=coverage['missing_bands'])
                    if not complete:
                        trace=transport.trace[-1:]
                        quota=bool(trace and (trace[0]['status']==429 or trace[0].get('error_status')=='RESOURCE_EXHAUSTED'))
                        if quota:item.update(status='deferred',reason='quota_restriction');shared_stop='quota_restriction'
                        elif _budget_reason(transport):item.update(status='deferred',reason='shared_budget')
                except (TimeoutError,AdmissionDeferred,MemoryError):raise
                except Exception as error:
                    trace=transport.trace[-1:] if isinstance(transport,BoundedTransport) else []
                    quota=bool(trace and (trace[0].get('status')==429 or trace[0].get('error_status')=='RESOURCE_EXHAUSTED'))
                    reason='quota_restriction' if quota else 'shared_budget' if _budget_reason(transport) else 'provider_unavailable' if isinstance(error,(OSError,AccessRefused)) else 'invalid_optional_source'
                    item.update(status='deferred' if quota or reason=='shared_budget' else 'unavailable' if reason=='provider_unavailable' else 'rejected',reason=reason)
                    if quota:shared_stop='quota_restriction'
                item['retry_at']=backoff.record(p,run,horizon,clock(),item['status'],item['reason'])
            except (TimeoutError,AdmissionDeferred,MemoryError):raise
            except AccessRefused:
                item.update(status='deferred',reason=_budget_reason(transport) or 'cache_unavailable')
            except Exception:
                item.update(status='deferred',reason='optional_state_unavailable')
    budget=dict(requests_used=getattr(transport,'requests',None),response_bytes_used=getattr(transport,'bytes_received',None),
        elapsed_seconds=round(transport.clock()-transport.started,3) if isinstance(transport,BoundedTransport) else None,
        maximum_requests=32,maximum_response_bytes=8*1024**2,maximum_seconds=75,
        eecu_remaining=None,paid_access_allowed=False,requester_billing_project=None,full_ensemble_allowed=False)
    return groups,budget

def _actual_bands(value):return identity(sorted((s['collection'],s['payload']['region'][0][4:]) for s in value['source_originals']))
