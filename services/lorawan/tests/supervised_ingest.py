"""Private-fixture process restart; Docker lifecycle remains guardian-owned."""
import signal
import subprocess
import sys
import threading


def supervise(command, *, launch=subprocess.Popen, stopping=None, restart_seconds=1):
    stopping = threading.Event() if stopping is None else stopping
    child = None

    def terminate(*_):
        stopping.set()
        current = child
        if current is not None:
            try:
                current.terminate()
            except ProcessLookupError:
                pass

    previous = {number: signal.signal(number, terminate) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        while not stopping.is_set():
            child = launch(command)
            if stopping.is_set():
                terminate()
            result = child.wait()
            child = None
            if stopping.is_set() or result == 0:
                return 0
            stopping.wait(restart_seconds)
        return 0
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main():
    return supervise([sys.executable, '-B', '-m', 'services.lorawan.runtime',
                      '--config', '/run/private/ingest.json', '--registry', '/run/registry.json'])


if __name__ == '__main__':
    raise SystemExit(main())
