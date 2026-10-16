"""Curated observational state and owned atomic publication; no source collection."""
from datetime import timedelta
from pathlib import Path
import os,secrets
from hashlib import sha256
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household_observation import _private_file,_directory

OBSERVATION='earthship-household-energy-observation/v1'
REPORT='earthship-household-solar-storage-performance/v1'
INDEX='earthship-household-solar-storage-samples/v1'


def project_energy_observation(forecast,*,plan_receipt,generated_at):
    from household_solar_outcomes import cohort_for
    # The scheduled producer already rederives this receipt. Curation verifies
    # its pins and copies a closed public field set, without running a model.
    if identity({k:v for k,v in forecast.items() if k!='receipt_sha256'})!=forecast.get('receipt_sha256') or forecast['schema']!='earthship-household-energy-forecast-receipt/v1':raise ValueError('original energy receipt required')
    if forecast['inputs']['plan_document_sha256']!=sha256(canonical(plan_receipt)).hexdigest() or forecast['inputs']['plan_receipt_sha256']!=plan_receipt['receipt_sha256']:raise ValueError('original observation plan differs')
    pv=forecast['output']['array_pv'];storage=forecast['output']['nominal_storage'];generated=utc(generated_at);issue=instant(pv['origin'])
    if not instant(forecast['inputs']['assessed_at'])<=generated<issue+timedelta(minutes=15):raise ValueError('bounded original forecast publication window required')
    available=pv['status']=='projected_provisional_array_potential';conditional=storage['status']=='conditional_nominal_simulation';cohort=cohort_for(forecast,plan_receipt)
    trajectory=[]
    for i,row in enumerate(pv['trajectory']):
        point=None if not conditional else storage['trajectory'][i]
        if point is not None and point['at']!=row['end']:raise ValueError('curated scenario clock differs')
        trajectory.append(dict(at=row['end'],potential_pv_kwh=row['potential_pv_kwh'],captured_pv_kwh=None if point is None else point['cumulative_modeled_captured_pv_kwh']-(0 if i==0 else storage['trajectory'][i-1]['cumulative_modeled_captured_pv_kwh']),nominal_soc_pct=None if point is None else point['nominal_soc_pct']))
    value=dict(schema=OBSERVATION,generated_at=generated.isoformat(),issued_at=issue.isoformat(),valid_until=(issue+timedelta(minutes=15)).isoformat(),
        receipt_sha256=forecast['receipt_sha256'],cohort_id=None if cohort is None else identity(cohort),status='available' if available else 'unavailable',
        reason=pv['reason'],storage_status='conditional' if conditional else 'unavailable',storage_reason=storage['reason'],
        potential_pv_24h_kwh=pv['potential_pv_kwh'],potential_pv_remaining_today_kwh=pv['remaining_today_potential_kwh'],
        captured_pv_24h_kwh=storage.get('modeled_captured_pv_kwh'),household_ac_load_w_assumption=storage.get('household_ac_load_w_assumption'),
        initial_soc_pct=storage.get('initial_soc_pct'),nominal_bank_kwh=storage.get('nominal_bank_kwh'),trajectory=trajectory,
        terrain_status=pv['terrain_status'],confidence='provisional_uncalibrated',pv_energy_accuracy='unavailable_unmatched_meter_scope',
        physical_calibration_qualified=False,automatic_actuation=False)
    value['view_sha256']=identity(value)
    if len(canonical(value))>32768:raise ValueError('bounded public energy observation required')
    return loads(canonical(value))


def publish_owned(path,value,*,guard,maximum=32768):
    path=Path(path);directory=_directory(path.parent);encoded=canonical(value)
    if value.get('schema') not in (OBSERVATION,REPORT,INDEX) or len(encoded)>maximum:raise ValueError('bounded owned energy publication required')
    try:previous=_private_file(path,maximum)
    except FileNotFoundError:previous=None
    if previous is not None and loads(previous[0]).get('schema')!=value['schema']:raise ValueError('energy target belongs to another producer')
    temporary=path.parent/('.energy-'+secrets.token_hex(16))
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        guard()
        try:current=_private_file(path,maximum)
        except FileNotFoundError:current=None
        if current!=previous or _directory(path.parent)!=directory:raise ValueError('energy publication context changed')
        os.replace(temporary,path)
        if _private_file(path,maximum)[0]!=encoded:raise ValueError('energy publication readback differs')
    finally:
        try:temporary.unlink()
        except FileNotFoundError:pass
