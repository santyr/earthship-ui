"""Pure future v2 contracts. No transport, durable ledger or live authority."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from .codec import canonical, loads, identity
from .evidence import utc, digest

MAX_BYTES = 2048
MAX_OWNER_AGE_SECONDS = 120
REASON_CATALOG_VERSION = 'earthship-control-reasons/v1'
REASON_CODES = frozenset(('accepted','running','completed','low_soc','cooldown','after_dark','busy',
    'provider_offline','request_stale','request_future','request_expired','request_invalid','schema_unknown',
    'ledger_restore_missing','ledger_readback_failed','restart_uncertain','duplicate','execution_error',
    'outcome_unknown','capability_unavailable','planner_authority_disabled','source_unavailable',
    'source_stale','hard_constraint','intent_conflict','no_optional_action','snapshot_mismatch',
    'intent_invalid','intent_expired','unqualified_effect'))
REQUEST_FIELDS = {'schema','requestId','intentId','intentType','source','requestedAt','expiresAt',
                  'snapshotId','plannerVersion','parameters'}
RESULT_FIELDS = {'schema','requestId','intentId','status','reasonCode','ownerVersion','at','snapshotId'}
SOURCES = frozenset(('ui','schedule','planner','operator','recovery'))
INTENT_TYPES = frozenset(('RUN_GREYWATER_CYCLE','RUN_FEEDER_CYCLE','SET_NIGHT_LOAD_OVERRIDE','SET_NIGHT_LOAD_DEVICE'))
STATUSES = frozenset(('accepted','running','completed','denied','failed'))
FAILURE_REASONS = frozenset(('execution_error','ledger_restore_missing','ledger_readback_failed',
                            'restart_uncertain','provider_offline','outcome_unknown'))


class ContractRefused(ValueError):
    def __init__(self, reason_code):
        if reason_code not in REASON_CODES: raise ValueError('uncatalogued contract refusal')
        self.reason_code=reason_code
        super().__init__(reason_code)


def _id(value):
    return isinstance(value,str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{7,127}',value) is not None


def _version(value):
    return isinstance(value,str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9._:-]{0,79}',value) is not None


def instant(value):
    if not isinstance(value,str) or not 1<=len(value)<=64: raise ContractRefused('request_invalid')
    try:return utc(datetime.fromisoformat(value))
    except (TypeError,ValueError,OverflowError):raise ContractRefused('request_invalid') from None


def _decode(raw,fields,schema):
    if not isinstance(raw,str):raise ContractRefused('request_invalid')
    try:
        if not 1<=len(raw.encode('utf-8'))<=MAX_BYTES:raise ContractRefused('request_invalid')
    except UnicodeError:raise ContractRefused('request_invalid') from None
    try:value=loads(raw)
    except (TypeError,ValueError,RecursionError):raise ContractRefused('request_invalid') from None
    if value.get('schema')!=schema:raise ContractRefused('schema_unknown')
    if set(value)!=fields:raise ContractRefused('request_invalid')
    return value


def validate_parameters(kind, parameters):
    if not isinstance(kind,str) or kind not in INTENT_TYPES or not isinstance(parameters,dict):raise ContractRefused('request_invalid')
    if kind in ('RUN_GREYWATER_CYCLE','RUN_FEEDER_CYCLE'):
        if parameters:raise ContractRefused('request_invalid')
    elif kind=='SET_NIGHT_LOAD_OVERRIDE':
        if set(parameters)!={'command'} or parameters['command'] not in ('ON','OFF'):raise ContractRefused('request_invalid')
    elif set(parameters)!={'device','command'} or parameters['device'] not in ('dishwasher','shureflo','goat-cam') or parameters['command'] not in ('ON','OFF'):
        raise ContractRefused('request_invalid')


def _request_document(value,now,owner_age):
    if type(owner_age) is not int or not 1<=owner_age<=MAX_OWNER_AGE_SECONDS:raise ValueError('explicit bounded owner maximum age required')
    if set(value)!=REQUEST_FIELDS or value['schema']!='earthship-control-request/v2':raise ContractRefused('schema_unknown')
    if not _id(value['requestId']) or not isinstance(value['source'],str) or value['source'] not in SOURCES:raise ContractRefused('request_invalid')
    for key in ('intentId','snapshotId'):
        if value[key] is not None:
            try:digest(value[key])
            except ValueError:raise ContractRefused('request_invalid') from None
    if value['plannerVersion'] is not None and not _version(value['plannerVersion']):raise ContractRefused('request_invalid')
    if value['source']=='planner' and any(value[key] is None for key in ('intentId','snapshotId','plannerVersion')):
        raise ContractRefused('request_invalid')
    requested,expires=map(instant,(value['requestedAt'],value['expiresAt']))
    if requested>now:raise ContractRefused('request_future')
    if now-requested>timedelta(seconds=owner_age):raise ContractRefused('request_stale')
    if expires<=now:raise ContractRefused('request_expired')
    if not requested<expires<=requested+timedelta(seconds=owner_age):raise ContractRefused('request_invalid')
    validate_parameters(value['intentType'],value['parameters'])


@dataclass(frozen=True)
class ControlRequest:
    content: bytes
    validated_at: datetime
    owner_max_age_seconds: int

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ContractRefused('request_invalid')
        object.__setattr__(self,'validated_at',utc(self.validated_at))
        _request_document(loads(self.content),self.validated_at,self.owner_max_age_seconds)

    def to_dict(self):return loads(self.content)


def parse_request(raw,*,now,owner_max_age_seconds=MAX_OWNER_AGE_SECONDS):
    value=_decode(raw,REQUEST_FIELDS,'earthship-control-request/v2')
    return ControlRequest(canonical(value),utc(now),owner_max_age_seconds)


def _result_document(value,request,now,owner_version):
    if not isinstance(request,ControlRequest) or not _version(owner_version):raise ValueError('original request and owner identity required')
    if set(value)!=RESULT_FIELDS or value['schema']!='earthship-control-result/v2':raise ContractRefused('schema_unknown')
    original=request.to_dict()
    if any(value[key]!=original[key] for key in ('requestId','intentId','snapshotId')) or value['ownerVersion']!=owner_version:
        raise ContractRefused('request_invalid')
    status,reason=value['status'],value['reasonCode']
    if not isinstance(status,str) or not isinstance(reason,str) or status not in STATUSES or reason not in REASON_CODES:raise ContractRefused('request_invalid')
    if status in ('accepted','running','completed') and reason!=status:raise ContractRefused('request_invalid')
    if status=='denied' and reason in {'accepted','running','completed'}|FAILURE_REASONS:raise ContractRefused('request_invalid')
    if status=='failed' and reason not in FAILURE_REASONS:raise ContractRefused('request_invalid')
    at=instant(value['at'])
    if not instant(original['requestedAt'])<=at<=now:raise ContractRefused('request_invalid')
    if status in ('accepted','running') and at>=instant(original['expiresAt']):raise ContractRefused('request_expired')


@dataclass(frozen=True)
class ControlResult:
    content: bytes
    request: ControlRequest
    validated_at: datetime
    expected_owner_version: str

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ContractRefused('request_invalid')
        object.__setattr__(self,'validated_at',utc(self.validated_at))
        _result_document(loads(self.content),self.request,self.validated_at,self.expected_owner_version)

    def to_dict(self):return loads(self.content)

    @property
    def owner_reports_completion(self):return self.to_dict()['status']=='completed'


def parse_result(raw,*,request,now,expected_owner_version):
    value=_decode(raw,RESULT_FIELDS,'earthship-control-result/v2')
    return ControlResult(canonical(value),request,utc(now),expected_owner_version)


def validate_result_sequence(results,*,request):
    if not isinstance(results,(list,tuple)) or not 1<=len(results)<=16 or not isinstance(request,ControlRequest):
        raise ContractRefused('request_invalid')
    transitions={None:{'accepted','denied','failed'},'accepted':{'running','completed','denied','failed'},
                 'running':{'completed','failed'},'completed':set(),'denied':set(),'failed':set()}
    previous=None;previous_at=None;owner=None
    for result in results:
        if not isinstance(result,ControlResult) or result.request.content!=request.content:raise ContractRefused('request_invalid')
        value=result.to_dict();at=instant(value['at']);version=value['ownerVersion']
        if value['status'] not in transitions[previous] or (previous_at is not None and at<previous_at) or (owner is not None and owner!=version):
            raise ContractRefused('request_invalid')
        previous=value['status'];previous_at=at;owner=version
    return previous


def legacy_result_status(status):
    value='completed' if status=='complete' else status
    if not isinstance(value,str) or value not in STATUSES:raise ContractRefused('request_invalid')
    return value
