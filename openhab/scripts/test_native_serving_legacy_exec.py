"""Retired legacy score entries cannot execute under a production unit."""
import pytest


def test_legacy_exec_is_removed():
    import household_forecast_score as coordinator
    assert not hasattr(coordinator,'execute_legacy_score')


@pytest.mark.parametrize('changed',['manifest','config'])
def test_no_retained_legacy_context_can_execute(changed,tmp_path,monkeypatch):
    import household_forecast_score as coordinator,household_cycle_deploy as deploy
    def forbidden(*args,**kwargs):pytest.fail('retired dependency context was opened')
    monkeypatch.setattr(deploy,'_path',forbidden)
    with pytest.raises(ValueError,match='Google-only'):
        coordinator.run_retained_worker(tmp_path/'old.py',tmp_path/'old.json',stage=tmp_path,
            deployment_sha256='a'*64,retained_native=False)
