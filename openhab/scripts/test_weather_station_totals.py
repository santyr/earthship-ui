from datetime import datetime,timedelta,timezone
import json
import pytest
from weather_station_rain import RainProducts
from weather_station_totals import RecordedRainTotals,replay_recorded_totals
UTC=timezone.utc
START=datetime(2026,10,22,17,tzinfo=UTC)
def test_recorded_amounts_survive_a_gap_without_assigning_gap_rain():
 s=RainProducts(timezone_name='America/Denver',validity_seconds=120,maximum_counter_in=100000)
 for offset,count in [(0,100),(60,100.02),(300,100.05),(360,100.06)]:s.observe(count,at=START+timedelta(seconds=offset),tick=offset)
 p=s.snapshot(at=START+timedelta(seconds=360),tick=360)['products']
 assert p['day']['recorded_in']==pytest.approx(.03)
 assert p['day']['value'] is None
 assert p['week']['recorded_in']==pytest.approx(.03)
 assert s.snapshot(at=START+timedelta(seconds=481),tick=481)['products']['day']['recorded_in'] is None

def test_persisted_counts_do_not_seed_current_measurements_or_count_a_restart_gap(tmp_path):
 path=tmp_path/'rain.json';s=RecordedRainTotals('America/Denver',path)
 s.observe(None,at=START,previous_at=None);s.observe(.02,at=START+timedelta(seconds=60),previous_at=START)
 restored=RecordedRainTotals('America/Denver',path)
 assert restored.periods==s.periods
 p=RainProducts(timezone_name='America/Denver',validity_seconds=120,maximum_counter_in=100000,recorded_totals=restored)
 assert p.snapshot(at=START+timedelta(seconds=120),tick=0)['products']['day']['recorded_in'] is None
 p.observe(100.09,at=START+timedelta(seconds=120),tick=0)
 assert p.snapshot(at=START+timedelta(seconds=120),tick=0)['products']['day']['recorded_in']==pytest.approx(.02)
 p.observe(100.10,at=START+timedelta(seconds=180),tick=60)
 assert p.snapshot(at=START+timedelta(seconds=180),tick=60)['products']['day']['recorded_in']==pytest.approx(.03)
 assert path.stat().st_mode&0o777==0o600

def test_calendar_rollover_never_assigns_a_straddling_increment_to_the_new_day():
 s=RecordedRainTotals('America/Denver');before=datetime(2026,10,23,5,59,50,tzinfo=UTC)
 s.observe(None,at=before,previous_at=None);s.observe(.02,at=before+timedelta(seconds=20),previous_at=before)
 assert s.periods['day']['amount_in']==0
 assert s.periods['week']['amount_in']==pytest.approx(.02)

@pytest.mark.parametrize('date,hours',[('2026-03-08',23),('2026-11-01',25)])
def test_totals_use_local_dst_boundaries(date,hours):
 from zoneinfo import ZoneInfo
 start=datetime.fromisoformat(date).replace(tzinfo=ZoneInfo('America/Denver')).astimezone(UTC)
 s=RecordedRainTotals('America/Denver');s.observe(None,at=start,previous_at=None)
 s.observe(.01,at=start+timedelta(hours=hours)-timedelta(seconds=1),previous_at=start+timedelta(hours=hours)-timedelta(seconds=61))
 s.observe(None,at=start+timedelta(hours=hours),previous_at=None)
 assert s.periods['day']['amount_in']==0

@pytest.mark.parametrize('payload',[{}, {'schema':'wrong'}, {'schema':'earthship-station-recorded-rain/v1','timezone':'America/Denver','periods':{'day':{'start':START.isoformat(),'amount_in':float('nan')}}}])
def test_corrupt_saved_totals_are_rejected(tmp_path,payload):
 path=tmp_path/'rain.json';path.write_text(json.dumps(payload));path.chmod(0o600)
 with pytest.raises(ValueError):RecordedRainTotals('America/Denver',path)

def test_replay_of_saved_openhab_receipts_recovers_real_today_and_week():
 from pathlib import Path
 fixture=json.loads((Path(__file__).parent/'fixtures/ws2902-rain-openhab-20261022.json').read_bytes())
 s=replay_recorded_totals(fixture['observations'],timezone_name='America/Denver')
 assert s.periods['day']['amount_in']==pytest.approx(.08,abs=1e-6)
 assert s.periods['week']['amount_in']==pytest.approx(.22,abs=1e-6)


def test_persistence_failure_does_not_interrupt_radio_ingestion(tmp_path,monkeypatch):
 saved=RecordedRainTotals('America/Denver',tmp_path/'rain.json')
 def fail():raise OSError('disk unavailable')
 monkeypatch.setattr(saved,'save',fail)
 p=RainProducts(timezone_name='America/Denver',validity_seconds=120,maximum_counter_in=100000,recorded_totals=saved)
 p.observe(100.,at=START,tick=0);p.observe(100.02,at=START+timedelta(seconds=60),tick=60)
 report=p.snapshot(at=START+timedelta(seconds=60),tick=60)
 assert report['products']['day']['recorded_in']==pytest.approx(.02)
 assert report['recordedPersistence']=='unavailable'


def test_a_stale_second_writer_cannot_overwrite_saved_rain(tmp_path):
 path=tmp_path/'rain.json';a=RecordedRainTotals('America/Denver',path);a.observe(None,at=START,previous_at=None)
 b=RecordedRainTotals('America/Denver',path);a.observe(.02,at=START+timedelta(seconds=60),previous_at=START)
 b.observe(.01,at=START+timedelta(seconds=60),previous_at=START)
 assert b.persistence_error is True
 assert RecordedRainTotals('America/Denver',path).periods['day']['amount_in']==pytest.approx(.02)


def test_invalid_owned_counter_packet_is_a_barrier_for_recorded_counts():
 s=RainProducts(timezone_name='America/Denver',validity_seconds=120,maximum_counter_in=100000)
 s.observe(100.,at=START,tick=0);s.observe(100.02,at=START+timedelta(seconds=30),tick=30)
 s.invalidate()
 s.observe(100.07,at=START+timedelta(seconds=60),tick=60)
 s.observe(100.08,at=START+timedelta(seconds=90),tick=90)
 assert s.snapshot(at=START+timedelta(seconds=90),tick=90)['products']['day']['recorded_in']==pytest.approx(.03)
