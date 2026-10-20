#!/usr/bin/env python3
"""Score retained, actually issued daily PV against qualified controller input."""
from datetime import datetime,timedelta,time,timezone,date
from pathlib import Path
from hashlib import sha256
from math import fsum
from zoneinfo import ZoneInfo
import argparse,json,os,sqlite3
from household_native_training import directory,save
from household_capture import _connection
from household_snapshot import _read as public_read
from weather_source_files import _read
from weather_learning.contracts import identity,instant,digest,finite
from weather_learning.energy_history import capture_hour,summarize_hour
from weather_learning.worker import collector_lock


def score_hour(forecast,source,*,assessed_at):
    if (forecast.get('schema')!='earthship-daily-pv-potential-receipt/v1' or forecast.get('receipt_sha256')!=identity({k:v for k,v in forecast.items() if k!='receipt_sha256'})):
        raise ValueError('original forecast identity differs')
    view=forecast['view'];start,end=map(instant,(source['start'],source['end']));origin=instant(view['generatedAt'])
    if view.get('schema')!='earthship-daily-pv-potential/v2' or view.get('automatic_actuation') is not False:raise ValueError('original calibrated read-only forecast required')
    if origin>start:raise ValueError('forecast must exist before the scored hour')
    if not instant(forecast['calibration_source']['model']['trained_at'])<=origin:raise ValueError('model must exist before its forecast')
    if instant(source['received_at'])>assessed_at:raise ValueError('original power not yet available')
    model=digest(view['calibration']['modelSha256']);steps=forecast['projection_steps']
    if not isinstance(steps,list) or not 1<=len(steps)<=3000:raise ValueError('bounded original forecast steps required')
    selected={}
    for step in steps:
        left,right=map(instant,(step['start'],step['end']))
        if not origin<=left<right or not all(finite(step[k]) and 0<=step[k]<=30000 for k in ('uncalibrated_w','potential_w')) or type(step['calibration_applied']) is not bool:
            raise ValueError('finite original future PV steps required')
        key=left,right
        if key in selected:raise ValueError('unique original PV steps required')
        selected[key]=step
    bins=summarize_hour(source);pairs=[];missing=0
    for b in bins:
        if not b['potential_proxy_eligible']:continue
        step=selected.get((instant(b['start']),instant(b['end'])))
        if step is None:missing+=1;continue
        field=b['fields']['pv.input_power_w'];seconds=field['covered_seconds'];actual=field['positive_kwh']*3600000/seconds
        pairs.append(dict(start=b['start'],end=b['end'],covered_seconds=seconds,observed_input_w=actual,baseline_w=step['uncalibrated_w'],candidate_w=step['potential_w'],calibration_applied=step['calibration_applied']))
    weight=fsum(r['covered_seconds'] for r in pairs)
    def mae(key):return None if not pairs else fsum(abs(r[key]-r['observed_input_w'])*r['covered_seconds'] for r in pairs)/weight
    out=dict(schema='earthship-pv-prospective-hour-score/v1',status='scored' if pairs else 'awaiting_eligible_evidence',assessed_at=assessed_at.isoformat(),
        window_start=start.isoformat(),window_end=end.isoformat(),forecast_issued_at=origin.isoformat(),forecast_receipt_sha256=forecast['receipt_sha256'],model_sha256=model,
        power_source_sha256=source['source_sha256'],eligible_bins=len(pairs),adjusted_bins=sum(r['calibration_applied'] for r in pairs),missing_forecast_bins=missing,
        covered_seconds=weight,baseline_mae_w=mae('baseline_w'),candidate_mae_w=mae('candidate_w'),pairs=pairs,
        outcome_scope='qualified_low_soc_charging_controller_input_proxy',metric_basis='covered_duration_weighted_absolute_power_error',
        prospective_score=True,physical_calibration_qualified=False,automatic_actuation=False)
    out['score_sha256']=identity(out);return out


def choose_forecast(root,start):
    paths=sorted(Path(root).glob('*.receipt.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True)[:64];best=None
    for path in paths:
        raw=_read(path,8*1024**2);value=json.loads(raw)
        if value.get('receipt_sha256')!=path.name.removesuffix('.receipt.json') or value.get('receipt_sha256')!=identity({k:v for k,v in value.items() if k!='receipt_sha256'}):raise ValueError('retained PV forecast identity differs')
        view=value.get('view',{})
        if view.get('schema')=='earthship-daily-pv-potential/v2' and instant(view['generatedAt'])<=start<instant(view['calibration']['applyThroughAt']):
            row=(instant(view['generatedAt']),value['receipt_sha256'],value)
            if best is None or row[:2]>best[:2]:best=row
    return None if best is None else best[2]


def run(*,forecast_root,state_root,clock=lambda:datetime.now(timezone.utc)):
    state=directory(state_root);now=clock();end=(now-timedelta(minutes=5)).replace(minute=0,second=0,microsecond=0);start=end-timedelta(hours=1)
    with collector_lock(state/'worker.lock'):
        database=state/'scores.sqlite3'
        with sqlite3.connect(database,timeout=2) as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS hours (start TEXT PRIMARY KEY,score_sha256 TEXT NOT NULL,model_sha256 TEXT NOT NULL)')
            os.chmod(database,0o600);previous=connection.execute('SELECT score_sha256 FROM hours WHERE start=?',(start.isoformat(),)).fetchone()
        if previous is not None:
            score=json.loads(_read(state/(digest(previous[0])+'.score.json'),262144))
            if score['score_sha256']!=previous[0] or score['score_sha256']!=identity({k:v for k,v in score.items() if k!='score_sha256'}):raise ValueError('retained prospective score differs')
            result=dict(status='already_scored',window_start=start.isoformat(),score_sha256=previous[0],automatic_actuation=False)
        else:
            forecast=choose_forecast(forecast_root,start)
            if forecast is None:
                result=dict(status='awaiting_as_issued_forecast',window_start=start.isoformat(),window_end=end.isoformat(),automatic_actuation=False)
            else:
                policy=_read('/home/sat/Solar_PV/analytics/config/power-evidence.json',4096).decode()
                epochs=json.loads(public_read('/home/sat/Solar_PV/analytics/config/system-epochs.json',16384));bank=next(r for r in epochs['epochs'] if r['current_analytics'])
                bank_start=datetime.combine(date.fromisoformat(bank['start_local_date']),time.min,ZoneInfo(epochs['timezone'])).astimezone(timezone.utc).isoformat()
                import earthship_energy.power_evidence as companion
                runtime={'daily_pv_monitor.py':Path(__file__),'weather_learning/energy_history.py':Path(__file__).with_name('weather_learning')/'energy_history.py'}
                runtime.update({'companion/'+name:Path(companion.__file__).parent/name for name in ('power_evidence.py','power_intervals.py','bms_evidence.py','ac_evidence.py')})
                originals={name:p.read_bytes() for name,p in runtime.items()}
                source,path=capture_hour(directory(state/'originals'),start,connect=_connection('/home/sat/.config/hex/energy-power-reader.jdbc','energy_power_reader'),policy_raw=policy,bank_start=bank_start,clock=clock)
                score=score_hour(forecast,source,assessed_at=clock())
                if any(p.read_bytes()!=originals[name] for name,p in runtime.items()):raise ValueError('PV scoring runtime changed during acquisition')
                score.pop('score_sha256');score['runtime_manifest']={name:sha256(raw).hexdigest() for name,raw in originals.items()};score['original_file_sha256']=sha256(_read(path,8*1024**2)).hexdigest();score['score_sha256']=identity(score)
                source_root=directory(state/'sources')
                for raw in originals.values():
                    path=source_root/(sha256(raw).hexdigest()+'.py')
                    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    except FileExistsError:
                        if _read(path,262144)!=raw:raise ValueError('retained scoring source differs')
                    else:
                        with os.fdopen(fd,'wb') as handle:handle.write(raw)
                save(state/(score['score_sha256']+'.score.json'),score)
                with sqlite3.connect(database,timeout=2) as connection:connection.execute('INSERT INTO hours VALUES(?,?,?)',(start.isoformat(),score['score_sha256'],score['model_sha256']))
                result={key:score[key] for key in ('status','window_start','window_end','model_sha256','eligible_bins','baseline_mae_w','candidate_mae_w','score_sha256','prospective_score','physical_calibration_qualified','automatic_actuation')}
        result['checked_at']=clock().isoformat();save(state/'last-result.json',result);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--forecasts',required=True,type=Path);p.add_argument('--state',required=True,type=Path);a=p.parse_args(argv);os.umask(0o077)
    try:print(json.dumps(run(forecast_root=a.forecasts,state_root=a.state)),flush=True);return 0
    except Exception as error:
        print(json.dumps(dict(status='pv_monitor_incomplete',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
