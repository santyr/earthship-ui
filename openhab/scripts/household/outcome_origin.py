"""Verify a delivered original at collection; frozen scoring does no source reads."""
from dataclasses import dataclass
from .codec import canonical,loads,identity
from .thermal_model import PreparedProjection,prepare_projection,project
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
        if set(value)!=FIELDS or value['schema']!='earthship-household-outcome-origin/v1':raise ValueError('closed prepared delivered origin required')
        if identity({key:item for key,item in value.items() if key!='origin_sha256'})!=value['origin_sha256']:
            raise ValueError('prepared delivered origin differs')
        prepared=PreparedProjection(canonical(value['prepared_thermal']));projection=project(prepared)
        capture=value['original_capture'];source=prepared.to_dict()
        if (not isinstance(capture,dict) or capture.get('capture_sha256')!=capture_digest(capture,'capture_sha256') or
            capture['capture_sha256']!=source['original_capture_sha256'] or capture['issued_at']!=source['issue'] or
            capture['published_at']!=source['snapshot']['created_at'] or
            canonical(capture['output'])!=canonical(projection['output']) or
            capture['candidate']['artifact_sha256']!=source['artifact_sha256'] or capture['candidate']['runtime_sha256']!=source['runtime_sha256']):
            raise ValueError('original delivered forecast differs from prepared model')
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
