"""Keep independently verified performance visible across a missing outcome.

This outside-fitted coordinator preserves the original scorer and single-job
semantics. It never invents measurements, changes model parameters or acts.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import time


def score_with_report(settings,*,guard,clock=lambda:datetime.now(timezone.utc)):
    from thermal_model import provisional_monitor as monitor
    guard();now=clock();runtime=monitor.current_runtime()
    candidate=monitor.read_candidate(Path(settings['candidate_path']),assessed_at=now,runtime=runtime)
    try:return monitor.score_jobs(settings,guard=guard)
    except ValueError as error:
        if str(error)!='original mature outcome unavailable':raise
    # Original refresh replays pair validation and checks every retained source
    # fingerprint. Missing/corrupt completed originals cannot become a report.
    guard()
    report=monitor.refresh_report(settings,artifact_sha256=candidate['artifact_sha256'],now=clock(),guard=guard)
    guard()
    return dict(status='monitoring_refreshed',scored=0,
        current_revision_scored=sum(row['model']['count'] for row in report['by_horizon'].values()),
        pending_reason='mature_outcome_unavailable',automatic_actuation=False)


def run(config,*,stage=None,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    import os
    from thermal_installed_intel import _resource_preflight
    from thermal_model.provisional_live import load_settings,_next_issue
    from thermal_model.capture_guard import SharedScoreLock
    from thermal_model.training_pressure_guard import TrainingHeadroom
    from thermal_model.policy_registration import _read_private
    from household_observation import _private_file
    _resource_preflight()
    os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
    config=Path(config).absolute();original=_private_file(config,8192);settings=load_settings(config)
    own=Path(__file__).read_bytes();now=clock();issue=_next_issue(now)
    if issue-now<timedelta(seconds=90):raise BlockingIOError('forecast preparation window reserved')
    verifier=None;binding=None
    if stage is not None:
        from household_cycle_deploy import verify_stage
        stage=Path(stage).absolute();binding=verify_stage(stage);verifier=verify_stage
        if Path(__file__).resolve()!=stage/'sources/openhab/scripts/household_forecast_score.py':
            raise ValueError('staged score coordinator execution required')
    deadline=monotonic()+50
    with SharedScoreLock(settings['shared_lock']) as lock:
        pressure=TrainingHeadroom(max_swapin_bytes_per_second=1048576)
        def guard():
            lock.verify();pressure.check()
            if monotonic()>=deadline or clock()>=issue-timedelta(seconds=35):raise ValueError('score lifetime elapsed')
            if _private_file(config,8192)!=original or _read_private(config)!=settings or Path(__file__).read_bytes()!=own:
                raise ValueError('score source or configuration changed')
        result=score_with_report(settings,guard=guard,clock=clock)
        guard()
        if verifier is not None and verifier(stage)!=binding:raise ValueError('staged score runtime changed')
        return result


def main(argv=None):
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path);parser.add_argument('--stage',type=Path)
    args=parser.parse_args(argv)
    try:result=run(args.config,stage=args.stage)
    except BlockingIOError:print(json.dumps(dict(status='busy',fit_executed=False,automatic_actuation=False)));return 75
    except Exception:print(json.dumps(dict(status='score_withheld',fit_executed=False,automatic_actuation=False)));return 1
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
