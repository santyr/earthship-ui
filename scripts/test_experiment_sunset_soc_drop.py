from datetime import date, datetime, timedelta, timezone
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from hashlib import sha256
import json

import pytest

spec = spec_from_file_location('sunset_experiment', Path(__file__).with_name('experiment-sunset-soc-drop.py'))
experiment = module_from_spec(spec); spec.loader.exec_module(experiment)


def test_sunset_selection_uses_only_original_available_same_day_context():
    sunset = datetime(2026, 9, 26, 0, 55, tzinfo=timezone.utc)
    origin = sunset+timedelta(hours=12)
    rows = [(sunset-timedelta(hours=12), sunset.isoformat()),
            (origin+timedelta(seconds=1), (sunset+timedelta(seconds=1)).isoformat())]
    assert experiment.sunset_at(rows, date(2026, 9, 25), origin) == rows[0][:1]+(sunset,)
    assert experiment.sunset_at(rows, date(2026, 9, 24), origin) is None
    with pytest.raises(ValueError): experiment.sunset_at(rows+rows, date(2026, 9, 25), origin)


def test_typed_postgresql_timestamp_preserves_offset_and_refuses_naive_value():
    sunset = datetime(2026, 9, 26, 0, 55, tzinfo=timezone.utc)
    persisted = sunset-timedelta(hours=12)
    assert experiment.sunset_at([(persisted, sunset)], date(2026, 9, 25), sunset) == (persisted, sunset)
    with pytest.raises(ValueError):
        experiment.sunset_at([(persisted, sunset.replace(tzinfo=None))], date(2026, 9, 25), sunset)


def test_counterfactual_preserves_dusk_cloud_penalty_and_rounding():
    record = {'dusk_soc_estimate_pct':78.411, 'tomorrow_cloud_drop_penalty_pct':2,
              'overnight_drop_final_pct':15.667, 'trough':63}
    assert experiment.counterfactual(record, [{'drop_pct':10}, {'drop_pct':12}, {'drop_pct':11}]) == (63, 65)
    assert record['trough'] == 63
    record['trough'] = 64
    with pytest.raises(ValueError): experiment.counterfactual(record, [{'drop_pct':11}]*3)


@pytest.mark.parametrize('drop', [-1, float('nan'), 101, True])
def test_bad_measured_drops_are_not_clamped_into_valid_training_inputs(drop):
    record = {'dusk_soc_estimate_pct':99, 'tomorrow_cloud_drop_penalty_pct':0,
              'overnight_drop_final_pct':15, 'trough':84}
    with pytest.raises(ValueError): experiment.counterfactual(record, [{'drop_pct':drop}]*3)


def late_fixture():
    morning = '2026-10-01T12:40:30.513835+00:00'
    record = {'temperature_issued_at': morning, 'dusk_soc_estimate_pct': 74.458,
              'tomorrow_cloud_drop_penalty_pct': 0, 'overnight_drop_final_pct': 22.333,
              'trough': 52, 'overnight_drop_sample_days': ['2026-09-30','2026-09-29','2026-09-28']}
    late = {'issuedAt': '2026-10-01T23:30:00.073215+00:00', 'morningIssuedAt': morning,
            'socAtIssuePct': 88., 'overnightDropPct': 22.333, 'overnightTroughSocPct': 66}
    profiles = [{'prediction_day': day, 'drop_pct': drop, 'as_of': morning,
                 'coverage': .999, 'canonical_coverage': .999, 'evidence_digest': str(index)*64}
                for index,(day,drop) in enumerate([('2026-09-29',17.),('2026-09-28',15.),('2026-09-27',14.)],1)]
    return record, profiles, late


def test_pre_dusk_counterfactual_preserves_source_soc_and_original_inputs():
    record, profiles, late = late_fixture()
    before = deepcopy((record, profiles, late))
    result = experiment.pre_dusk_counterfactual(record, profiles, late)
    assert result['baseline_pct'] == 66
    assert result['candidate_pct'] == 73
    assert result['candidate_drop_pct'] == 15.333
    assert result['soc_at_issue_pct'] == 88.
    assert result['future_outcome_used_as_input'] is False
    assert (record, profiles, late) == before


@pytest.mark.parametrize('damage', ['later_profile','wrong_day','poor_coverage','bad_digest',
                                  'morning_link','drop_link','baseline','bad_soc','late_clock',
                                  'duplicate_days','unordered_days'])
def test_pre_dusk_counterfactual_refuses_unqualified_or_substituted_origins(damage):
    record, profiles, late = late_fixture()
    if damage == 'later_profile': profiles[0]['as_of'] = late['issuedAt']
    elif damage == 'wrong_day': profiles[0]['prediction_day'] = '2026-09-30'
    elif damage == 'poor_coverage': profiles[0]['coverage'] = .99
    elif damage == 'bad_digest': profiles[0]['evidence_digest'] = 'not-bound'
    elif damage == 'morning_link': late['morningIssuedAt'] = '2026-10-01T12:41:00+00:00'
    elif damage == 'drop_link': late['overnightDropPct'] = 20.
    elif damage == 'baseline': late['overnightTroughSocPct'] = 65
    elif damage == 'bad_soc': late['socAtIssuePct'] = True
    elif damage == 'late_clock': late['issuedAt'] = late['morningIssuedAt']
    elif damage == 'duplicate_days':
        record['overnight_drop_sample_days'][1] = record['overnight_drop_sample_days'][0]
        profiles[1] = deepcopy(profiles[0])
    else:
        record['overnight_drop_sample_days'].reverse()
        profiles.reverse()
    with pytest.raises(ValueError):
        experiment.pre_dusk_counterfactual(record, profiles, late)


def test_pre_dusk_counterfactual_uses_positive_math_round_half_ties():
    record, profiles, late = late_fixture()
    for profile in profiles: profile['drop_pct'] = 15.5
    late['socAtIssuePct'] = 88.
    assert experiment.pre_dusk_counterfactual(record, profiles, late)['candidate_pct'] == 73


def phase_comparison_fixture():
    record, profiles, late = late_fixture()
    late['sunsetAt'] = '2026-10-02T00:45:00.073215+00:00'
    for profile in profiles:
        sunset = datetime.fromisoformat(profile['prediction_day']+'T19:00:00-06:00')
        profile.update(profile_version='pre-dusk-phase-soc-v1', lead_seconds=4500.,
            sunset_at=sunset.isoformat(), phase_start_at=(sunset-timedelta(minutes=75)).isoformat(),
            sunset_persisted_at=(sunset-timedelta(hours=12)).isoformat())
    return record, profiles, late


def test_phase_comparison_is_explicitly_bound_to_original_late_lead():
    record, profiles, late = phase_comparison_fixture()
    result = experiment.phase_matched_counterfactual(record, profiles, late)
    assert result['candidate_pct'] == 73 and result['phase_lead_seconds'] == 4500.
    assert result['input_phase_starts'] == [p['phase_start_at'] for p in profiles]
    assert result['profile_basis'] == 'pre-dusk-phase-soc-v1'


@pytest.mark.parametrize('damage', ['lead','version','start','late_sunset','sunset_day','future_context'])
def test_phase_comparison_refuses_mismatched_phase_and_sunset_context(damage):
    record, profiles, late = phase_comparison_fixture()
    if damage == 'lead': profiles[0]['lead_seconds'] += 1
    elif damage == 'version': profiles[0]['profile_version'] = 'sunset-soc-profile-v1'
    elif damage == 'start': profiles[0]['phase_start_at'] = profiles[0]['sunset_at']
    elif damage == 'late_sunset': late['sunsetAt'] = late['issuedAt']
    elif damage == 'sunset_day': profiles[0]['sunset_at'] = profiles[1]['sunset_at']
    else: profiles[0]['sunset_persisted_at'] = profiles[0]['sunset_at']
    with pytest.raises(ValueError): experiment.phase_matched_counterfactual(record, profiles, late)


def charge_input_fixture():
    weather=datetime(2026,10,2,12,40,30,513835,tzinfo=timezone.utc)
    assessed=weather.replace(microsecond=519000)
    observed=assessed-timedelta(seconds=10)
    stamp=lambda at:int(at.timestamp()*1000)
    raw=json.dumps({'version':1,'streamEpoch':'123e4567-e89b-42d3-a456-426614174000',
        'recordedAt':stamp(observed),'status':'valid','reason':'ok',
        'observedAt':stamp(observed),'scaleObservedAt':stamp(observed),
        'validUntil':stamp(observed+timedelta(seconds=120)),'soc':79})
    origin={'version':1,'assessedAtMs':stamp(assessed),'recordedAtMs':stamp(observed),
        'validUntilMs':stamp(observed+timedelta(seconds=120)),
        'streamEpoch':'123e4567-e89b-42d3-a456-426614174000',
        'evidenceSha256':sha256(raw.encode()).hexdigest(),'socPct':79}
    record={'temperature_issued_at':weather.isoformat(),'soc_origin':origin,'soc_reference_pct':79}
    receipt={'issuedAt':weather.isoformat(),'energySocOrigin':deepcopy(origin)}
    return record,receipt,[(observed+timedelta(seconds=1),raw)],assessed


def test_charge_assessment_keeps_the_later_atomic_clock_without_mutating_origins():
    record,receipt,rows,assessed=charge_input_fixture()
    before=deepcopy((record,receipt,rows))
    assert experiment.verify_charge_input(record,receipt,rows)==assessed
    assert assessed>datetime.fromisoformat(record['temperature_issued_at'])
    assert (record,receipt,rows)==before


@pytest.mark.parametrize('fault',['missing_public','bool_version','bool_public_version','bool_clock',
    'expired','future_recorded','bad_digest','soc_mismatch','weather_backdate','weather_naive',
    'assessment_too_late','different_weather_issue','extra_origin_field','wrong_stream','altered_expiry',
    'later_fault','duplicate','only_future_source','wrong_digest'])
def test_charge_input_refuses_unqualified_origins_or_source_substitutions(fault):
    record,receipt,rows,assessed=charge_input_fixture()
    origin=record['soc_origin']
    if fault=='missing_public':receipt.pop('energySocOrigin')
    elif fault=='bool_public_version':receipt['energySocOrigin']['version']=True
    elif fault=='bool_version':origin['version']=True
    elif fault=='bool_clock':origin['assessedAtMs']=True
    elif fault=='expired':origin['validUntilMs']=origin['assessedAtMs']
    elif fault=='future_recorded':origin['recordedAtMs']=origin['assessedAtMs']+1
    elif fault=='bad_digest':origin['evidenceSha256']='unbound'
    elif fault=='soc_mismatch':record['soc_reference_pct']=80
    elif fault=='weather_backdate':record['temperature_issued_at']=(assessed+timedelta(seconds=1)).isoformat()
    elif fault=='weather_naive':record['temperature_issued_at']='2026-10-02T12:40:30'
    elif fault=='assessment_too_late':origin['assessedAtMs']+=121000;origin['validUntilMs']+=121000
    elif fault=='different_weather_issue':receipt['issuedAt']='2026-10-02T12:39:00+00:00'
    elif fault=='extra_origin_field':origin['extra']='unreviewed'
    elif fault=='wrong_stream':origin['streamEpoch']='123e4567-e89b-42d3-a456-426614174001'
    elif fault=='altered_expiry':origin['validUntilMs']+=1000
    elif fault=='later_fault':rows.append((assessed-timedelta(seconds=1),'{}'))
    elif fault=='duplicate':rows.append(rows[0])
    elif fault=='only_future_source':rows=[(assessed+timedelta(seconds=1),rows[0][1])]
    else:origin['evidenceSha256']='a'*64
    if fault not in ('missing_public','bool_public_version','different_weather_issue'):
        receipt['energySocOrigin']=deepcopy(origin)
    if fault in ('weather_backdate','weather_naive'):
        receipt['issuedAt']=record['temperature_issued_at']
    with pytest.raises(ValueError):experiment.verify_charge_input(record,receipt,rows)


@pytest.mark.parametrize('charge_only', [True, False])
@pytest.mark.parametrize('missing_charge_origin', [False, True])
def test_cli_charge_outcome_requires_original_atomic_input_in_both_modes(
        monkeypatch,tmp_path,capsys,charge_only,missing_charge_origin):
    from types import SimpleNamespace
    import forecast_intel
    import psycopg2
    from earthship_energy import db as db_module, materialize, reader
    record,receipt,rows,assessed=charge_input_fixture()
    sunset=assessed+timedelta(hours=12)
    now=sunset+timedelta(minutes=1)
    assert not experiment.trough_window(date(2026,10,2),'America/Denver').is_complete(now)
    if not charge_only:
        now=assessed+timedelta(hours=30)
        record.update(overnight_drop_sample_days=['2026-10-01','2026-09-30','2026-09-29'],
                      overnight_drop_samples_pct=[20,20,20],dusk_soc_estimate_pct=99)
        monkeypatch.setattr(experiment,'counterfactual',lambda *a:(80,84))
        def measured(**kwargs):
            return dict(trough_soc_pct=79,drop_pct=20,sunset_soc_pct=79,coverage=1,
                        evidence_digest='a'*64)
        monkeypatch.setattr(experiment,'measure',measured)
        from earthship_energy import trough_assessment
        monkeypatch.setattr(trough_assessment,'assess_trough_measurement',lambda **k:
            dict(status='measured',min_soc_pct=70,evidence_digest='b'*64))
        monkeypatch.setattr(experiment,'sunset_at',lambda rows,day,origin:
            (assessed-timedelta(days=4),sunset-timedelta(days=(date(2026,10,2)-day).days)))
    record['trough']=80
    receipt.update(version=1,predictionDay='2026-10-02',overnightTroughSocPct=80)
    if missing_charge_origin:
        receipt.pop('energySocOrigin')
    for second in range(30,12*3600+1,30):
        at=assessed+timedelta(seconds=second)
        value=json.loads(rows[0][1]); stamp=int(at.timestamp()*1000)
        for key in ('recordedAt','observedAt','scaleObservedAt'):value[key]=stamp
        value['validUntil']=stamp+120000
        rows.append((at,json.dumps(value)))
    if not charge_only:
        # Later overnight observations must not alter the charge-target digest.
        later=sunset+timedelta(seconds=30)
        value=json.loads(rows[-1][1]);stamp=int(later.timestamp()*1000)
        for key in ('recordedAt','observedAt','scaleObservedAt'):value[key]=stamp
        value.update(validUntil=stamp+120000,soc=78)
        rows.append((later,json.dumps(value)))
    path=tmp_path/'state.json';path.write_text(json.dumps({'predictions':{'2026-10-02':record}}))
    monkeypatch.setattr(forecast_intel,'STATE_FILE',str(path))
    before=path.read_bytes()
    monkeypatch.setattr(experiment.sys,'argv',['benchmark','--start-day','2026-10-02',
        '--end-day','2026-10-03']+(['--charge-only'] if charge_only else []))
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return now
    monkeypatch.setattr(experiment,'datetime',Clock)
    monkeypatch.setattr(experiment,'read_day_issues',lambda *a,**k:[{'receipt':receipt}])
    monkeypatch.setattr(db_module,'parse_openhab_jdbc_config',lambda *_:SimpleNamespace(
        host='127.0.0.1',port=5432,dbname='openhab',user='energy_power_reader',connect_kwargs={}))
    monkeypatch.setattr(materialize,'load_epoch_config',lambda:[SimpleNamespace(
        current_analytics=True,start_local_date=date(2026,7,19),end_local_date_exclusive=None)])
    monkeypatch.setattr(reader,'fetch_freshness_observations',lambda *a,**k:rows)
    calls=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):
            calls.append((str(sql),params))
            self.result=[(1 if params[0]=='Sun_Set_Start' else 613,)] if str(sql).startswith(
                'SELECT itemid') else [(
                    Clock.fromtimestamp((assessed-timedelta(hours=6)).timestamp(),timezone.utc),
                    Clock.fromtimestamp(sunset.timestamp(),timezone.utc))]
        def fetchall(self):return self.result
    class Database:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def set_session(self,**kwargs):assert kwargs['readonly'] is True
        def cursor(self):return Cursor()
    monkeypatch.setattr(psycopg2,'connect',lambda *a,**k:Database())
    experiment.main()
    result=json.loads(capsys.readouterr().out)
    assert result['assessment_mode']==('charge_only' if charge_only else 'overnight_counterfactual')
    if missing_charge_origin:
        assert result['counts']['charge_origin_or_outcome_unavailable']==1
        if charge_only:
            assert not result['rows']
        else:
            assert result['rows'][0]['charge_profile'] is None
            assert result['rows'][0]['actual_trough_pct']==70
    else:
        assert result['rows'][0]['charge_profile']['status']=='no_full_report'
        profile=result['rows'][0]['charge_profile']
        assert profile['soc_assessed_at']==assessed.isoformat()
        assert profile['weather_origin']==record['temperature_issued_at']
        assert profile['soc_input_digest']==record['soc_origin']['evidenceSha256']
        assert profile['evidence_digest']==experiment.charge_profile(day=date(2026,10,2),
            origin=assessed,sunset=sunset,sunset_persisted_at=(
                assessed-timedelta(hours=6) if charge_only else assessed-timedelta(days=4)),
            as_of=now,observations=[row for row in rows if row[0]<=sunset],
            epoch_start=datetime(2026,7,19,6,tzinfo=timezone.utc))['evidence_digest']
    assert result['production_changed'] is False and path.read_bytes()==before
    assert not any(word in sql.upper().split() for sql,_ in calls
                   for word in ('INSERT','UPDATE','DELETE','DROP'))


def test_charge_only_and_overnight_modes_cannot_be_mixed(monkeypatch):
    monkeypatch.setattr(experiment.sys,'argv',['benchmark','--start-day','2026-10-01',
        '--end-day','2026-10-03','--charge-only','--include-pre-dusk'])
    with pytest.raises(SystemExit) as error:experiment.main()
    assert error.value.code==2
