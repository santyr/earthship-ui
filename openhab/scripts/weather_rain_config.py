"""Explicit, default-off rain evidence receiver configuration."""
import json
import os
import stat

from weather_rain_evidence import RainPolicy


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate rain policy key')
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError('nonfinite rain policy constant')


def load_rain_policy(path):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError('absolute rain policy path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o022 or not 1 <= metadata.st_size <= 4096):
            raise ValueError('owned bounded rain policy file required')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            contents = stream.read(4097)
        if len(contents) > 4096:
            raise ValueError('rain policy file exceeds bound')
    finally:
        os.close(fd)
    document = json.loads(contents, object_pairs_hook=_object,
                          parse_constant=_nonfinite)
    if (not isinstance(document, dict) or set(document) != {'version', 'sensor_id',
            'validity_seconds', 'maximum_counter_in'} or
            type(document['version']) is not int or document['version'] != 1):
        raise ValueError('unsupported rain policy schema')
    return RainPolicy(sensor_id=document['sensor_id'],
                      validity_seconds=document['validity_seconds'],
                      maximum_counter_in=document['maximum_counter_in'])


def configure_rain_receiver(app, environ=None):
    env = os.environ if environ is None else environ
    if env.get('WEATHER_RAIN_EVIDENCE_ENABLE') != '1':
        return None
    try:
        from weather_rain_receiver import install_rain_evidence
        policy = load_rain_policy(env.get('WEATHER_RAIN_EVIDENCE_POLICY'))
        return install_rain_evidence(app, enabled=True, policy=policy)
    except Exception:
        app.logger.warning('rain evidence configuration unavailable; legacy receiver retained')
        return None
