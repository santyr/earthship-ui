"""Native-model refresh through the completed local daily or six-hour cutoff.

Private training runs beside serving. Only the final owned handoff briefly
quiesces the three serving timers. A failed refresh leaves the selected model.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def training_cutoff(now, timezone_name, *, cadence='daily'):
    if now.tzinfo is None:
        raise ValueError('aware daily training clock required')
    if cadence not in ('daily','six_hourly'):raise ValueError('supported native training cadence required')
    local=now.astimezone(ZoneInfo(timezone_name));step=24 if cadence=='daily' else 6
    return local.replace(hour=(local.hour//step)*step,minute=0,second=0,microsecond=0).astimezone(timezone.utc)


def long_part_prefix(rows):
    """Reuse at most two contiguous day-or-longer originals before a new day.

    At most three fresh two-day captures plus three intraday increments then
    fit within the unchanged eight-part limit. All old files remain retained.
    """
    result=[]
    for row in rows:
        if len(result)==2 or datetime.fromisoformat(row['end'])-datetime.fromisoformat(row['start'])<timedelta(days=1):break
        result.append(row)
    return result


def capture_windows(start, end):
    if start.tzinfo is None or end.tzinfo is None or start > end:
        raise ValueError('ordered aware capture interval required')
    result = []
    while start < end:
        stop = min(start + timedelta(days=2), end)
        result.append((start, stop))
        start = stop
    return result


def retained_parts(rows, cutoff):
    floor = cutoff - timedelta(days=7)
    rows = sorted((r for r in rows if datetime.fromisoformat(r['end']) > floor),
                  key=lambda r: r['start'])
    if any(datetime.fromisoformat(r['end']) > cutoff for r in rows):
        raise ValueError('future training part refused')
    if any(a['end'] != b['start'] for a, b in zip(rows, rows[1:])):
        raise ValueError('adjacent raw training parts required')
    if len(rows) > 8:
        raise ValueError('at most eight raw training parts required')
    return rows


# Only fixed lifecycle reasons cross the child/result boundary. Arbitrary
# exceptions can contain private command arguments, payloads or unbounded text.
FAILURE_REASONS=frozenset(('external activation owner acknowledgment missing',
    'external cleanup acknowledgment missing','activation reservation expired',
    'native activation child failed','activation child deadline exceeded','native_refresh_failed'))
FAILURE_TYPES=frozenset(('ValueError','RuntimeError','TimeoutError','CalledProcessError',
    'OSError','FileNotFoundError','PermissionError','BlockingIOError','KeyboardInterrupt','Exception'))


def failure_details(error):
    primary=getattr(error,'native_primary_failure',None)
    if (isinstance(primary,dict) and set(primary)=={'error','reason'} and
        primary['error'] in FAILURE_TYPES and primary['reason'] in FAILURE_REASONS):return dict(primary)
    name=type(error).__name__;reason=str(error)
    return dict(error=name if name in FAILURE_TYPES else 'Exception',
        reason=reason if reason in FAILURE_REASONS else 'native_refresh_failed')


def activation_failure_path(run,reservation):
    from pathlib import Path
    run=Path(run);nonce=Path(reservation).name
    if run.resolve()!=run or len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce):
        raise ValueError('exact activation failure binding required')
    return run/('activation-failure-'+nonce+'.json')


@contextmanager
def reservation_cleanup(backend):
    close=getattr(backend,'close_reservation',lambda:None)
    try:yield
    except BaseException as primary:
        try:close()
        except BaseException as cleanup:primary.native_cleanup_failure=failure_details(cleanup)
        raise
    else:
        try:close()
        except BaseException as cleanup:
            cleanup.native_failure_domain='cleanup'
            raise


def run_daily(backend, *, now, timezone_name, cadence='daily'):
    cutoff = training_cutoff(now, timezone_name,cadence=cadence)
    load_cutoff=training_cutoff(now,timezone_name)
    load = None
    prepare_load = getattr(backend, 'prepare_ac_load', None)
    if prepare_load is not None:
        try:
            load = prepare_load(load_cutoff)
        except Exception:
            load = dict(status='deferred', reason='load_profile_refresh_failed', automatic_actuation=False)
    def result(value):
        if load is not None: value = dict(value, ac_load=load)
        return value
    previous = backend.current()
    if datetime.fromisoformat(previous['trained_through']) >= cutoff:
        return result(dict(status='already_current', trained_through=previous['trained_through'],
                    cutoff=cutoff.isoformat(), fit_executed=False, automatic_actuation=False))
    with reservation_cleanup(backend):
        retry=getattr(backend,'retry_selection',lambda *args:None)(cutoff,previous)
        selection=retry if retry is not None else backend.prepare(cutoff,previous)
        return result(dict(backend.activate(selection,previous),cutoff=cutoff.isoformat(),
            fit_executed=retry is None,automatic_actuation=False))


def main(argv=None):
    import argparse
    import json
    import os
    import time
    from pathlib import Path
    from thermal_model.runtime_bundle import _owned_bytes
    from household_native_training import NativeTraining, activate, save, daily_lock
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--config', type=Path)
    group.add_argument('--activate', type=Path)
    args = parser.parse_args(argv)
    os.umask(0o077)
    started = time.monotonic()
    status = 0
    backend = None
    failure_path = None
    try:
        if args.activate:
            from household_native_lifecycle import activation_lock,cancellation_boundary
            if os.environ.get('EARTHSHIP_NATIVE_DAILY_LOCK_FD') is not None:
                with activation_lock(args.activate),cancellation_boundary():
                    failure_path=activation_failure_path(args.activate,os.environ['EARTHSHIP_NATIVE_RESERVATION'])
                    result = activate(args.activate)
            else:
                trusted=Path('/home/sat/.local/state/earthship-weather/audit-rollout-8f3747-20261020-native/native-config.json')
                config=json.loads(_owned_bytes(trusted,32768));backend=NativeTraining(config)
                with daily_lock(backend.state/'daily.lock') as lock,cancellation_boundary():
                    backend.learner_lock=lock
                    cutoff=training_cutoff(datetime.now(timezone.utc),config['timezone'],cadence=config.get('training_cadence','daily'))
                    with reservation_cleanup(backend):
                        previous=backend.current();selection=backend.retry_selection(cutoff,previous,requested_run=args.activate)
                        if selection is None:raise ValueError('exact valid retained activation package required')
                        result=backend.activate(selection,previous)
        else:
            config = json.loads(_owned_bytes(args.config, 32768))
            backend = NativeTraining(config)
            from household_native_lifecycle import cancellation_boundary
            with daily_lock(backend.state / 'daily.lock') as lock,cancellation_boundary():
                backend.learner_lock=lock
                result = run_daily(backend, now=datetime.now(timezone.utc),
                                   timezone_name=config['timezone'],cadence=config.get('training_cadence','daily'))
    except Exception as error:
        status = 1
        result = dict(status='daily_native_refresh_failed', **failure_details(error), automatic_actuation=False)
        if hasattr(error,'native_cleanup_failure'):result['cleanup_failure']=error.native_cleanup_failure
        if hasattr(error,'native_failure_domain'):result['failure_domain']=error.native_failure_domain
    if status and failure_path is not None:
        save(failure_path,dict(schema='earthship-native-activation-failure/v1',run=str(args.activate),
            nonce=Path(os.environ['EARTHSHIP_NATIVE_RESERVATION']).name,
            failure={key:result[key] for key in ('error','reason')}))
    result.update(exit=status, seconds=time.monotonic() - started)
    if backend is not None:
        save(backend.state / 'last-result.json', result)
    print(json.dumps(result), flush=True)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
