"""A useful scoring window stays bounded and leaves preparation clear."""
from datetime import datetime, timezone
import pytest
from test_native_serving_score_driver import fixture


@pytest.mark.parametrize('elapsed,accepted', [(90, True), (121, False)])
def test_score_can_finish_measured_work_but_cannot_renew_its_budget(tmp_path, monkeypatch, elapsed, accepted):
    c, config, stage, calls, model, now, dispatch = fixture(tmp_path, monkeypatch, 1)
    monkeypatch.setattr(c, 'score_role', lambda _: 'current')
    ticks = [100.]
    def score(*args, guard, **kwargs):
        ticks[0] += elapsed
        guard()
        return {'status': 'waiting'}
    monkeypatch.setattr(c, 'score_with_report', score)
    if accepted:
        assert c.run(config, stage=stage, deployment_sha256='a'*64, clock=lambda:now, monotonic=lambda:ticks[0])['status'] == 'waiting'
    else:
        with pytest.raises(ValueError, match='score lifetime'):
            c.run(config, stage=stage, deployment_sha256='a'*64, clock=lambda:now, monotonic=lambda:ticks[0])


def test_one_full_window_per_cycle_rotates_native_and_legacy():
    import household_forecast_score as c
    roles = [c.score_role(datetime(2026,10,14,18,m,0,tzinfo=timezone.utc)) for m in range(10)]
    assert roles[1] == 'current' and roles[6] == 'legacy'
    assert roles.count('reserved') == 8


def test_verified_family_preserves_old_policy_and_spaces_new_work(tmp_path):
    import household_native_family as f
    stage = tmp_path/'stage'
    script = stage/'sources/openhab/scripts/household_forecast_score.py'
    script.parent.mkdir(parents=True)
    script.write_text('# retained original coordinator\n')
    script.with_name('household_cycle.py').write_text('# retained original driver\n')
    assert f._extended_score_window(stage) is False
    script.write_text('SCORE_LIFETIME_SECONDS = 120\n')
    assert f._extended_score_window(stage) is True
    config = stage/'config.json'
    template = stage/'service.conf'
    template.write_text('[Service]\nExecStart=/usr/bin/python3 driver.py --stage '+str(stage)+'\n')
    template.chmod(0o600)
    files = f._render(stage, config, stage/'libraries.json', deployment_sha256='a'*64)
    assert b'TimeoutStartSec=130\n' in files['score.conf']
    assert files['score-timer.conf'] == b'[Timer]\nOnCalendar=\nOnCalendar=*-*-* *:01/5:00 UTC\n'
    assert b'OnCalendar=*-*-* *:03/5:05 UTC' in files['thermal-native-geometry-prepare.timer']
    assert b'CPUQuota=20%' in files['thermal-native-geometry-prepare.service']
    assert b'MemoryMax=256M' in files['thermal-native-geometry-prepare.service']


def test_extended_owned_upgrade_replaces_schedule_and_timeout_together(tmp_path, monkeypatch):
    import household_native_family as family
    from test_native_serving_upgrade import fixture as upgrade
    monkeypatch.setattr(family, '_extended_score_window', lambda stage: stage.name == 'new-stage')
    deploy, handoff, new_family, kwargs, targets, old_family = upgrade(tmp_path, monkeypatch)
    assert family.verify(old_family, guard=lambda:None)['score_service_timeout_seconds'] == 60
    assert family.verify(new_family, guard=lambda:None)['score_service_timeout_seconds'] == 130
    handoff.prepare(new_family, **kwargs)
    import household_native_install as install
    assert install._install_files(kwargs['output'], guard=lambda:None)['file_count'] == 5
    assert b'TimeoutStartSec=130' in targets['score'].read_bytes()
    assert targets['score_timer'].read_bytes() == b'[Timer]\nOnCalendar=\nOnCalendar=*-*-* *:01/5:00 UTC\n'


def test_effective_extended_family_requires_its_longer_timeout_and_single_slot(tmp_path, monkeypatch):
    import household_native_family as family
    from test_native_serving_effective import fixture as effective
    monkeypatch.setattr(family, '_extended_score_window', lambda stage:True)
    install, output, pin, states = effective(tmp_path, monkeypatch)
    states['thermal-provisional-score.service']['TimeoutStartUSec'] = '2min 10s'
    states['thermal-provisional-score.timer']['TimersCalendar'] = ['*-*-* *:01/5:00 UTC']
    assert install._verify_effective_family(output, guard=lambda:None)['deployment_sha256'] == pin
    states['thermal-provisional-score.service']['TimeoutStartUSec'] = '1min'
    with pytest.raises(ValueError, match='effective native service'):
        install._verify_effective_family(output, guard=lambda:None)


def test_inner_native_worker_allows_measured_work_within_outer_budget(monkeypatch):
    import native_thermal_live as native
    ticks = [100.]
    monkeypatch.setattr(native, 'monotonic', lambda:ticks[0])
    monkeypatch.setattr(native, '_resource_preflight', lambda:None)
    class ObservedBudget(Exception): pass
    def inspect_budget(*args, guard, **kwargs):
        ticks[0] = 190.
        assert guard() == 30.
        raise ObservedBudget()
    monkeypatch.setattr(native, '_serving_settings', inspect_budget)
    with pytest.raises(ObservedBudget):
        native.score_jobs({'schema':native.SERVING_SCHEMA}, guard=lambda:None, serving_model=object())
