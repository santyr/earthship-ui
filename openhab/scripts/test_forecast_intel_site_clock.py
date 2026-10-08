"""Forecast learning days must use the site clock, independent of host midnight."""
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo

import pytest
import forecast_intel as fi


@pytest.mark.parametrize('zone,expected',[('America/Denver',date(2026,10,6)),('America/New_York',date(2026,10,6)),('Asia/Tokyo',date(2026,10,7))])
def test_main_selects_completed_site_day_at_utc_midnight(monkeypatch,zone,expected):
    instant=datetime(2026,10,8,1,tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)
    class HostDate(date):
        @classmethod
        def today(cls):return date(2026,10,8)
    monkeypatch.setattr(fi,'datetime',Clock);monkeypatch.setattr(fi,'date',HostDate)
    monkeypatch.setattr(fi,'MOUNTAIN',ZoneInfo(zone))
    monkeypatch.setattr(fi,'load_state',lambda:{'predictions':{}})
    monkeypatch.setattr(fi,'save_state',lambda *_:None)
    import hourly_temperature_runtime
    monkeypatch.setattr(hourly_temperature_runtime,'score_runtime_hourly',lambda *_:0)
    seen=[]
    class StopBeforeQueries(RuntimeError):pass
    def observed(day):seen.append(day);raise StopBeforeQueries()
    monkeypatch.setattr(fi,'measured_day_weather_with_evidence',observed)
    with pytest.raises(StopBeforeQueries):fi.main()
    assert seen==[expected]
