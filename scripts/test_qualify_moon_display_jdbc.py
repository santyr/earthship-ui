import importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('moon_display_jdbc_test',Path(__file__).with_name('qualify-moon-display-jdbc.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_quantity_equality_keeps_units_and_rejects_nonfinite():
 assert m.same_state('12.500 °','12.5 °','Number:Angle')
 assert not m.same_state('12.5 rad','12.5 °','Number:Angle')
 assert not m.same_state('NaN °','NaN °','Number:Angle')
 assert m.same_state('0.5000','0.5','Number:Dimensionless')
 assert not m.same_state('50 %','0.5','Number:Dimensionless')

def test_datetime_instant_equality_and_exact_string_contract():
 assert m.same_state('2026-10-08T13:00:00.000+0000','2026-10-08T07:00:00-0600','DateTime')
 assert not m.same_state('NULL','NULL','DateTime')
 assert m.same_state('Aries','Aries','String')
 assert not m.same_state('Aries','ARIES','String')

def test_jdbc_fixture_preserves_live_us_unit_context_before_all_quantity_states(monkeypatch,tmp_path):
 seen=[]
 monkeypatch.setattr(m.batch,'checked_source',lambda *_:b'source')
 monkeypatch.setattr(m.batch,'private_file',lambda *_:None)
 monkeypatch.setattr(m.rehearsal,'main',lambda **kw:seen.append(kw))
 m.main(['--report',str(tmp_path/'report.json')])
 fixtures=dict(seen[0]['setup_sources'])
 assert b'org.openhab.i18n:measurementSystem=US' in fixtures['services/regional.cfg']
 assert b'org.openhab.i18n:region=US' in fixtures['services/regional.cfg']
 assert seen[0]['items']['Moon_Apogee_Distance']=='0.5 in'

def test_unitless_persistence_dto_is_compared_in_exact_frozen_item_unit():
 raw=[{'time':123,'state':'0.5'}]
 assert m.normalize_history(raw,'Moon_Apogee_Distance')==[{'time':123,'state':'0.5 in'}]
 assert raw==[{'time':123,'state':'0.5'}]
 assert m.normalize_history([{'time':123,'state':'0.5 m'}],'Moon_Apogee_Distance')[0]['state']=='0.5 m'
 assert not m.same_state('0.5 m','0.5 in','Number:Length')
 assert m.normalize_history(raw,'Moon_Phase_AgePercent')==raw
