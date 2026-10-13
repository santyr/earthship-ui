"""Reuse a mature provider's validated Household Observation, never poll twice."""
from .contract import digest,normalize,instant


def adapt_provider(*,sensor,observation,original_raw,expected_sha256,kind,unit,as_of):
    from household.evidence import Observation
    if not isinstance(observation,Observation):raise ValueError('mature validated household observation required')
    ref=observation.ref;as_of=instant(as_of)
    if not isinstance(original_raw,bytes) or len(original_raw)>1048576 or digest(original_raw)!=expected_sha256 or ref.digest!=expected_sha256:
        raise ValueError('exact original provider evidence required')
    if (ref.quality!='qualified' or ref.assessed_at>as_of or ref.available_at>as_of or
        as_of>=ref.valid_until or sensor['hardware_epoch']!=(ref.hardware_epoch or ref.source_epoch)):
        raise ValueError('fresh owner-bound qualified provider required')
    # Conversion is explicit at the source adapter, not guessed from Item names.
    value=observation.value
    if kind=='air_temperature' and observation.unit=='degF' and unit=='degC':value=(value-32)*5/9
    elif observation.unit!=unit:raise ValueError('unsupported provider unit conversion')
    return normalize(sensor=sensor,kind=kind,value=value,unit=unit,observed_at=ref.observed_at,
        received_at=ref.received_at,valid_until=ref.valid_until,source_identity=ref.source_identity,
        raw_sha256=expected_sha256,source_epoch=ref.source_epoch,timestamp_basis='provider_receipt',synthetic=False,qualified=True)
