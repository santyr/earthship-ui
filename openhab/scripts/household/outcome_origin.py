"""Verify a delivered original at collection; frozen scoring does no source reads."""
from dataclasses import dataclass
from .codec import canonical,loads,identity
from .thermal_model import PreparedProjection,prepare_projection,project,ROLES
from .evidence import EvidenceRef,Observation
from .snapshot import build_snapshot
from .control_contracts import instant
from thermal_model.provisional_artifact import candidate_digest
from thermal_model.temperature_history import STREAMS,_validate_sensor_receipt
from thermal_model.provisional_forecast import digest as capture_digest
from thermal_model.provisional_score import validate_delivery

FIELDS={'schema','prepared_thermal','original_capture','receipts','origin_sha256'}
MAX_BYTES=3*1024*1024


@dataclass(frozen=True)
class PreparedOutcomeOrigin:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded prepared delivered origin required')
        value=loads(self.content)
        if set(value)!=FIELDS or value['schema'] not in ('earthship-household-outcome-origin/v1','earthship-household-outcome-origin/v2'):raise ValueError('closed prepared delivered origin required')
        if identity({key:item for key,item in value.items() if key!='origin_sha256'})!=value['origin_sha256']:
            raise ValueError('prepared delivered origin differs')
        prepared=PreparedProjection(canonical(value['prepared_thermal']));projection=project(prepared)
        capture=value['original_capture'];source=prepared.to_dict()
        native=value['schema']=='earthship-household-outcome-origin/v2'
        if (source['schema'] in ('earthship-household-prepared-thermal/v2','earthship-household-prepared-thermal/v3'))!=native:
            raise ValueError('delivered origin and prepared model versions differ')
        if (not isinstance(capture,dict) or capture.get('capture_sha256')!=capture_digest(capture,'capture_sha256') or
            capture['capture_sha256']!=source['original_capture_sha256'] or capture['issued_at']!=source['issue'] or
            capture['published_at']!=source['snapshot']['created_at'] or
            canonical(capture['output'])!=canonical(projection['output']) or
            capture['candidate']['artifact_sha256']!=source['artifact_sha256'] or capture['candidate']['runtime_sha256']!=source['runtime_sha256']):
            raise ValueError('original delivered forecast differs from prepared model')
        candidate=capture['candidate']
        if candidate_digest(candidate)!=candidate['artifact_sha256']:
            raise ValueError('original candidate identity differs')
        issue=instant(source['issue']);observations=[]
        for role,name in ROLES.items():
            row=capture['inputs']['origin_temperatures']['roles'][role]
            phase=candidate['fit']['sensor_epochs'][role]
            stream,model,sensor_id=STREAMS[role]
            if row['identity']!=dict(stream=stream,model=model,sensor_id=sensor_id,sensor_epoch=phase):
                raise ValueError('original sensor identity differs')
            target,receipt=row['grid'][-1]
            _validate_sensor_receipt(receipt,instant(target),sensor_epoch=phase)
            ref=EvidenceRef(name,'Weather_Temperature_Evidence_JSON:'+stream,receipt['snapshotSha256'],
                receipt['streamEpoch'],receipt['sensorEpoch'],None,instant(receipt['receivedAt']),instant(receipt['storedAt']),
                instant(receipt['validUntil']),issue,'qualified',None,(capture['capture_sha256'],))
            observations.append(Observation(ref,receipt['temperatureF'],'degF'))
        policy=dict(requirements={'thermal_current':list(ROLES.values())},max_age_seconds={role:120 for role in ROLES.values()},max_skew_seconds=120)
        snapshot=build_snapshot(observations,as_of=issue,created_at=instant(capture['published_at']),
            code_revision=source['snapshot']['code_revision'],config_revision=identity(policy),**policy)
        if canonical(snapshot.to_dict())!=canonical(source['snapshot']):
            raise ValueError('prepared snapshot differs from original sensor evidence')
        if native:
            # Reuse the complete frozen Google/model/geometry/source verifier;
            # an outer rehash cannot authorize a changed original weather row.
            from .weather_context import PreparedWeatherContext,GOOGLE_SCHEMA,_encode_original
            weather=dict(schema=GOOGLE_SCHEMA,original_capture=_encode_original(capture),prepared_thermal=source)
            weather['weather_sha256']=identity(weather)
            PreparedWeatherContext(canonical(weather))
            from native_thermal_score import validate_delivery as validate_native_delivery
            validate_native_delivery(capture,value['receipts'])
        else:
            from thermal_model.forecast_history import verify_origin_forecast_receipts
            verify_origin_forecast_receipts(capture['inputs']['forecast'])
            validate_delivery(capture,value['receipts'])

    def to_dict(self):return loads(self.content)

    @property
    def prepared(self):return PreparedProjection(canonical(self.to_dict()['prepared_thermal']))


def prepare_outcome_origin(capture,receipts,*,code_revision):
    prepared=prepare_projection(capture,code_revision=code_revision)
    validate_delivery(capture,receipts)
    value=dict(schema='earthship-household-outcome-origin/v1',prepared_thermal=prepared.to_dict(),
        original_capture=capture,receipts=receipts)
    value['origin_sha256']=identity(value)
    return PreparedOutcomeOrigin(canonical(value))


def prepare_native_outcome_origin(capture,receipts,*,code_revision,runtime,
        expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    """Verify the externally pinned native delivery before pure outcome scoring."""
    from copy import deepcopy
    from .thermal_model import prepare_native_projection
    from native_thermal_score import validate_delivery as validate_native_delivery
    capture,receipts,runtime=map(deepcopy,(capture,receipts,runtime))
    prepared=prepare_native_projection(capture,code_revision=code_revision,runtime=runtime,
        expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,
        check_budget=check_budget)
    validate_native_delivery(capture,receipts)
    value=dict(schema='earthship-household-outcome-origin/v2',prepared_thermal=prepared.to_dict(),
        original_capture=capture,receipts=receipts)
    value['origin_sha256']=identity(value)
    result=PreparedOutcomeOrigin(canonical(value));check_budget();return result
