"""Process-restart and shutdown contract, without Docker or a database."""
import signal
import threading
from services.lorawan.tests.supervised_ingest import supervise


def test_failure_restarts_before_clean_completion():
    calls = []
    results = iter([1, 1, 0])

    def launch(command):
        calls.append(tuple(command))
        result = next(results)
        return type('Child', (), {'wait': lambda self: result})()

    assert supervise(['fixed-worker'], launch=launch, restart_seconds=0) == 0
    assert calls == [('fixed-worker',)] * 3


def test_shutdown_forwards_to_live_worker_and_does_not_restart():
    calls = []
    previous = signal.getsignal(signal.SIGTERM)

    class Child:
        def wait(self):
            signal.raise_signal(signal.SIGTERM)
            calls.append('waited')
            return 0

        def terminate(self):
            calls.append('terminated')

    assert supervise(['fixed-worker'], launch=lambda _: Child()) == 0
    assert calls == ['terminated', 'waited']
    assert signal.getsignal(signal.SIGTERM) == previous


def test_stop_during_launch_terminates_new_worker_before_waiting():
    stopping = threading.Event()
    calls = []

    class Child:
        def wait(self):
            calls.append('waited')
            return -15

        def terminate(self):
            calls.append('terminated')

    def launch(_):
        stopping.set()
        return Child()

    assert supervise(['fixed-worker'], launch=launch, stopping=stopping) == 0
    assert calls == ['terminated', 'waited']


def test_stop_during_backoff_prevents_another_worker():
    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, seconds):
            assert seconds == 1
            self.stopped = True

    calls = []
    stop = Stop()

    def launch(_):
        calls.append('started')
        return type('Child', (), {'wait': lambda self: 1})()

    assert supervise(['fixed-worker'], launch=launch, stopping=stop) == 0
    assert calls == ['started']
