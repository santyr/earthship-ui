"""Residual calibration is development learning, never release qualification."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import pytest

from test_installed_shade_origin import candidate, prepared, original, ISSUE
from test_installed_shade_qualification import source_case
from thermal_model.installed_shade_artifact import _digest


def module():
    from thermal_model import installed_shade_calibration
    return installed_shade_calibration


def rows(days=35, regimes=('warm',)):
    result=[]
    for r,regime in enumerate(regimes):
        for hours in (1,6,12,24):
            for day in range(days):
                issue=ISSUE+timedelta(days=r*days+day)
                result.append(dict(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=hours)).isoformat(),
                    horizon_hours=hours,regime=regime,model_error_f=float(day)))
    return result


def test_order_statistic_is_finite_sample_rank_not_interpolation_or_clipping():
    result=module()._summarize(rows(),regimes=['warm'])
    # n=35: ceil((n+1)*.9)=33; the 33rd sorted absolute residual is 32.
    assert result['complete'] is True
    for hours in ('1','6','12','24'):
        assert result['bands'][hours]['overall']['radius_f']==32.
        assert result['bands'][hours]['regimes']['warm']['radius_f']==32.
        assert result['bands'][hours]['overall']['order_statistic_rank']==33


def test_sparse_history_reports_insufficient_bands_instead_of_claiming_calibration():
    result=module()._summarize(rows(34),regimes=['warm'])
    assert result['complete'] is False
    assert result['bands']['24']['overall']['radius_f'] is None
    assert result['bands']['24']['overall']['independent_days']==34


def test_dense_intraday_windows_cannot_inflate_independent_days():
    values=[]
    for index in range(36):
        issue=ISSUE+timedelta(minutes=20*index)
        values.append(dict(issue_at=issue.isoformat(),target_at=(issue+timedelta(hours=1)).isoformat(),
            horizon_hours=1,regime='warm',model_error_f=100. if index else 2.))
    result=module()._summarize(values,regimes=['warm'])
    assert result['bands']['1']['overall']['raw_pairs']==36
    assert result['bands']['1']['overall']['independent_days']==1
    assert result['bands']['1']['overall']['radius_f'] is None
    assert result['complete'] is False


def test_each_declared_regime_requires_its_own_independent_support():
    result=module()._summarize(rows(regimes=('warm','winter'))[:-1],regimes=['warm','winter'])
    assert result['bands']['24']['overall']['radius_f'] is not None
    assert result['bands']['24']['regimes']['warm']['radius_f']==32.
    assert result['bands']['24']['regimes']['winter']['radius_f'] is None
    assert result['complete'] is False


def test_absolute_residuals_include_both_error_directions():
    values=rows()
    for row in values:row['model_error_f']*=-1
    assert module()._summarize(values,regimes=['warm'])['bands']['1']['overall']['radius_f']==32.


@pytest.mark.parametrize('damage',['unknown','nan','duplicate','future','wrong_horizon'])
def test_bad_residual_rows_refuse_calibration(damage):
    values=rows()
    if damage=='unknown':values[0]['regime']='unknown'
    elif damage=='nan':values[0]['model_error_f']=float('nan')
    elif damage=='duplicate':values.append(values[0])
    elif damage=='future':values[0]['target_at']=values[0]['issue_at']
    else:values[0]['horizon_hours']=2
    with pytest.raises(ValueError):module()._summarize(values,regimes=['warm'])


def create(candidate,source_case,**overrides):
    packet,_,assessed=source_case
    options=dict(bundle=candidate[0],inputs=candidate[1],expected_runtime_revision=_digest(candidate[2]),
        original_pairs=[packet],calibration_start=ISSUE,calibration_end=ISSUE+timedelta(hours=1),
        regimes=['warm'],created_at=assessed)
    options.update(overrides)
    return module().build_calibration(**options)


def test_calibration_replays_original_forecast_publication_outcome_and_native_fit(candidate,source_case):
    result=create(candidate,source_case)
    assert result['schema']=='earthship-installed-shade-calibration/v1'
    assert result['base_candidate_sha256']==candidate[0]['artifact']['artifact_sha256']
    assert result['runtime_sha256']==_digest(candidate[2])
    assert result['sensor_epochs']==candidate[0]['artifact']['sensor_epochs']
    assert result['summary']['bands']['1']['overall']['raw_pairs']==1
    assert result['summary']['bands']['1']['overall']['independent_days']==1
    assert result['summary']['bands']['24']['overall']['raw_pairs']==0
    assert result['summary']['complete'] is False
    assert result['release_authorized'] is False
    assert result['coverage_guaranteed'] is False
    assert result['source_pair_bindings'][0]['original_capture_sha256']


@pytest.mark.parametrize('damage',['training_overlap','outside_end','creation','summary_only','duplicate_packet','publication','phase'])
def test_calibration_cannot_use_training_release_or_altered_issued_evidence(candidate,source_case,damage):
    packet=deepcopy(source_case[0]);changes={}
    if damage=='training_overlap':changes['calibration_start']=candidate[0]['artifact']['trained_from']
    elif damage=='outside_end':changes['calibration_end']=ISSUE+timedelta(minutes=30)
    elif damage=='creation':changes['created_at']=ISSUE+timedelta(minutes=30)
    elif damage=='summary_only':packet={'model_error_f':0,'calibration_passed':True}
    elif damage=='duplicate_packet':changes['original_pairs']=[packet,packet]
    elif damage=='publication':packet['publication']['state']='{"status":"forecast_active"}'
    else:packet['outcome']['receipt']['sensorEpoch']='wrong'
    changes.setdefault('original_pairs',[packet])
    with pytest.raises(ValueError):create(candidate,source_case,**changes)


def test_rehashed_band_and_source_index_tampering_refused(candidate,source_case):
    record=create(candidate,source_case);m=module();packet=source_case[0]
    for change in ('radius','source'):
        altered=deepcopy(record)
        if change=='radius':altered['summary']['bands']['1']['overall']['radius_f']=0.
        else:altered['source_packets_sha256']='a'*64
        altered['calibration_sha256']=_digest({k:v for k,v in altered.items() if k!='calibration_sha256'})
        with pytest.raises(ValueError):m.validate_calibration(altered,bundle=candidate[0],inputs=candidate[1],
            expected_runtime_revision=_digest(candidate[2]),original_pairs=[packet],assessed_at=source_case[2])


def test_private_calibration_storage_replays_original_retained_sources(tmp_path,candidate,source_case):
    m=module();tmp_path.chmod(0o700);root=tmp_path/'calibration';root.mkdir(mode=0o700)
    record=create(candidate,source_case)
    path=m.write_calibration(root,record,bundle=candidate[0],inputs=candidate[1],
        expected_runtime_revision=_digest(candidate[2]),original_pairs=[source_case[0]],assessed_at=source_case[2])
    assert path.stat().st_mode&0o777==0o600
    for member in root.iterdir():assert member.stat().st_mode&0o777==0o600
    assert m.read_calibration(path,expected_runtime_revision=_digest(candidate[2]),assessed_at=source_case[2])==record
    assert list(root.glob('*.installed-shade-origin-v1.json'))
    assert list(root.glob('*.training-inputs-v2.json'))
    assert list(root.glob('*.installed-shade-candidate-v1.json'))
    index=root/(record['source_packets_sha256']+'.installed-shade-calibration-sources-v1.json')
    import json
    packets=json.loads(index.read_text())
    assert '/' not in packets[0]['origin_path']
    packets[0]['outcome']['receipt']['temperatureF']+=1
    index.write_text(json.dumps(packets))
    with pytest.raises(ValueError):m.read_calibration(path,expected_runtime_revision=_digest(candidate[2]),assessed_at=source_case[2])


def test_calibration_storage_refuses_missing_original_training_source(tmp_path,candidate,source_case):
    m=module();tmp_path.chmod(0o700);root=tmp_path/'calibration';root.mkdir(mode=0o700)
    record=create(candidate,source_case)
    path=m.write_calibration(root,record,bundle=candidate[0],inputs=candidate[1],
        expected_runtime_revision=_digest(candidate[2]),original_pairs=[source_case[0]],assessed_at=source_case[2])
    next(root.glob('*.training-inputs-v2.json')).unlink()
    with pytest.raises((OSError,ValueError)):m.read_calibration(path,expected_runtime_revision=_digest(candidate[2]),assessed_at=source_case[2])


def test_regime_bands_cannot_choose_a_later_issue_from_the_same_local_day():
    values=rows()
    extra=[]
    for row in values:
        if row['horizon_hours']==1:
            issue=datetime.fromisoformat(row['issue_at'])+timedelta(hours=2)
            extra.append({**row,'issue_at':issue.isoformat(),'target_at':(issue+timedelta(hours=1)).isoformat(),'regime':'winter'})
    result=module()._summarize(values+extra,regimes=['warm','winter'])
    assert result['bands']['1']['regimes']['warm']['radius_f']==32.
    assert result['bands']['1']['regimes']['winter']['raw_pairs']==35
    assert result['bands']['1']['regimes']['winter']['independent_days']==0
    assert result['bands']['1']['regimes']['winter']['radius_f'] is None


def test_spring_clock_change_cannot_count_overlapping_daily_24h_origins():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    values=[];begin=datetime(2026,3,1,12,tzinfo=ZoneInfo('America/Denver'))
    for day in range(35):
        issue=begin+timedelta(days=day)
        # The horizon is elapsed UTC time; the next local noon at spring DST
        # arrives after 23 hours, so it cannot count as a separate 24h window.
        utc=issue.astimezone(timezone.utc)
        values.append(dict(issue_at=utc.isoformat(),target_at=(utc+timedelta(hours=24)).isoformat(),
            horizon_hours=24,regime='warm',model_error_f=float(day)))
    result=module()._summarize(values,regimes=['warm'])
    assert result['bands']['24']['overall']['raw_pairs']==35
    assert result['bands']['24']['overall']['independent_windows']==34
    assert result['bands']['24']['overall']['radius_f'] is None


@pytest.mark.skipif(os.environ.get('CI')!='true',reason='multiweek synthetic source replay runs in hosted CI')
def test_synthetic_multiday_original_source_replay_learns_all_required_bands(tmp_path,candidate,prepared):
    # This is software integration, never genuine household/release evidence.
    import json
    import test_installed_shade_origin as fixtures
    from thermal_model import installed_shade_origin as origin
    tmp_path.chmod(0o700);packets=[]
    for day in range(36):
        at=ISSUE+timedelta(days=day)
        grids={hours:synthetic_cycle_grid(at,hours) for hours in (1,6,12,24)}
        if not all(grids.values()):continue
        residual=len(packets)//4
        current,proof=fixtures.native(at)
        capture=origin.build_issued_capture(prepared,issued_at=at,inputs_available_at=at,
            published_at=at+timedelta(seconds=2),runtime=candidate[2],forecast=fixtures.weather(at),
            current=current,origin_temperatures=proof,action_snapshot=fixtures.actions(at))
        path=origin.write_issued_capture(tmp_path,capture)
        for hours in (1,6,12,24):
            target=at+timedelta(hours=hours)
            point=next(p for p in capture['output']['trajectory'] if p['at']==target.isoformat())
            grid=grids[hours]
            packets.append(dict(origin_path=str(path),publication=dict(
                time=int((at+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(capture['output'])),
                horizon_hours=hours,outcome=dict(target_at=target.isoformat(),receipt=fixtures.outcome(target,point['air_f']-residual)),
                recent_cycle_grid=grid))
    result=module().build_calibration(bundle=candidate[0],inputs=candidate[1],expected_runtime_revision=_digest(candidate[2]),
        original_pairs=packets,calibration_start=ISSUE,calibration_end=ISSUE+timedelta(days=36),
        regimes=['warm'],created_at=ISSUE+timedelta(days=36,minutes=10))
    assert result['summary']['complete'] is True
    for hours in ('1','6','12','24'):
        cell=result['summary']['bands'][hours]['overall']
        assert cell['independent_days']==35 and cell['radius_f']==32.
    assert result['release_authorized'] is False and result['coverage_guaranteed'] is False

    # Complete public preparation/read/issue integration uses the same retained
    # synthetic sources; it remains unqualified (short core-fit evidence).
    from thermal_model import installed_shade_calibrated_artifact as aggregate
    from thermal_model import installed_shade_calibrated_origin as calibrated_origin
    from test_installed_shade_calibrated import runtime as new_runtime
    runtime=new_runtime(candidate);created=ISSUE+timedelta(days=36,minutes=10)
    artifact=aggregate.build_calibrated_candidate(base_bundle=candidate[0],inputs=candidate[1],calibration=result,
        original_pairs=packets,base_runtime=candidate[2],runtime=runtime,created_at=created)
    root=tmp_path/'aggregate';root.mkdir(mode=0o700)
    path=aggregate.write_calibrated_candidate(root,artifact,base_bundle=candidate[0],inputs=candidate[1],calibration=result,
        original_pairs=packets,expected_runtime_revision=_digest(runtime),assessed_at=created)
    assert aggregate.read_calibrated_candidate(path,expected_runtime_revision=_digest(runtime),assessed_at=created)['artifact']==artifact
    prepared2=calibrated_origin.prepare_calibrated_candidate(artifact,base_bundle=candidate[0],inputs=candidate[1],calibration=result,
        original_pairs=packets,expected_runtime_revision=_digest(runtime),assessed_at=created)
    at=ISSUE+timedelta(days=37);current,proof=fixtures.native(at)
    issued=calibrated_origin.build_calibrated_capture(prepared2,issued_at=at,inputs_available_at=at,published_at=at+timedelta(seconds=2),
        runtime=runtime,forecast=fixtures.weather(at),current=current,origin_temperatures=proof,action_snapshot=fixtures.actions(at))
    assert issued['output']['schema']=='earthship-installed-shade-forecast/v2'
    assert issued['output']['prediction_intervals'][0]['nominal_coverage']==.9
    assert issued['output']['release_authorized'] is False


def synthetic_cycle_grid(at,hours):
    import test_installed_shade_origin as fixtures
    from thermal_model.recent_cycles import shifted_clock, POLICY
    target=at+timedelta(hours=hours);values={};count=0
    for lag in range(1,POLICY['lookback_days']+1):
        begin,end=shifted_clock(at,lag),shifted_clock(target,lag)
        if (begin is None or end is None or not begin<end<at or end-begin!=target-at):continue
        for time in (begin,end):values[time]=fixtures.outcome(time,74.)
        count+=1
        if count==POLICY['required_cycles']:break
    return [[time.isoformat(),receipt] for time,receipt in sorted(values.items())] if count==7 else []


def test_synthetic_cycle_grid_preserves_same_local_clocks_after_fall_transition():
    from thermal_model.recent_cycles import compare_v2
    from test_installed_shade_inputs import EPOCHS
    issue=datetime(2026,11,1,18,tzinfo=timezone.utc)
    native={datetime.fromisoformat(at):{**receipt,**{key:datetime.fromisoformat(receipt[key]) for key in
        ('receivedAt','storedAt','validUntil')}} for at,receipt in synthetic_cycle_grid(issue,24)}
    result=compare_v2(issue=issue,target=issue+timedelta(hours=24),current_f=74.,sensor_epoch=EPOCHS['air'],
        grid_reader=lambda targets,assessed:[(at,native.get(at)) for at in targets])
    assert result['status']=='available'
    assert result['qualified_cycles']==7
    assert datetime(2026,10,30,17,tzinfo=timezone.utc) in native


def test_synthetic_cycle_grid_withholds_elapsed_duration_mismatch_at_fall_transition():
    issue=datetime(2026,10,31,18,tzinfo=timezone.utc)
    assert synthetic_cycle_grid(issue,24)==[]
