"""Frequent replay callbacks must not repeatedly poll the kernel."""
import pytest


def monitor(tmp_path):
    from native_inference_pressure import NativeInferenceHeadroom
    from household_forecast_score import SampledScorePressure
    vmstat=tmp_path/'vmstat';vmstat.write_text('oom_kill 0\n')
    events=tmp_path/'memory.events';events.write_text('max 0\noom 0\noom_kill 0\n')
    ticks=[0.];samples=[]
    pressure=NativeInferenceHeadroom(vmstat=vmstat,memory_events=events,
        resource_check=lambda:samples.append(ticks[0]))
    sampled=SampledScorePressure(pressure,monotonic=lambda:ticks[0])
    return sampled,ticks,samples,events


def test_replay_callbacks_sample_once_per_second_without_starving_checks(tmp_path):
    sampled,ticks,samples,events=monitor(tmp_path)
    sampled.check()
    for i in range(1,10000):
        ticks[0]=i/10000;sampled.check()
    assert samples==[0.]
    events.write_text('max 1\noom 0\noom_kill 0\n')
    ticks[0]=1.
    with pytest.raises(ValueError,match='memory-limit counters changed'):sampled.check()


def test_job_boundary_checks_even_inside_sampling_interval(tmp_path):
    sampled,ticks,_,events=monitor(tmp_path);sampled.check()
    ticks[0]=0.01;events.write_text('max 0\noom 1\noom_kill 0\n')
    with pytest.raises(ValueError,match='memory-limit counters changed'):sampled.check(force=True)


def test_sample_failure_cannot_be_skipped_by_another_callback(tmp_path):
    sampled,ticks,_,events=monitor(tmp_path);sampled.check()
    ticks[0]=1.;events.write_text('max 0\noom 1\noom_kill 0\n')
    with pytest.raises(ValueError):sampled.check()
    events.write_text('max 0\noom 0\noom_kill 0\n')
    with pytest.raises(ValueError):sampled.check()


@pytest.mark.parametrize('tick',[-1.,float('nan'),float('inf')])
def test_unknown_or_regressed_sampling_clock_refuses(tmp_path,tick):
    sampled,ticks,_,_=monitor(tmp_path);sampled.check();ticks[0]=tick
    with pytest.raises(ValueError):sampled.check()


def native_runtime(tmp_path,monkeypatch):
    import json
    import native_thermal_live
    import native_inference_pressure
    from test_household_forecast_score import runtime_setup
    config,now=runtime_setup(tmp_path,monkeypatch)
    settings=json.loads(config.read_text());settings['schema']='earthship-provisional-thermal-live-config/v2'
    config.write_text(json.dumps(settings))
    monkeypatch.setattr(native_thermal_live,'load_settings',lambda path:settings)
    sampled,ticks,samples,events=monitor(tmp_path)
    monkeypatch.setattr(native_inference_pressure,'NativeInferenceHeadroom',lambda:sampled.pressure)
    return config,now,ticks,samples,events


def test_native_job_completion_forces_fresh_pressure_check(tmp_path,monkeypatch):
    import household_forecast_score as score
    config,now,ticks,_,events=native_runtime(tmp_path,monkeypatch)
    def work(settings,*,guard,**kw):
        guard();ticks[0]=0.01;events.write_text('max 1\noom 0\noom_kill 0\n')
        return {'status':'scored'}
    monkeypatch.setattr(score,'score_with_report',work)
    with pytest.raises(ValueError,match='memory-limit counters changed'):
        score.run(config,clock=lambda:now,monotonic=lambda:ticks[0])


def test_native_deadline_is_checked_between_pressure_samples(tmp_path,monkeypatch):
    import household_forecast_score as score
    config,now,ticks,_,_=native_runtime(tmp_path,monkeypatch)
    monkeypatch.setattr(score,'SCORE_LIFETIME_SECONDS',0.25)
    def work(settings,*,guard,**kw):
        guard();ticks[0]=0.5;guard();pytest.fail('deadline skipped between samples')
    monkeypatch.setattr(score,'score_with_report',work)
    with pytest.raises(ValueError,match='score lifetime elapsed'):
        score.run(config,clock=lambda:now,monotonic=lambda:ticks[0])
