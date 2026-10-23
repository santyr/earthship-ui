"""Curated as-issued PV potential proxy accuracy; no fitting or acquisition."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from math import fsum,isclose
from zoneinfo import ZoneInfo
import json,sqlite3
from weather_learning.contracts import identity,instant,digest,finite,canonical
from weather_source_files import _read

SCHEMA='earthship-pv-potential-performance/v1'
COUNTS=('eligible_bins','missing_forecast_bins','censored_bins','unqualified_bins','low_generation_bins','unknown_coverage_bins')
SCORES=('earthship-pv-prospective-hour-score/v1','earthship-pv-prospective-hour-score/v2','earthship-pv-prospective-hour-score/v3','earthship-pv-prospective-hour-score/v4')


def _score(score,now):
    if (not isinstance(score,dict) or score.get('schema') not in SCORES or score.get('score_sha256')!=identity({k:v for k,v in score.items() if k!='score_sha256'}) or
            score.get('prospective_score') is not True or score.get('physical_calibration_qualified') is not False or score.get('automatic_actuation') is not False or
            score.get('outcome_scope')!='qualified_low_soc_charging_controller_input_proxy' or score.get('metric_basis')!='covered_duration_weighted_absolute_power_error'):
        raise ValueError('original prospective PV score required')
    for k in ('score_sha256','model_sha256','forecast_receipt_sha256','power_source_sha256','original_file_sha256'):digest(score[k])
    policy=score.get('calibration_policy_sha256')
    if policy is not None:digest(policy)
    runtime=score['runtime_manifest']
    if not isinstance(runtime,dict) or not 1<=len(runtime)<=64:raise ValueError('bounded original PV score runtime required')
    for pin in runtime.values():digest(pin)
    start,end,origin,assessed=map(instant,(score['window_start'],score['window_end'],score['forecast_issued_at'],score['assessed_at']))
    if start.minute or start.second or start.microsecond or end-start!=timedelta(hours=1) or not origin<=start<end or not end+timedelta(minutes=5)<=assessed<=now:
        raise ValueError('original mature PV score clocks required')
    pairs=score['pairs'];seen=set()
    if not isinstance(pairs,list) or len(pairs)>12 or type(score['eligible_bins']) is not int or score['eligible_bins']!=len(pairs):raise ValueError('original PV score pairs required')
    for row in pairs:
        a,b=map(instant,(row['start'],row['end']))
        if (not start<=a<b<=end or b-a!=timedelta(minutes=5) or (a-start).total_seconds()%300 or a in seen or
                not finite(row['covered_seconds']) or not 285<=row['covered_seconds']<=300 or type(row['calibration_applied']) is not bool or
                not all(finite(row[k]) and 0<=row[k]<=30000 for k in ('observed_input_w','baseline_w','candidate_w'))):
            raise ValueError('unique finite covered original PV pairs required')
        seen.add(a)
    weight=fsum(p['covered_seconds'] for p in pairs)
    errors={key:fsum(abs(p[key]-p['observed_input_w'])*p['covered_seconds'] for p in pairs) for key in ('baseline_w','candidate_w')}
    for field,key in [('baseline_mae_w','baseline_w'),('candidate_mae_w','candidate_w')]:
        if (weight==0 and score[field] is not None or weight>0 and (not finite(score[field]) or not isclose(score[field],errors[key]/weight,rel_tol=1e-10,abs_tol=1e-8))):raise ValueError('original PV score metric differs from retained pairs')
    if not finite(score['covered_seconds']) or not isclose(weight,score['covered_seconds'],abs_tol=1e-8) or score['adjusted_bins']!=sum(p['calibration_applied'] for p in pairs):raise ValueError('original PV score duration or adjustment count differs')
    if type(score['missing_forecast_bins']) is not int or not 0<=score['missing_forecast_bins']<=12-len(pairs):raise ValueError('bounded original missing PV forecast count required')
    counts=score.get('bin_accounting')
    if score['schema'] in SCORES[2:]:
        if (not isinstance(counts,dict) or set(counts)!=set(COUNTS) or any(type(counts[k]) is not int or not 0<=counts[k]<=12 for k in COUNTS) or sum(counts.values())!=12 or
                counts['eligible_bins']!=len(pairs) or counts['missing_forecast_bins']!=score['missing_forecast_bins']):raise ValueError('closed original PV bin accounting required')
    else:
        counts=dict.fromkeys(COUNTS,0);counts.update(eligible_bins=len(pairs),missing_forecast_bins=score['missing_forecast_bins'],unknown_coverage_bins=12-len(pairs)-score['missing_forecast_bins'])
    cohort=dict(model_sha256=score['model_sha256'],calibration_policy_sha256=policy,scoring_runtime_sha256=identity(runtime))
    if score['schema']==SCORES[3]:
        for name in ('calibration_sha256','procedure_sha256','measurement_cohort_sha256','solar_grid_sha256','forecast_emission_sha256'):digest(score[name])
        if (not origin<=instant(score['forecast_published_at'])<=start or
            score['metric_population']!='constituent_five_minute_power_of_published_daily_totals' or
            score['baseline_rule']!='native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2'):
            raise ValueError('original component score population or publication differs')
        ZoneInfo(score['target_timezone'])
        cohort.update({k:score[k] for k in ('procedure_sha256','measurement_cohort_sha256','solar_grid_sha256','baseline_rule','metric_population','target_timezone')})
    return cohort,counts,errors,weight


def build_view(scores,*,generated_at):
    if not isinstance(scores,list) or len(scores)>168:raise ValueError('bounded seven-day PV performance originals required')
    end=(generated_at-timedelta(minutes=5)).replace(minute=0,second=0,microsecond=0);start=end-timedelta(days=7);groups={};seen=set()
    for score in scores:
        cohort,counts,errors,weight=_score(score,generated_at);window=instant(score['window_start'])
        if not start<=window<end:continue
        pin=identity(cohort);key=(pin,score['window_start'])
        if key in seen:raise ValueError('unique original hour per PV cohort required')
        seen.add(key);g=groups.setdefault(pin,dict(cohort_id=pin,**cohort,counts=[],weights=[],baseline_errors=[],candidate_errors=[],scores=[]))
        g['counts'].append(counts);g['weights'].append(weight);g['baseline_errors'].append(errors['baseline_w']);g['candidate_errors'].append(errors['candidate_w']);g['scores'].append(score)
    rows=[];component=any(s['schema']==SCORES[3] for s in scores)
    for group in groups.values():
        sources=group.pop('scores');counts=group.pop('counts');weight=fsum(group.pop('weights'));baseline=fsum(group.pop('baseline_errors'));candidate=fsum(group.pop('candidate_errors'))
        group.update({k:sum(c[k] for c in counts) for k in COUNTS})
        group.update(hour_count=len(sources),adjusted_bins=sum(s['adjusted_bins'] for s in sources),covered_seconds=weight,
            first_issue=min(s['forecast_issued_at'] for s in sources),last_issue=max(s['forecast_issued_at'] for s in sources),first_window_start=min(s['window_start'] for s in sources),last_window_end=max(s['window_end'] for s in sources),
            independent_target_days=len({instant(s['window_start']).astimezone(ZoneInfo('America/Denver')).date() for s in sources if s['eligible_bins']}),baseline_mae_w=None if not weight else baseline/weight,candidate_mae_w=None if not weight else candidate/weight)
        if component:
            group['local_target_dates']=len({instant(s['window_start']).astimezone(ZoneInfo(group.get('target_timezone','America/Denver'))).date() for s in sources if s['eligible_bins']})
            group.pop('independent_target_days')
            for key in ('procedure_sha256','measurement_cohort_sha256','solar_grid_sha256','baseline_rule'):group.setdefault(key,None)
            group.setdefault('metric_population','legacy_original_five_minute_power');group.setdefault('target_timezone','America/Denver')
        rows.append(group)
    rows.sort(key=lambda r:(r['last_window_end'],r['cohort_id']),reverse=True);omitted=max(0,len(rows)-16);rows=rows[:16]
    value=dict(schema=SCHEMA,generated_at=generated_at.isoformat(),valid_until=(generated_at+timedelta(hours=2)).isoformat(),window_start=start.isoformat(),window_end=end.isoformat(),
        status='scored' if any(r['eligible_bins'] for r in rows) else 'collecting',cohorts=rows,omitted_cohort_count=omitted,scored_hours=len({at for _,at in seen}),unscored_hours=168-len({at for _,at in seen}),
        outcome_scope='qualified_low_soc_charging_controller_input_proxy',metric_basis='covered_duration_weighted_absolute_power_error',prospective_score=True,physical_calibration_qualified=False,automatic_actuation=False)
    if component:value['schema']='earthship-pv-potential-performance/v2'
    value['view_sha256']=identity(value)
    if len(canonical(value))>32768:raise ValueError('bounded public PV performance required')
    return value


def publish(state,output,*,clock=lambda:datetime.now(timezone.utc)):
    from household_native_training import directory,save
    from household_cycle_pressure import PublicationHeadroom
    state=Path(state);now=clock();end=(now-timedelta(minutes=5)).replace(minute=0,second=0,microsecond=0);start=end-timedelta(days=7);scores=[];guard=PublicationHeadroom()
    database=state/'scores.sqlite3'
    if database.exists():
        _read(database,32*1024**2) # Enforce the existing owned-file boundary before SQLite opens it.
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=2) as connection:
            refs=connection.execute('SELECT start,score_sha256,model_sha256 FROM hours WHERE start>=? AND start<? ORDER BY start LIMIT 169',(start.isoformat(),end.isoformat())).fetchall()
        if len(refs)>168:raise ValueError('bounded one-score-per-hour PV index required')
        for at,pin,model in refs:
            guard.check();score=json.loads(_read(state/(digest(pin)+'.score.json'),262144))
            if score['score_sha256']!=pin or score['model_sha256']!=model or score['window_start']!=at:raise ValueError('original PV score index differs')
            scores.append(score)
    view=build_view(scores,generated_at=now);output=Path(output);directory(output.parent);save(output,view)
    return dict(status='pv_performance_published',view_sha256=view['view_sha256'],cohorts=len(view['cohorts']),eligible_bins=sum(r['eligible_bins'] for r in view['cohorts']),automatic_actuation=False)
