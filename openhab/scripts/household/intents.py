"""Sealed typed shadow intents. Translation is disabled, not a send path."""
from dataclasses import dataclass
from datetime import datetime,timedelta
import math
from .codec import canonical,loads,identity
from .evidence import utc,digest
from .snapshot import HouseholdSnapshot
from .control_contracts import ContractRefused,INTENT_TYPES,REASON_CODES,instant,validate_parameters

MAX_INTENT_BYTES=8192
FIELDS={'schema','intentId','type','createdAt','expiresAt','snapshotId','evidenceRefs',
        'predictedEffects','confidence','reasonCodes','shadowOnly','parameters'}
EFFECT_UNITS={'batteryKwh':'kWh','socPct':'percentage_points','thermalF':'degF',
              'water':'litre','wearCost':'normalized_cycle_cost'}
EFFECT_LIMITS={'batteryKwh':1000,'socPct':100,'thermalF':100,'water':1000000,'wearCost':1000000}
CONFIDENCE=frozenset(('unavailable','low','medium','high'))


def _validate(value,snapshot,now):
    if not isinstance(snapshot,HouseholdSnapshot):raise ContractRefused('intent_invalid')
    snap=snapshot.to_dict()
    if snap.get('schema') in ('earthship-household-snapshot/v3','earthship-household-snapshot/v4','earthship-household-snapshot/v5'):
        from .model_snapshot import ModelSnapshot
        if not isinstance(snapshot,ModelSnapshot):raise ContractRefused('intent_invalid')
        if snap['schema'].endswith('/v5'):
            from .energy_source_snapshot import EnergySourceSnapshot
            if not isinstance(snapshot,EnergySourceSnapshot):raise ContractRefused('intent_invalid')
        if snap['schema'].endswith(('/v4','/v5')):
            from .weather_snapshot import WeatherSnapshot
            if not isinstance(snapshot,WeatherSnapshot):raise ContractRefused('intent_invalid')
    elif snap.get('schema')!='earthship-household-snapshot/v1':raise ContractRefused('intent_invalid')
    if set(value)!=FIELDS or value['schema']!='earthship-household-intent/v1':raise ContractRefused('schema_unknown')
    body={key:item for key,item in value.items() if key!='intentId'}
    if value['intentId']!=identity(body):raise ContractRefused('intent_invalid')
    if value['shadowOnly'] is not True:raise ContractRefused('planner_authority_disabled')
    if value['snapshotId']!=snapshot.snapshot_id:raise ContractRefused('snapshot_mismatch')
    created,expires=map(instant,(value['createdAt'],value['expiresAt']))
    if created>now or created<instant(snap['as_of']) or not created<expires or expires-created>timedelta(seconds=300):
        raise ContractRefused('intent_invalid')
    if now>=expires:raise ContractRefused('intent_expired')
    kind=value['type']
    if not isinstance(kind,str) or kind not in INTENT_TYPES|{'NO_ACTION'}:raise ContractRefused('intent_invalid')
    confidence=value['confidence']
    if not isinstance(confidence,str) or confidence not in CONFIDENCE:raise ContractRefused('intent_invalid')
    reasons=value['reasonCodes']
    if not isinstance(reasons,list) or not 1<=len(reasons)<=16 or any(not isinstance(reason,str) or reason not in REASON_CODES-{'accepted','running','completed'} for reason in reasons) or len(reasons)!=len(set(reasons)):
        raise ContractRefused('intent_invalid')
    effects=value['predictedEffects']
    if not isinstance(effects,dict) or set(effects)!=set(EFFECT_UNITS):raise ContractRefused('intent_invalid')
    for name,number in effects.items():
        if number is not None and (type(number) not in (int,float) or not math.isfinite(number) or abs(number)>EFFECT_LIMITS[name] or (name=='wearCost' and number<0)):
            raise ContractRefused('intent_invalid')
    refs=value['evidenceRefs']
    if not isinstance(refs,list) or len(refs)>32 or any(not isinstance(ref,str) for ref in refs) or len(refs)!=len(set(refs)):
        raise ContractRefused('intent_invalid')
    for ref in refs:digest(ref)
    available={row['evidence']['digest']:(role,row) for domain in snap['domains'].values() for role,row in domain.items() if row['evidence'] is not None and row['evidence']['digest'] is not None}
    if any(ref not in available for ref in refs):raise ContractRefused('intent_invalid')
    if kind=='NO_ACTION':
        if value['parameters']!={} or any(number not in (None,0) for number in effects.values()):raise ContractRefused('intent_invalid')
    else:
        validate_parameters(kind,value['parameters'])
        if not refs:raise ContractRefused('source_unavailable')
        for ref in refs:
            role,row=available[ref];evidence=row['evidence']
            if row['reason'] is not None or row['value'] is None or evidence['quality']!='qualified':raise ContractRefused('source_unavailable')
            observed=evidence['observed_at'] or evidence['received_at']
            if instant(evidence['available_at'])>now or now>=instant(evidence['valid_until']) or (now-instant(observed)).total_seconds()>snap['temporal_policy']['max_age_seconds'][role]:
                raise ContractRefused('source_stale')


@dataclass(frozen=True)
class HouseholdIntent:
    content:bytes
    snapshot:HouseholdSnapshot
    validated_at:datetime

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_INTENT_BYTES:raise ContractRefused('intent_invalid')
        object.__setattr__(self,'validated_at',utc(self.validated_at))
        try:_validate(loads(self.content),self.snapshot,self.validated_at)
        except ContractRefused:raise
        except (KeyError,TypeError,ValueError,OverflowError,RecursionError):raise ContractRefused('intent_invalid') from None

    @property
    def intent_id(self):return self.to_dict()['intentId']

    def to_dict(self):return loads(self.content)


def build_intent(document,*,snapshot,now):
    try:
        if not isinstance(document,dict) or set(document)!=FIELDS-{'intentId'}:raise ContractRefused('intent_invalid')
        value={**document,'intentId':identity(document)}
        return HouseholdIntent(canonical(value),snapshot,utc(now))
    except ContractRefused:raise
    except (TypeError,ValueError,OverflowError,RecursionError):raise ContractRefused('intent_invalid') from None


def parse_intent(raw,*,snapshot,now):
    try:
        if not isinstance(raw,str) or not 1<=len(raw.encode('utf-8'))<=MAX_INTENT_BYTES:raise ContractRefused('intent_invalid')
        return HouseholdIntent(canonical(loads(raw)),snapshot,utc(now))
    except ContractRefused:raise
    except (TypeError,ValueError,OverflowError,RecursionError):raise ContractRefused('intent_invalid') from None


def intent_to_request(intent):
    raise ContractRefused('planner_authority_disabled')
