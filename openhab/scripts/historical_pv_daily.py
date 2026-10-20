#!/usr/bin/env python3
"""Daily local PV evidence refresh and explicit provisional model selection."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import argparse,gzip,json,os,subprocess,time,traceback
from household_native_training import directory,save
from weather_source_files import _read
from weather_learning.contracts import canonical,identity,instant
from weather_learning.worker import collector_lock
from weather_learning.pv_calibration_source import restore_calibration
from weather_learning.pv_refresh import compare_incumbent


def geometry_declarations(root):
    root=Path(root)
    return tuple(_read(root/'openhab'/name,16384,source=True) for name in ('household-pv-system.json','household-solar-horizon.json'))


def select_candidate(candidate,rows,*,training_model,selected_path,now,system_raw,horizon_raw):
    path=Path(selected_path);raw=canonical(candidate)
    try:restored=restore_calibration(raw,origin=now,system_raw=system_raw,horizon_raw=horizon_raw)
    except ValueError as error:
        if str(error)!='PV calibration is unavailable or expired at origin':raise
        return dict(status='candidate_unavailable_incumbent_preserved',reason='model_unavailable_or_expired',automatic_actuation=False)
    if training_model['model_sha256']!=candidate['training_model_sha256']:
        raise ValueError('candidate comparison model differs')
    before=_read(path,262144) if path.exists() else None
    comparison=None
    if before is not None:
        old=json.loads(before)
        # Validate original availability even when the incumbent is expired;
        # an assessment must never renew its original training clock.
        incumbent=restore_calibration(before,origin=instant(old['created_at']),system_raw=system_raw,horizon_raw=horizon_raw)
        comparison=compare_incumbent(training_model,incumbent['model'],rows,
            holdout_start=instant(candidate['report']['holdout_start']),holdout_end=instant(candidate['report']['holdout_end']))
    selected=comparison is None or comparison['selected'] is True
    if selected:
        if before is not None and _read(path,262144)!=before:raise ValueError('selected PV model changed during comparison')
        save(path,candidate)
    return dict(status='candidate_selected' if selected else 'incumbent_preserved',
        selected_model_sha256=restored['model']['model_sha256'] if selected else incumbent['model']['model_sha256'],
        candidate_model_sha256=restored['model']['model_sha256'],previous_file_sha256=None if before is None else sha256(before).hexdigest(),
        comparison=comparison,automatic_actuation=False)


def load_candidate(state):
    state=Path(state);pointer=json.loads(_read(state/'directional/last-experiment.json',8192));run=Path(pointer['path'])
    candidate=json.loads(_read(run/'experiment.json',262144))
    if candidate['receipt_sha256']!=pointer['receipt_sha256'] or candidate['receipt_sha256']!=identity({k:v for k,v in candidate.items() if k!='receipt_sha256'}):raise ValueError('candidate original differs')
    parent=Path(candidate['parent_experiment_path']);receipt=json.loads(_read(parent/'experiment.json',1048576))
    if receipt['receipt_sha256']!=candidate['parent_receipt_sha256'] or receipt['dataset_sha256']!=candidate['dataset_sha256'] or receipt['receipt_sha256']!=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'}):raise ValueError('candidate parent differs')
    with gzip.open(parent/(candidate['dataset_sha256']+'.pairs.json.gz'),'rb') as stream:raw=stream.read(32*1024**2+1)
    if len(raw)>32*1024**2:raise ValueError('bounded PV paired data required')
    dataset=json.loads(raw)
    if dataset['dataset_sha256']!=candidate['dataset_sha256'] or dataset['dataset_sha256']!=identity({k:v for k,v in dataset.items() if k!='dataset_sha256'}):raise ValueError('candidate paired data differ')
    training=json.loads(_read(run/'training-model.json',1048576))
    return candidate,dataset,training,run


def selection_bytes(path):
    """Read an optional original without following links or accepting large files."""
    try:return _read(path,262144)
    except FileNotFoundError:return None


def retained_selection(raw):
    """Identify opaque original bytes; numerical serving admission stays separate."""
    result=dict(status='incumbent_unavailable',selected_model_sha256=None,
        selected_receipt_sha256=None,previous_file_sha256=None,promotion_permitted=False,
        serving_availability='unavailable',automatic_actuation=False)
    if raw is None:return result
    value=json.loads(raw);model=value.get('final_model')
    if (value.get('schema')!='earthship-historical-pv-directional-experiment/v1' or
        value.get('receipt_sha256')!=identity({k:v for k,v in value.items() if k!='receipt_sha256'}) or
        value.get('automatic_actuation') is not False or not isinstance(model,dict) or
        model.get('model_sha256')!=identity({k:v for k,v in model.items() if k!='model_sha256'}) or
        model.get('automatic_actuation') is not False or model.get('physical_calibration_qualified') is not False):
        raise ValueError('unchanged retained PV selection identity required')
    # Deliberately do not load old numerics into today's producer or renew its
    # clocks. Only the actual serving producer can assess original availability.
    result.update(status='incumbent_retained_by_policy',selected_model_sha256=model['model_sha256'],
        selected_receipt_sha256=value['receipt_sha256'],previous_file_sha256=sha256(raw).hexdigest(),
        serving_availability='not_assessed')
    return result


def run(*,archive_path,libraries_path,base=None,root=None,clock=lambda:datetime.now(timezone.utc),retain_selection=False):
    base=Path.home()/'.local/state/earthship-weather' if base is None else Path(base)
    root=Path(__file__).resolve().parents[2] if root is None else Path(root)
    state=directory(base/'pv-calibration');status=directory(base/'pv-learning-daily');end=clock().replace(hour=0,minute=0,second=0,microsecond=0)
    index=json.loads(_read(base/'historical-energy/energy-index.json',1048576))
    if index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('original energy index differs')
    start=max(instant(index['hours'][0]['start']).replace(hour=0),end-timedelta(days=90));days=(end-start).days
    if not 7<=days<=90:raise ValueError('earlier training and later comparison dates required')
    deadline=time.monotonic()+850
    def command(name,args):
        left=deadline-time.monotonic()
        if left<5:raise TimeoutError('daily PV learning deadline elapsed')
        result=subprocess.run(['/usr/bin/python3',str(root/'openhab/scripts'/name),*map(str,args)],capture_output=True,timeout=min(left,600),env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(root/'openhab/scripts')+':/home/sat/Solar_PV/analytics/src'})
        if len(result.stdout)+len(result.stderr)>2*1024**2:raise ValueError('bounded PV step output required')
        log=status/(name+'.last.log');log.write_bytes(result.stdout+result.stderr);log.chmod(0o600)
        if result.returncode:raise RuntimeError('PV learning step failed: '+name)
    with collector_lock(status/'daily.lock'):
        selected=state/'selected-directional.json'
        if retain_selection:
            selected_before=selection_bytes(selected)
            decision=retained_selection(selected_before)
        command('historical_energy_capture.py',['--state',base/'historical-energy','--start',start.date().isoformat(),'--days',days,'--batch-hours',48,'--rolling-index'])
        command('historical_pv_train.py',['--archive',base/'historical-2026','--operational-archive',archive_path,'--energy',base/'historical-energy','--output',state,'--geometry',base/'pv-calibration-geometry','--libraries',libraries_path,'--train-end',(end-timedelta(days=6)).isoformat(),'--holdout-end',end.isoformat()])
        command('historical_pv_directional_train.py',['--state',state])
        candidate,dataset,training,origin=load_candidate(state)
        if not retain_selection:
            system_raw,horizon_raw=geometry_declarations(root)
            if candidate['report']['selected'] is True:
                decision=select_candidate(candidate,dataset['pairs'],training_model=training,selected_path=selected,now=clock(),system_raw=system_raw,horizon_raw=horizon_raw)
            else:decision=dict(status='candidate_not_improved_incumbent_preserved',automatic_actuation=False)
        updated=json.loads(_read(base/'historical-energy/energy-index.json',1048576));retained={r['start'] for r in updated['hours']};missing=sum((start+timedelta(hours=i)).isoformat() not in retained for i in range(days*24))
        if retain_selection and selection_bytes(selected)!=selected_before:
            raise ValueError('selected PV model changed during retained-selection run')
        result=dict(status='daily_pv_learning_complete',checked_at=clock().isoformat(),cutoff=end.isoformat(),missing_energy_hours=missing,
            candidate_experiment_path=str(origin),fit_executed=candidate['fit_executed'],selection=decision,automatic_actuation=False)
        result['result_sha256']=identity(result);save(status/(result['result_sha256']+'.result.json'),result);save(status/'last-result.json',result);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--libraries',type=Path,required=True);p.add_argument('--retain-selection',action='store_true',help='retain the original selected model while refreshing candidate evidence');a=p.parse_args(argv);os.umask(0o077)
    try:print(json.dumps(run(archive_path=a.archive,libraries_path=a.libraries,retain_selection=a.retain_selection)),flush=True);return 0
    except Exception as error:
        state=directory(Path.home()/'.local/state/earthship-weather/pv-learning-daily');save(state/'last-error.json',dict(at=datetime.now(timezone.utc).isoformat(),reason=type(error).__name__,message=str(error)[:2048],traceback=traceback.format_exc()[-8192:]))
        print(json.dumps(dict(status='daily_pv_learning_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
