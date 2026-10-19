"""Opt-in generic user-systemd retry fixture; no household worker execution.

The fixture uses an isolated counter with no network, credential, OpenHAB, DM
or control callback. Retired provider unit-template assertions are removed.
"""
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest







def command(*arguments):
    return subprocess.run(arguments, capture_output=True, text=True, timeout=10, check=True).stdout


def properties(unit):
    raw = command('systemctl', '--user', 'show', unit, '-p', 'ActiveState', '-p', 'SubState',
                  '-p', 'Result', '-p', 'NRestarts', '-p', 'LoadState')
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def wait_for(predicate, timeout=30):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    pytest.fail('isolated systemd fixture did not reach expected state')


@pytest.mark.skipif(os.environ.get('EARTHSHIP_ISOLATED_SYSTEMD_TEST') != '1',
                    reason='explicit isolated user-systemd qualification required')
@pytest.mark.parametrize('mode', ['success', 'recover', 'persistent'])
def test_actual_systemd_retry_cap_and_next_natural_timer(tmp_path, mode):
    name = 'earthship-shadow-retry-test-'+uuid.uuid4().hex
    service, timer = name+'.service', name+'.timer'
    worker = tmp_path/'worker.py'
    worker.write_text(
        'from pathlib import Path\n'
        'import sys\n'
        'p=Path(__file__).parent\n'
        'counter=p/"attempts"\n'
        'n=int(counter.read_text())+1 if counter.exists() else 1\n'
        'counter.write_text(str(n))\n'
        'mode=(p/"mode").read_text()\n'
        'sys.exit(1 if mode=="persistent" or mode=="recover" and n==1 else 0)\n')
    (tmp_path/'mode').write_text(mode)
    count = lambda: int((tmp_path/'attempts').read_text()) if (tmp_path/'attempts').exists() else 0
    try:
        command('systemd-run', '--user', '--unit='+name, '--on-active=1s', '--on-unit-active=16s',
                '--timer-property=AccuracySec=1us', '--property=Type=oneshot',
                '--property=Restart=on-failure', '--property=RestartSec=2s',
                '--property=StartLimitIntervalSec=10s', '--property=StartLimitBurst=2',
                '--property=TimeoutStartSec=5s', '--property=UMask=0077',
                '--property=NoNewPrivileges=yes', '--property=RestrictAddressFamilies=AF_UNIX',
                sys.executable, str(worker))
        if mode == 'persistent':
            # This host's systemd 255 oneshot keeps Result=exit-code when the
            # restart start-limit is hit. Observe terminal state, restart
            # count and actual executions, not a guessed result string.
            state = wait_for(lambda: (p if (p:=properties(service)).get('SubState') == 'failed'
                                      and p.get('NRestarts') == '2' else None))
            assert state['ActiveState'] == 'failed' and count() == 2
            time.sleep(1)
            assert count() == 2 and properties(service)['SubState'] == 'failed'
            # Keep the same live timer. Recovery after its rate window expires
            # must need neither reset-failed nor a manual worker start.
            (tmp_path/'mode').write_text('success')
            wait_for(lambda: count() >= 3 and properties(service)['ActiveState'] == 'inactive')
            assert count() == 3 and properties(service)['Result'] == 'success'
        else:
            wanted = 1 if mode == 'success' else 2
            wait_for(lambda: count() >= wanted and properties(service)['ActiveState'] == 'inactive')
            time.sleep(2.5)
            assert count() == wanted and properties(service)['Result'] == 'success'
    finally:
        subprocess.run(['systemctl', '--user', 'stop', timer, service], capture_output=True, timeout=10)
        subprocess.run(['systemctl', '--user', 'reset-failed', service], capture_output=True, timeout=10)
        wait_for(lambda: all(properties(unit)['LoadState'] == 'not-found' for unit in (service, timer)),
                 timeout=10)
