"""One immutable source/model identity; retained confidence grants no authority."""
from dataclasses import dataclass
from datetime import timedelta
import re
from .codec import canonical,loads,identity
from .evidence import EvidenceRef,Observation,digest
from .control_contracts import instant
from .snapshot import HouseholdSnapshot
from .power_snapshot import replay_power_snapshot
from .thermal_model import PreparedProjection,project

MAX_SOURCE_BYTES=1024*1024
NATIVE={'air_temperature':'thermal','mass_temperature':'thermal','outdoor_temperature':'weather'}
CONTEXT_FIELDS={'prepared_sha256','artifact_sha256','runtime_sha256','original_capture_sha256','executing_runtime_sha256',
                'issue','available_at','valid_until','confidence','measurements','temporal_policy'}


def describe_thermal(prepared):
    if not isinstance(prepared,PreparedProjection):raise ValueError('prepared original thermal context required')
    value=prepared.to_dict();snap=value['snapshot'];output=project(prepared)['output']
    return dict(prepared_sha256=value['prepared_sha256'],artifact_sha256=value['artifact_sha256'],runtime_sha256=value['runtime_sha256'],
        original_capture_sha256=value['original_capture_sha256'],executing_runtime_sha256=identity(value['executing_runtime']),
        issue=value['issue'],available_at=snap['created_at'],valid_until=(instant(value['issue'])+timedelta(hours=value['horizon_hours'])).isoformat(),
        confidence=output['confidence'],measurements={role:snap['domains'][domain][role] for role,domain in NATIVE.items()},
        temporal_policy=snap['temporal_policy'])


def _context(value):
    if value is None:return None
    if not isinstance(value,dict) or set(value)!=CONTEXT_FIELDS or len(canonical(value))>8192:raise ValueError('closed bounded model descriptor required')
    for name in ('prepared_sha256','artifact_sha256','runtime_sha256','original_capture_sha256','executing_runtime_sha256'):digest(value[name])
    issue,available,until=map(instant,(value['issue'],value['available_at'],value['valid_until']))
    if not issue<=available<until or not timedelta(0)<until-issue<=timedelta(hours=48) or value['confidence']!='low':
        raise ValueError('original provisional availability/confidence required')
    if not isinstance(value['measurements'],dict) or set(value['measurements'])!=set(NATIVE):raise ValueError('three original native measurements required')
    for role,row in value['measurements'].items():
        if not isinstance(row,dict) or set(row)!={'value','unit','reason','evidence'} or row['reason'] is not None:
            raise ValueError('qualified original model measurement required')
        ref=row['evidence']
        if not isinstance(ref,dict) or ref.get('source_role')!=role or value['original_capture_sha256'] not in ref.get('parent_digests',[]):
            raise ValueError('original measurement capture provenance required')
        restored={**ref,'parent_digests':tuple(ref['parent_digests'])}
        for key in ('observed_at','received_at','available_at','valid_until','assessed_at'):
            restored[key]=None if restored[key] is None else instant(restored[key])
        checked=EvidenceRef(**restored);Observation(checked,row['value'],row['unit'])
        if checked.quality!='qualified' or checked.assessed_at!=issue:raise ValueError('original model assessment clock differs')
    policy=value['temporal_policy']
    if not isinstance(policy,dict) or set(policy)!={'requirements','max_age_seconds','max_skew_seconds'} or any(
        type(policy['max_age_seconds'].get(role)) is not int or not 1<=policy['max_age_seconds'][role]<=86400 for role in NATIVE):
        raise ValueError('original model age policy required')
    if type(policy['max_skew_seconds']) is not int or not 0<=policy['max_skew_seconds']<=300:raise ValueError('original model skew required')
    return value


def _metadata(role,context):
    unit='identity' if role=='thermal_artifact_identity' else 'confidence'
    if context is None:return dict(value=None,unit=unit,reason='missing_model_context',evidence=None)
    return dict(value=context['artifact_sha256'] if unit=='identity' else context['confidence'],unit=unit,reason=None,
        evidence=dict(source_role=role,source_identity='retained_original_provisional_thermal',digest=context['prepared_sha256'],
            source_epoch=None,hardware_epoch=None,observed_at=context['issue'],received_at=context['available_at'],
            available_at=context['available_at'],valid_until=context['valid_until'],assessed_at=context['available_at'],
            quality='retained_model_context',reason=None,parent_digests=[context['original_capture_sha256']]))


def _render(source_receipt,context,code_revision):
    if not isinstance(code_revision,str) or not re.fullmatch('[0-9a-f]{40}',code_revision):raise ValueError('model snapshot code revision required')
    original=replay_power_snapshot(source_receipt,runtime_manifest=source_receipt['runtime_manifest'])
    source=original['snapshot'];context=_context(context)
    body=loads(canonical({key:value for key,value in source.items() if key!='snapshot_id'}))
    as_of=instant(source['as_of']);created=instant(source['created_at']);policy=body['temporal_policy']
    if context is not None:
        issue=instant(context['issue'])
        if as_of>issue or created>issue:raise ValueError('later source cannot become an earlier model origin')
        as_of=issue;created=max(created,instant(context['available_at']))
        for role,domain in NATIVE.items():
            body['domains'][domain][role]=loads(canonical(context['measurements'][role]))
            policy['max_age_seconds'][role]=min(policy['max_age_seconds'].get(role,86400),context['temporal_policy']['max_age_seconds'][role])
        policy['max_skew_seconds']=min(policy['max_skew_seconds'],context['temporal_policy']['max_skew_seconds'])
    for role in ('thermal_artifact_identity','thermal_model_confidence'):body['domains']['thermal'][role]=_metadata(role,context)
    rows={role:row for domain in body['domains'].values() for role,row in domain.items()}
    for role,row in rows.items():
        ref=row['evidence']
        if ref is None or ref['quality']!='qualified' or row['reason'] is not None:continue
        observed=instant(ref['observed_at'] or ref['received_at']);reason=None
        if instant(ref['available_at'])>as_of or instant(ref['assessed_at'])>as_of:reason='future_source'
        elif as_of>=instant(ref['valid_until']):reason='expired_source'
        elif as_of-observed>timedelta(seconds=policy['max_age_seconds'][role]):reason='source_too_old'
        if reason is not None:row.update(value=None,reason=reason)
    complete={};reasons={}
    for name,roles in policy['requirements'].items():
        valid=all(rows[role]['value'] is not None and rows[role]['reason'] is None for role in roles);reason=None if valid else 'required_source_unavailable'
        if valid:
            clocks=[instant(rows[role]['evidence']['observed_at'] or rows[role]['evidence']['received_at']) for role in roles]
            if (max(clocks)-min(clocks)).total_seconds()>policy['max_skew_seconds']:valid=False;reason='source_skew'
        complete[name]=valid;reasons[name]=reason
    body.update(schema='earthship-household-snapshot/v3',source_snapshot=source,source_receipt_sha256=source_receipt['receipt_sha256'],
        thermal_context=context,model_context_scope='retained_original_provisional',code_revision=code_revision,
        as_of=as_of.isoformat(),created_at=created.isoformat(),config_revision=identity(policy),completeness=complete,capability_reasons=reasons)
    return body


@dataclass(frozen=True)
class ModelSnapshot(HouseholdSnapshot):
    original_source:bytes

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.original_source,bytes) or len(self.original_source)>MAX_SOURCE_BYTES:raise ValueError('bounded original source receipt required')
        value=loads(self.content)
        if value.get('schema')!='earthship-household-snapshot/v3' or value.get('planner_authority')!='none':raise ValueError('model-bound observational snapshot required')
        rederived=_render(loads(self.original_source),value['thermal_context'],value['code_revision'])
        if canonical(rederived)!=self.content:raise ValueError('original source/model snapshot differs')

    @property
    def source_receipt(self):return loads(self.original_source)


def bind_model_snapshot(*,source_receipt,source_runtime_manifest,thermal_inputs,code_revision):
    source=replay_power_snapshot(source_receipt,runtime_manifest=source_runtime_manifest)
    descriptor=None if thermal_inputs is None else describe_thermal(thermal_inputs)
    return ModelSnapshot(canonical(_render(source,descriptor,code_revision)),canonical(source))


def verify_model_binding(snapshot,thermal_inputs):
    if not isinstance(snapshot,ModelSnapshot):raise ValueError('model-bound snapshot required')
    expected=None if thermal_inputs is None else describe_thermal(thermal_inputs)
    if canonical({'context':snapshot.to_dict()['thermal_context']})!=canonical({'context':expected}):raise ValueError('prepared thermal model binding differs')


def restore_model_snapshot(document,*,source_receipt):
    value=ModelSnapshot(canonical({key:item for key,item in document.items() if key!='snapshot_id'}),canonical(source_receipt))
    if value.snapshot_id!=document['snapshot_id']:raise ValueError('original model snapshot identity differs')
    return value


def restore_snapshot(document,source_contexts=None):
    if document.get('schema')=='earthship-household-snapshot/v3':
        if not isinstance(source_contexts,dict) or document.get('snapshot_id') not in source_contexts:raise ValueError('original source context missing')
        return restore_model_snapshot(document,source_receipt=source_contexts[document['snapshot_id']])
    if document.get('schema')!='earthship-household-snapshot/v1':raise ValueError('unsupported model snapshot version')
    value=HouseholdSnapshot(canonical({key:item for key,item in document.items() if key!='snapshot_id'}))
    if value.snapshot_id!=document['snapshot_id']:raise ValueError('original snapshot identity differs')
    return value


def verify_source_runtime(snapshot,runtime_manifest):
    if not isinstance(snapshot,ModelSnapshot):raise ValueError('original model snapshot required')
    expected=snapshot.source_receipt['runtime_manifest']
    if not isinstance(runtime_manifest,dict) or any(runtime_manifest.get(name)!=sha for name,sha in expected.items()):
        raise ValueError('original source execution runtime differs')
