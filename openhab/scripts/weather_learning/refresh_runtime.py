"""Opt-in source-bound near24 candidates alongside unchanged raw publication.

Candidate cache availability is not a core-Item forecast publication or a skill
qualification. Historical registration never creates a current candidate cache.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import json
from weather_source_files import _read,_write
from .contracts import canonical,identity,instant
from .evidence import utc
from .near_term_correction import prepare_near_term_correction,replay_near_correction
from .refresh_queue import RefreshQueue
from .shadow import ShadowStore


class RefreshRuntime:
    def __init__(self,*,state_root,archive,site,sensor_epoch,selection_path=None,origin_metadata=None,origin_acquired_at=None,
            clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
        self.root=Path(state_root)
        if not self.root.is_absolute() or self.root.resolve()!=self.root:raise ValueError('resolved private near24 state required')
        self.archive=archive;self.site=site;self.epoch=sensor_epoch;self.clock=clock;self.guard=guard
        self.selection=self.root/'historical-outdoor.json' if selection_path is None else Path(selection_path)
        self.origin=origin_metadata;self.acquired=origin_acquired_at

    def prepare(self,decision,provider):
        self.guard()
        record=prepare_near_term_correction(self.archive,decision_at=decision,site=self.site,selection_path=self.selection,
            origin_metadata=self.origin,origin_acquired_at=self.acquired,sensor_epoch=self.epoch)
        original=provider.to_dict();profile=original.get('near_term',original);body=record.to_dict()
        if body['source'] is not None and (profile['source'] is None or body['source']['snapshot_sha256']!=profile['source']['snapshot_sha256']):
            raise ValueError('near24 preparation differs from actual raw publication source')
        return record

    def retain(self,attempt,result,near):
        self.guard();now=utc(self.clock());state=ShadowStore(self.root);queue=RefreshQueue(state)
        if near is not None:replay_near_correction(near,archive=self.archive,site=self.site)
        key=queue.retain(attempt,result,archive=self.archive,site=self.site,near=near,clock=lambda:now)
        if near is None:return 'retained_raw_only'
        body=near.to_dict();decision=instant(body['decision_at'])
        # The compiled historical original remains useful; publishing its newly
        # prepared correction later would invent a current/as-issued product.
        if not decision<=now<=decision+timedelta(seconds=120):return 'retained_historical_only'
        source=body['source']
        expiry=min(decision+timedelta(hours=2),instant(source['initialized_at'])+timedelta(hours=24)) if source else now
        hours=[row for row in body['hours'] if instant(row['at'])>now]
        value=dict(schema='earthship-near24-candidate-cache/v1',profile=body['profile'],status=body['status'],reason=body['reason'],
            decision_at=body['decision_at'],cached_at=now.isoformat(),expires_at=expiry.isoformat(),source=source,model=body['model'],hours=hours,
            prepared_sha256=body['record_sha256'],retained_decision_key=key,issued=False,
            local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
        value['report_sha256']=identity(value)
        def before():
            self.guard();at=utc(self.clock())
            if not now<=at<=decision+timedelta(seconds=120) or at>=expiry or any(instant(row['at'])<=at for row in hours):
                raise ValueError('near24 candidate publication lifetime elapsed')
        raw=canonical(value);_write(self.root,'near-term-correction.json',raw,before_publish=before)
        if _read(self.root/'near-term-correction.json',262144)!=raw:raise ValueError('near24 candidate cache readback differs')
        return 'retained_candidate'


def from_config(path,*,archive,site,clock=lambda:datetime.now(timezone.utc),guard=lambda:None,origin_reader=None):
    """Read one existing native outdoor origin before the actual decision clock."""
    from hourly_temperature_runtime import _native_outdoor_policy,read_db_config
    from weather_temperature_history import fetch_temperature_grid_v2
    value=json.loads(_read(Path(path),16384))
    if (set(value)!={'schema','state','temperature_policy','temperature_db_config','runtime_manifest'} or value['schema']!='earthship-near24-production-profile/v1'):
        raise ValueError('closed explicit near24 production profile required')
    from .production_worker import runtime_manifest
    if value['runtime_manifest']!=runtime_manifest():raise ValueError('exact optional near24 runtime source pins required')
    for key in ('state','temperature_policy','temperature_db_config'):
        p=Path(value[key])
        if not p.is_absolute() or p.resolve()!=p:raise ValueError('resolved private near24 profile paths required')
    guard();policy,epoch=_native_outdoor_policy(value['temperature_policy']);metadata=None;acquired=None
    target=utc(clock())
    try:
        if origin_reader is None:
            import psycopg2
            config=read_db_config(value['temperature_db_config'])
            original=fetch_temperature_grid_v2(lambda:psycopg2.connect(**config,connect_timeout=3),targets=[target],
                assessed_at=target,stream='outdoor',policy=policy,sensor_epoch=epoch)
            metadata=dict(original).get(target)
        else:metadata=origin_reader(target,policy,epoch)
        acquired=utc(clock())
    except Exception:
        metadata=None;acquired=None
    guard()
    return RefreshRuntime(state_root=value['state'],archive=archive,site=site,sensor_epoch=epoch,origin_metadata=metadata,
        origin_acquired_at=acquired,clock=clock,guard=guard)
