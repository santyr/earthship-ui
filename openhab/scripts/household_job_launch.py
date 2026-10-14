"""Serialize RAM admission until systemd exposes the new scope's commitment."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import socket
import struct
import sys
import tempfile
import time
from uuid import uuid4

from household_job_budget import AdmissionDeferred, admit_memory
from household_job_pool import POOL_NAME, HOST_RESERVE, available_memory, read_pool, _counter, check_host_pressure


@contextmanager
def admission_gate(path, *, seconds=15):
    path = Path(path)
    if path.parent.resolve() != path.parent.absolute():
        raise ValueError('real private admission directory required')
    directory = path.parent.stat()
    if directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) != 0o700:
        raise ValueError('owned private admission directory required')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        original = os.fstat(fd)
        def verify():
            current = path.lstat()
            if (not stat.S_ISREG(current.st_mode) or current.st_uid != os.getuid()
                    or current.st_nlink != 1 or stat.S_IMODE(current.st_mode) != 0o600
                    or (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino)):
                raise ValueError('admission lock identity changed')
        verify()
        deadline = time.monotonic() + seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AdmissionDeferred('another job is being admitted')
                time.sleep(.05)
        verify()
        yield verify
    finally:
        os.close(fd)


class StartupPermission:
    """A scoped shim must receive permission before executing the workload."""
    def __init__(self, directory=None):
        self.directory = tempfile.TemporaryDirectory(prefix='es-job-', dir=directory)
        self.path = Path(self.directory.name)/'start'
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.listener.settimeout(15)
            self.listener.bind(str(self.path))
            self.listener.listen(1)
        except BaseException:
            self.close()
            raise

    def authorize(self, expected_pid=None):
        connection, _ = self.listener.accept()
        with connection:
            connection.settimeout(5)
            pid, uid, _ = struct.unpack('3i', connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
            if uid != os.getuid() or (expected_pid is not None and pid != expected_pid):
                raise ValueError('unexpected scoped startup peer')
            connection.sendall(b'1')
        self.close()

    def close(self):
        self.listener.close()
        self.directory.cleanup()

    def __enter__(self):return self
    def __exit__(self, *args):self.close()


class ScopedProcess:
    def __init__(self, process, permission):
        self.process, self.permission = process, permission
    def poll(self):return self.process.poll()
    def wait(self):return self.process.wait(timeout=20)
    def authorize(self):self.permission.authorize(self.process.pid)
    def cancel(self):self.permission.close()


def start_scope(command, *, unit, memory_bytes, production, tasks, seconds, collection=False):
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    permission = StartupPermission(Path('/run/user')/str(os.getuid()))
    shim = [sys.executable, str(Path(__file__).with_name('household_job_start.py')),
        '--socket', str(permission.path), '--', *command]
    argv = ['systemd-run', '--user', '--scope', '--quiet', '--collect',
        '--slice='+POOL_NAME, '--unit='+unit, '--description=Earthship managed job',
        '-p', 'MemoryMax='+str(memory_bytes), '-p', 'MemorySwapMax=0',
        '-p', 'CPUWeight='+('100' if production else '25'), '-p', 'TasksMax='+str(tasks),
        '-p', 'RuntimeMaxSec='+str(seconds), '-p', 'IOWeight='+('100' if production and not collection else '10'),
        *(['-p','CPUQuota=20%'] if collection else []),
        'nice', '-n', '15', 'ionice', '-c', '3', *shim]
    try:
        return ScopedProcess(subprocess.Popen(argv, env=environment), permission)
    except BaseException:
        permission.close()
        raise


def stop_scope(unit):
    subprocess.run(['systemctl', '--user', 'stop', unit], check=True, timeout=15,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch_job(command, *, pool_path, lock_path, minimum_bytes, preferred_bytes,
               reserve_bytes=HOST_RESERVE, production=False, tasks=96, seconds=600, collection=False,
               available=available_memory, spawn=start_scope, stop=stop_scope, health=check_host_pressure):
    if (not isinstance(command, (list, tuple)) or not 1 <= len(command) <= 256
            or any(not isinstance(arg, str) or '\0' in arg for arg in command)
            or not Path(command[0]).is_absolute() or sum(map(len, command)) > 32768):
        raise ValueError('bounded absolute command required')
    if type(tasks) is not int or not 1 <= tasks <= 128 or type(seconds) is not int or not 1 <= seconds <= 3600:
        raise ValueError('bounded task count and runtime required')
    if collection and (minimum_bytes != 256*1024**2 or preferred_bytes != 256*1024**2 or tasks != 24 or seconds > 90):
        raise ValueError('fixed compatible collection budget required')
    unit = 'earthship-job-'+uuid4().hex+'.scope'
    process = None
    with admission_gate(lock_path) as verify:
        try:
            health()
            snapshot = read_pool(pool_path)
            memory = admit_memory(available_bytes=available(), **snapshot,
                minimum_bytes=minimum_bytes, preferred_bytes=preferred_bytes, reserve_bytes=reserve_bytes)
            verify()
            process = spawn(command, unit=unit, memory_bytes=memory,
                production=production, tasks=tasks, seconds=seconds, **({'collection':True} if collection else {}))
            deadline = time.monotonic() + 15
            while True:
                status = process.poll()
                if status is not None:
                    process.cancel()
                    return status
                leaf = Path(pool_path)/unit
                if leaf.exists():
                    if leaf.resolve()!=leaf.absolute():raise ValueError('real admitted scope required')
                    if (_counter(leaf/'memory.max') != memory or
                            _counter(leaf/'memory.swap.max') != 0):
                        raise ValueError('started scope differs from admitted budget')
                    verify()
                    process.authorize()
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('scope admission was not confirmed')
                time.sleep(.05)
        except BaseException:
            if process is not None:
                # Revoke permission before cancellation, still under the lock.
                # A delayed shim cannot execute even if systemd stop fails.
                process.cancel()
                stop(unit)
                process.wait()
            raise
    try:
        while process.poll() is None:
            health()
            time.sleep(1)
        return process.wait()
    except BaseException:
        process.cancel()
        stop(unit)
        process.wait()
        raise
