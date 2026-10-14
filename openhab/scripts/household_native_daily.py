"""Morning native-model refresh: missing measurements through local midnight.

Private training runs beside serving. Only the final owned handoff briefly
quiesces the three serving timers. A failed refresh leaves the selected model.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def training_cutoff(now, timezone_name):
    if now.tzinfo is None:
        raise ValueError('aware daily training clock required')
    return now.astimezone(ZoneInfo(timezone_name)).replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


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


def run_daily(backend, *, now, timezone_name):
    cutoff = training_cutoff(now, timezone_name)
    previous = backend.current()
    if datetime.fromisoformat(previous['trained_through']) >= cutoff:
        return dict(status='already_current', trained_through=previous['trained_through'],
                    cutoff=cutoff.isoformat(), fit_executed=False, automatic_actuation=False)
    selection = backend.prepare(cutoff, previous)
    return dict(backend.activate(selection, previous), cutoff=cutoff.isoformat(),
                fit_executed=True, automatic_actuation=False)


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
    try:
        if args.activate:
            result = activate(args.activate)
        else:
            config = json.loads(_owned_bytes(args.config, 32768))
            backend = NativeTraining(config)
            with daily_lock(backend.state / 'daily.lock'):
                result = run_daily(backend, now=datetime.now(timezone.utc),
                                   timezone_name=config['timezone'])
    except Exception as error:
        status = 1
        result = dict(status='daily_native_refresh_failed', error=type(error).__name__,
                      reason=str(error), automatic_actuation=False)
    result.update(exit=status, seconds=time.monotonic() - started)
    if backend is not None:
        save(backend.state / 'last-result.json', result)
    print(json.dumps(result), flush=True)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
