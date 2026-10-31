"""Shared fail-closed ownership boundary for disposable sensor qualification.

Only this harness imports the boundary; production sensor services are unchanged.
Inspection is read-only. Lifecycle/exec operations target inspected container IDs,
so a replacement Compose project cannot inherit an earlier authorization.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
DOCKER = '/snap/bin/docker'
PROJECT = 'earthship-sensors-test'
SERVICES = ('mqtt', 'postgres', 'ingest', 'openhab', 'redis', 'chirpstack')
PORTS = {'mqtt': ('1883/tcp', '18884'), 'openhab': ('8080/tcp', '18084'),
         'chirpstack': ('8080/tcp', '28085')}
BINDS = {
    'mqtt': {'/mosquitto/config/mosquitto.conf': 'mosquitto.conf',
             '/mosquitto/config/passwords': 'mqtt.passwords', '/mosquitto/config/acl': 'mqtt.acl',
             '/mosquitto/config/mosquitto_sub': 'mosquitto_sub', '/mosquitto/data': 'mqtt_data'},
    'postgres': {'/run/secrets/postgres_admin': 'postgres_admin',
                 '/docker-entrypoint-initdb.d/10-sensors.sql': 'init.sql'},
    'ingest': {'/run/private/ingest.json': 'ingest.json', '/run/registry.json': '@registry'},
    'openhab': {'/openhab/conf': 'openhab', '/openhab/addons': 'addons'},
    'redis': {'/run/private/redis.conf': 'redis.conf'},
    'chirpstack': {'/etc/chirpstack': 'chirpstack'},
    'simulator': {'/run/private/simulator.json': 'simulator.json', '/run/registry.json': '@registry'},
}
VOLUMES = {'postgres': {'/var/lib/postgresql/data': PROJECT + '_database'},
           'openhab': {'/openhab/userdata': PROJECT + '_openhab_data'},
           'redis': {'/data': PROJECT + '_redis_data'}}
# Hard caps include health checks, execs and the actual simulator. Docker's
# MemorySwap equals Memory to prohibit swap; zero would mean its default.
CAPS = {'mqtt': (64, .25, 8), 'postgres': (256, 1, 24), 'ingest': (192, .5, 8),
        'openhab': (1152, 2, 128), 'redis': (64, .25, 8), 'chirpstack': (192, 1, 8),
        'simulator': (128, .5, 8)}
RUNTIME_IMAGE = 'sha256:2a8053a90d76dcdd13696f6c21ab58ad2555f59dec266cda7ba77ec80a3dd19a'
_bound_ids = None
_bound_config = None


class IsolationError(RuntimeError):
    """Never swallowed by HTTP readiness retries."""


def _refuse():
    raise IsolationError('sensor fixture ownership refused: current worktree isolated Compose stack required')


def rendered_memory_bytes(value):
    """Compose byte count only; invalid/ambiguous values cannot match a cap."""
    if type(value) is str:
        if not re.fullmatch(r'[1-9][0-9]{0,18}', value):return None
        value = int(value)
    if type(value) is not int or not 0 < value <= 9223372036854775807:return None
    return value


def _inspect(arguments):
    try:
        result = subprocess.run([DOCKER, *arguments], check=True, capture_output=True,
                                text=True, timeout=10)
        if len(result.stdout) > 1048576:
            _refuse()
        return result.stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise IsolationError('sensor fixture ownership inspection failed') from error


def _sources(root, service):
    private = root / '.superpowers/lorawan-private'
    return {destination: str(root / 'deploy/lorawan/registry.simulation.json')
            if name == '@registry' else str(private / name)
            for destination, name in BINDS[service].items()}


def assert_owned_stack(*, require_running=('mqtt', 'openhab')):
    global _bound_ids, _bound_config
    root = ROOT.resolve()
    compose = root / 'deploy/lorawan/compose.test.yaml'
    nonce = os.environ.get('SENSOR_QUALIFICATION_NONCE', '')
    if (os.environ.get('SENSOR_INTEGRATION') != '1' or Path.cwd().resolve() != root
            or not re.fullmatch('[a-f0-9]{32}', nonce)):
        _refuse()
    try:
        source = compose.read_bytes()
        rendered = json.loads(_inspect(['compose', '-f', str(compose), '--profile', '*', 'config', '--format', 'json']))
        configured = rendered['services']
        if set(configured) != set(CAPS):
            _refuse()
        for name, network in rendered['networks'].items():
            if name not in ('sensors', 'management') or network['name'] != PROJECT + '_' + name:
                _refuse()
        if set(rendered['networks']) != {'sensors', 'management'} or rendered['networks']['sensors'].get('internal') is not True:
            _refuse()
        for service in (*SERVICES, 'simulator'):
            spec = configured[service]
            if spec.get('labels', {}).get('org.earthship.sensor.qualification') != nonce:
                _refuse()
            memory, cpu, tasks = CAPS[service]
            if (rendered_memory_bytes(spec.get('mem_limit')) != memory * 1024**2 or rendered_memory_bytes(spec.get('memswap_limit')) != memory * 1024**2
                or float(spec.get('cpus', 0)) != cpu or spec.get('pids_limit') != tasks or spec.get('restart') != 'no'
                or 'build' in spec or (service in ('ingest', 'simulator') and spec['image'] != RUNTIME_IMAGE)):
                _refuse()
            networks = {'sensors', 'management'} if service in PORTS else {'sensors'}
            if set(spec.get('networks', {})) != networks:
                _refuse()
            binds = {mount['target']: mount['source'] for mount in spec.get('volumes', [])
                     if mount['type'] == 'bind'}
            if binds != _sources(root, service):
                _refuse()
            if service in PORTS:
                _, published = PORTS[service]
                ports = spec.get('ports', [])
                if len(ports) != 1 or str(ports[0]['published']) != published or ports[0]['host_ip'] != '127.0.0.1':
                    _refuse()
        ids = _inspect(['compose', '-f', str(compose), '--profile', '*', 'ps', '--all', '-q', *SERVICES]).split()
        if len(ids) != len(SERVICES) or len(set(ids)) != len(ids) or any(not re.fullmatch('[a-f0-9]{64}', value) for value in ids):
            _refuse()
        containers = json.loads(_inspect(['inspect', *ids]))
        owned = {}
        for container in containers:
            labels = container['Config']['Labels']
            service = labels['com.docker.compose.service']
            if (service not in SERVICES or service in owned or container['Id'] not in ids
                or labels.get('org.earthship.sensor.qualification') != nonce
                or labels['com.docker.compose.project'] != PROJECT
                or labels['com.docker.compose.project.working_dir'] != str(root / 'deploy/lorawan')
                or labels['com.docker.compose.project.config_files'] != str(compose)
                or (service in require_running and not container['State']['Running'])):
                _refuse()
            binds = {mount['Destination']: mount['Source'] for mount in container['Mounts'] if mount['Type'] == 'bind'}
            volumes = {mount['Destination']: mount['Name'] for mount in container['Mounts'] if mount['Type'] == 'volume'}
            if binds != _sources(root, service) or volumes != VOLUMES.get(service, {}):
                _refuse()
            if container['Config']['Image'] != configured[service]['image']:
                _refuse()
            memory, cpu, tasks = CAPS[service]
            host = container['HostConfig']
            if (host['Memory'] != memory * 1024**2 or host['MemorySwap'] != memory * 1024**2
                or host['NanoCpus'] != int(cpu * 10**9) or host['PidsLimit'] != tasks
                or host['RestartPolicy'] != {'Name': 'no', 'MaximumRetryCount': 0}):
                _refuse()
            networks = {PROJECT + '_' + name for name in configured[service]['networks']}
            if set(container['NetworkSettings']['Networks']) != networks:
                _refuse()
            images = json.loads(_inspect(['image', 'inspect', configured[service]['image']]))
            if len(images) != 1 or container['Image'] != images[0]['Id']:
                _refuse()
            if service in PORTS:
                internal, published = PORTS[service]
                expected_ports = {internal: [{'HostIp': '127.0.0.1', 'HostPort': published}]}
                if host.get('PortBindings') != expected_ports:
                    _refuse()
                ports = {port: bindings for port, bindings in container['NetworkSettings']['Ports'].items() if bindings}
                if container['State']['Running'] and ports != expected_ports:
                    _refuse()
            owned[service] = container['Id']
        if set(owned) != set(SERVICES) or compose.read_bytes() != source:
            _refuse()
        # Retained volumes must have no foreign consumer, including stopped
        # containers which would otherwise inherit these private DB contents.
        volume_names = {name for volumes in VOLUMES.values() for name in volumes.values()}
        volumes = json.loads(_inspect(['volume', 'inspect', *sorted(volume_names)]))
        if {v['Name'] for v in volumes} != volume_names or len(volumes) != len(volume_names):
            _refuse()
        for volume in volumes:
            if (volume['Driver'] != 'local' or volume.get('Options') not in (None, {})
                or volume['Labels'].get('com.docker.compose.project') != PROJECT
                or volume['Labels'].get('com.docker.compose.volume') != volume['Name'].removeprefix(PROJECT + '_')):
                _refuse()
        all_ids = _inspect(['ps', '--all', '--quiet', '--no-trunc']).split()
        if len(all_ids) > 256 or any(not re.fullmatch('[a-f0-9]{64}', value) for value in all_ids):
            _refuse()
        for container in json.loads(_inspect(['inspect', *all_ids])) if all_ids else []:
            if any(mount['Type'] == 'volume' and mount.get('Name') in volume_names for mount in container['Mounts']):
                if container['Id'] not in owned.values():
                    _refuse()
        signature = json.dumps(rendered, sort_keys=True)
        if (_bound_ids is not None and owned != _bound_ids) or (_bound_config is not None and signature != _bound_config):
            _refuse()
        _bound_ids, _bound_config = owned, signature
        return owned
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise IsolationError('sensor fixture ownership/configuration unavailable') from error


def owned_urlopen(request, **kwargs):
    assert_owned_stack()
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    from urllib.parse import urlsplit
    if (urlsplit(url).scheme, urlsplit(url).netloc) not in {
        ('http', '127.0.0.1:18084'), ('http', '127.0.0.1:28085'),
    }:
        _refuse()
    return urllib.request.urlopen(request, **kwargs)


def guarded_mqtt_client(config, name):
    assert_owned_stack()
    if config.get('environment') != 'simulation' or (config.get('mqtt_host'), config.get('mqtt_port')) != ('127.0.0.1', 18884):
        _refuse()
    from services.lorawan.runtime import mqtt_client
    client = mqtt_client(config, name)
    publish = client.publish
    connect = client.connect
    def owned_connect(*args, **kwargs):
        assert_owned_stack()
        return connect(*args, **kwargs)
    client.connect = owned_connect
    def owned_publish(*args, **kwargs):
        assert_owned_stack()
        return publish(*args, **kwargs)
    client.publish = owned_publish
    return client


def _guardian_lifecycle(action, service, **kwargs):
    """Closed service protocol; the controller never sends Docker start requests."""
    import socket
    import stat
    import struct
    import time
    from services.lorawan.tests.qualification_guard import decode, require
    from services.lorawan.tests.qualification_runtime import Lease
    try:
        require(set(kwargs) <= {'check', 'capture_output', 'text', 'timeout'})
        timeout = kwargs.get('timeout', 30)
        require(type(timeout) in (int, float) and 0 < timeout <= 30)
        nonce = os.environ.get('SENSOR_QUALIFICATION_NONCE', '')
        require(re.fullmatch('[a-f0-9]{32}', nonce))
        digest = os.environ.get('SENSOR_QUALIFICATION_SHA256', '')
        lease = Lease(Path(os.environ['SENSOR_QUALIFICATION_MANIFEST']), digest,
                      root=ROOT.resolve(), nonce=nonce,
                      boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), clock=time.monotonic)
        envelope = lease.verify()
        unit = 'earthship-sensor-guard-' + nonce + '.service'
        require(envelope['controller']['guardian_unit'] == unit)
        address = Path('/run') / ('earthship-sensor-guard-' + nonce) / 'control.sock'
        info = address.lstat()
        require(address.resolve() == address and stat.S_ISSOCK(info.st_mode)
                and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600)
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(timeout)
            connection.connect(str(address))
            pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            require(uid == os.getuid() and Path('/proc', str(pid), 'cgroup').read_text() == '0::/system.slice/' + unit + '\n')
            payload = {'operation': 'lifecycle', 'manifest_sha256': digest, 'action': action, 'service': service}
            connection.sendall(json.dumps(payload, separators=(',', ':')).encode())
            raw, ancillary, flags, _ = connection.recvmsg(8193, 0)
            require(not ancillary and not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) and len(raw) <= 8192)
            response = decode(raw)
        require(set(response) == {'returncode', 'stdout', 'stderr'} and type(response['returncode']) is int
                and response['stdout'] == response['stderr'] == '')
        empty = '' if kwargs.get('text') else b''
        result = subprocess.CompletedProcess(['sensor-guardian', action, service], response['returncode'],
            empty if kwargs.get('capture_output') else None, empty if kwargs.get('capture_output') else None)
        if kwargs.get('check'): result.check_returncode()
        return result
    except subprocess.CalledProcessError:
        raise
    except Exception as error:
        raise IsolationError('sensor fixture guardian lifecycle refused; reconciliation required') from error


def run_compose(arguments, **kwargs):
    # Lifecycle recovery permits deliberately stopped fixture services but still
    # checks every identity/mount/config before cleanup, restart, exec or start.
    owned = assert_owned_stack(require_running=())
    action = arguments[0]
    if action in ('stop', 'start', 'restart') and len(arguments) == 2 and arguments[1] in owned:
        return _guardian_lifecycle(action, arguments[1], **kwargs)
    elif action == 'exec' and len(arguments) > 3 and arguments[1] == '-T' and arguments[2] in owned:
        command = [DOCKER, 'exec', '-i', owned[arguments[2]], *arguments[3:]]
    elif arguments == ['--profile', 'simulation', 'run', '--rm', 'simulator']:
        return _guardian_lifecycle('start', 'simulator', **kwargs)
    else:
        _refuse()
    return subprocess.run(command, **kwargs)


if __name__ == '__main__':
    assert_owned_stack(require_running=SERVICES)
    print('Verified current-worktree disposable sensor stack ownership')
