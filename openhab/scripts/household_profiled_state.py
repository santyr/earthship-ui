"""Curated profile scenarios and atomic private publication; no model execution."""
from datetime import timedelta
from pathlib import Path
import os,secrets
from household.codec import canonical,loads,identity
from household.evidence import utc
from household.control_contracts import instant
from household_observation import _directory,_private_file
from household_profiled_forecast import SCHEMA
from household_profiled_samples import REPORT

OBSERVATION='earthship-household-profiled-energy-observation/v1'
INDEX='earthship-household-profiled-energy-samples/v1'


def project_observation(forecast,*,energy_receipt,generated_at):
    if (forecast.get('schema')!=SCHEMA or identity({k:v for k,v in forecast.items() if k!='receipt_sha256'})!=forecast.get('receipt_sha256') or
        forecast['inputs']['original_energy_receipt_sha256']!=energy_receipt['receipt_sha256'] or forecast['inputs']['original_energy_document_sha256']!=identity(energy_receipt)):
        raise ValueError('original profiled and constant-load receipts required')
    out=forecast['output'];issue=instant(out['issued_at']);generated=utc(generated_at);source=forecast['inputs']['load_source'];load=out['load_forecast']
    profile=None if source is None else source['artifact']['profile'];available=out['status']=='conditional_nominal_simulation';until=issue+timedelta(minutes=15)
    if available and profile is not None and profile['valid_until'] is not None:until=min(until,instant(profile['valid_until']))
    if not instant(forecast['inputs']['assessed_at'])<=generated<until:raise ValueError('bounded original profiled observation window required')
    storage=out['profiled_storage'];original=energy_receipt['output']['nominal_storage'];trajectory=[]
    if available:
        for i,row in enumerate(load['trajectory']):
            point=storage['trajectory'][i];baseline=original['trajectory'][i]
            if row['at']!=point['at'] or row['at']!=baseline['at']:raise ValueError('original curated profile target differs')
            trajectory.append(dict(at=row['at'],profiled_ac_w=row['mean_ac_w'],constant_ac_w=out['current_load_persistence_w'],
                profiled_soc_pct=point['nominal_soc_pct'],constant_soc_pct=baseline['nominal_soc_pct'],minimum_support_days=row['minimum_support_days'],training_spread_ac_w=row['training_spread_mean_w']))
    value=dict(schema=OBSERVATION,generated_at=generated.isoformat(),issued_at=issue.isoformat(),valid_until=until.isoformat(),receipt_sha256=forecast['receipt_sha256'],
        original_energy_receipt_sha256=energy_receipt['receipt_sha256'],cohort_id=out['cohort_id'],status='conditional' if available else 'unavailable',reason=out['reason'],
        model_artifact_sha256=None if source is None else source['artifact']['artifact_sha256'],model_sha256=None if profile is None else profile['model_sha256'],
        trained_through=None if profile is None else profile['latest_qualified_hour_end'],training_cutoff=None if source is None else source['artifact']['cutoff'],
        model_valid_until=None if profile is None else profile['valid_until'],total_ac_kwh=None if not available else load['total_ac_kwh'],
        initial_soc_pct=None if not available else storage['initial_soc_pct'],nominal_bank_kwh=None if not available else storage['nominal_bank_kwh'],
        current_ac_w=None if not available else out['current_load_persistence_w'],profiled_captured_pv_24h_kwh=None if not available else storage['modeled_captured_pv_kwh'],
        constant_captured_pv_24h_kwh=None if not available else original['modeled_captured_pv_kwh'],trajectory=trajectory,confidence='provisional_uncalibrated',
        physical_calibration_qualified=False,automatic_actuation=False)
    value['view_sha256']=identity(value)
    if len(canonical(value))>32768:raise ValueError('bounded curated profile observation required')
    return loads(canonical(value))


def publish_owned(path,value,*,guard,maximum=32768):
    path=Path(path);directory=_directory(path.parent);encoded=canonical(value)
    if value.get('schema') not in (OBSERVATION,REPORT,INDEX) or len(encoded)>maximum:raise ValueError('bounded owned profile publication required')
    try:previous=_private_file(path,maximum)
    except FileNotFoundError:previous=None
    if previous is not None and loads(previous[0]).get('schema')!=value['schema']:raise ValueError('profile publication target belongs to another producer')
    temporary=path.parent/('.profiled-'+secrets.token_hex(16))
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        guard()
        try:current=_private_file(path,maximum)
        except FileNotFoundError:current=None
        if current!=previous or _directory(path.parent)!=directory:raise ValueError('profile publication context changed')
        os.replace(temporary,path)
        if _private_file(path,maximum)[0]!=encoded:raise ValueError('profile publication readback differs')
    finally:temporary.unlink(missing_ok=True)
