"""Offline assembly of original evidence; no readers, writers or planner."""
from hashlib import sha256
import re
from .adapters import battery_soc, pv_day_counter, native_temperature
from .capabilities import build_registry
from .snapshot import build_snapshot
from .codec import canonical, loads, identity
from .evidence import utc, digest
from datetime import datetime

MAX_BYTES = 1024 * 1024
BUNDLE_FIELDS = {'schema','as_of','created_at','policy','sources'}
SOURCE_FIELDS = {'kind','source_role','source_identity','expected_epoch','expected_sha256','persisted_at','raw'}
POLICY_FIELDS = {'requirements','max_age_seconds','max_skew_seconds'}


def _instant(value):
    if not isinstance(value,str) or not 1 <= len(value) <= 64: raise ValueError('explicit frozen clock required')
    return utc(datetime.fromisoformat(value))


def compile_inputs(bundle, *, managed, ownership, code_revision, runtime_manifest):
    if not isinstance(bundle,dict) or set(bundle)!=BUNDLE_FIELDS or bundle['schema']!='earthship-household-inputs/v1' or len(canonical(bundle))>MAX_BYTES:
        raise ValueError('closed bounded original input bundle required')
    policy=bundle['policy']
    if not isinstance(policy,dict) or set(policy)!=POLICY_FIELDS: raise ValueError('closed original temporal policy required')
    if not isinstance(runtime_manifest,dict) or not 1 <= len(runtime_manifest) <= 128:
        raise ValueError('explicit bounded executing source manifest required')
    for name,sha in runtime_manifest.items():
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_./:-]{1,192}',name) or '..' in name:
            raise ValueError('explicit runtime source name required')
        digest(sha)
    as_of,created_at=map(_instant,(bundle['as_of'],bundle['created_at']))
    sources=bundle['sources']
    if not isinstance(sources,list) or len(sources)>6: raise ValueError('bounded original source collection required')
    observations=[]
    for source in sources:
        if not isinstance(source,dict) or set(source)!=SOURCE_FIELDS: raise ValueError('closed original source context required')
        args={key:source[key] for key in ('raw','source_identity','expected_epoch','expected_sha256')};args['as_of']=as_of
        kind=source['kind'];role=source['source_role']
        if kind=='battery_soc' and role=='battery_soc':
            observation=battery_soc(**args,persisted_at=_instant(source['persisted_at']))
        elif kind=='pv_day_wh' and role=='pv_day_wh':
            observation=pv_day_counter(**args,persisted_at=_instant(source['persisted_at']))
        elif kind=='native_temperature' and source['persisted_at'] is None:
            observation=native_temperature(role=role,**args)
        else: raise ValueError('unsupported original source adapter')
        observations.append(observation)
    snapshot=build_snapshot(observations,as_of=as_of,created_at=created_at,code_revision=code_revision,
                            config_revision=identity(policy),**policy)
    registry=build_registry(managed,ownership)
    record=dict(schema='earthship-household-foundation-receipt/v1',inputs_sha256=identity(bundle),
                runtime_manifest=dict(runtime_manifest),runtime_sha256=identity(runtime_manifest),
                snapshot=snapshot.to_dict(),registry=registry.to_dict(),automatic_actuation=False)
    record=loads(canonical(record));record['receipt_sha256']=identity(record)
    if len(canonical(record))>262144: raise ValueError('bounded sealed receipt required')
    return record


def verify_replay(original, replayed):
    for record in (original,replayed):
        if not isinstance(record,dict) or set(record)!={'schema','inputs_sha256','runtime_manifest','runtime_sha256','snapshot','registry','automatic_actuation','receipt_sha256'} or record['schema']!='earthship-household-foundation-receipt/v1' or record['automatic_actuation'] is not False:
            raise ValueError('closed original sealed receipt required')
        body={key:value for key,value in record.items() if key!='receipt_sha256'}
        if identity(body)!=record['receipt_sha256']: raise ValueError('sealed original receipt digest differs')
    if canonical(original)!=canonical(replayed): raise ValueError('original source, runtime or snapshot replay differs')
    return original['receipt_sha256']
