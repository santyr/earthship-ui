"""Opt-in qualified hourly learning with a bounded read-only subprocess.

Absent opt-in preserves legacy operation. Invalid activation or unavailable
evidence skips learning without numeric-history fallback. The child cannot
save model state, publish Items, or send notifications.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from weather_temperature_reader import _utc, validate_temperature_metadata_v2


def read_db_config(path):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError('absolute database config required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077 or not 1 <= metadata.st_size <= 4096):
            raise ValueError('private owned database config required')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            raw = handle.read(4097)
    finally:
        os.close(fd)
    if len(raw) > 4096:
        raise ValueError('database config too large')
    from weather_temperature_config import _object
    config = json.loads(raw, object_pairs_hook=_object)
    if not isinstance(config, dict) or set(config) != {'host', 'port', 'dbname', 'user', 'password'}:
        raise ValueError('closed database config required')
    if (config['host'] != '127.0.0.1' or type(config['port']) is not int or config['port'] != 5432
            or config['dbname'] != 'openhab' or config['user'] != 'weather_temperature_reader'
            or not isinstance(config['password'], str) or not 1 <= len(config['password']) <= 256):
        raise ValueError('restricted evidence database required')
    return config


def collect(request,*,config_path,policy_path):
    return _collect(request,config_path=config_path,policy_path=policy_path,version=1)


def collect_v2(request,*,config_path,policy_path):
    return _collect(request,config_path=config_path,policy_path=policy_path,version=2)


def _native_outdoor_policy(path):
    from weather_temperature_config import load_temperature_receiver_configuration
    policies,epochs=load_temperature_receiver_configuration(path)
    if epochs is None or 'outdoor' not in policies:raise ValueError('native outdoor policy required')
    policy=policies['outdoor']
    if policy.model!='Fineoffset-WH65B' or policy.sensor_id!=206:raise ValueError('approved outdoor identity required')
    return policy,epochs['outdoor']


def _collect(request,*,config_path,policy_path,version):
    from weather_temperature_config import load_temperature_policies
    from weather_temperature_history import fetch_temperature_target,fetch_temperature_target_v2,TemperatureHistoryUnavailable
    import psycopg2
    fields={'targets','assessed_at'}|({'receipt_version','sensor_epoch'} if version==2 else set())
    if not isinstance(request,dict) or set(request)!=fields:
        raise ValueError('closed request required')
    assessed = _utc(request['assessed_at'])
    if assessed > datetime.now(timezone.utc):
        raise ValueError('future assessment')
    targets = request['targets']
    if not isinstance(targets, list) or not 1 <= len(targets) <= 24:
        raise ValueError('bounded targets required')
    parsed = [_utc(t) for t in targets]
    if len(set(parsed)) != len(parsed) or any(t > assessed for t in parsed):
        raise ValueError('unique elapsed targets required')
    kwargs={}
    if version==2:
        from weather_temperature_evidence import sensor_epoch_id
        policy,epoch=_native_outdoor_policy(policy_path)
        if type(request['receipt_version']) is not int or request['receipt_version']!=2 or sensor_epoch_id(request['sensor_epoch'])!=epoch:
            raise ValueError('native outdoor phase differs from request')
        kwargs['sensor_epoch']=epoch;fetch=fetch_temperature_target_v2
    else:
        policy=load_temperature_policies(policy_path)['outdoor'];fetch=fetch_temperature_target
    config=read_db_config(config_path)
    if policy.model != 'Fineoffset-WH65B' or policy.sensor_id != 206:
        raise ValueError('approved outdoor identity required')
    results = {}
    for key, target in zip(targets, parsed):
        try:
            value = fetch(
                lambda: psycopg2.connect(**config, connect_timeout=3),
                target=target,assessed_at=assessed,stream='outdoor',policy=policy,**kwargs)
        except TemperatureHistoryUnavailable:
            value = None
        results[key] = None if value is None else {
            k: v.isoformat() if isinstance(v, datetime) else v for k, v in value.items()}
    return results


def score_runtime_hourly(state, now, scorer):
    enabled=os.environ.get('HOURLY_TEMP_QUALIFIED_ENABLE')
    version=os.environ.get('HOURLY_TEMP_RECEIPT_VERSION','1')
    if enabled is None and version=='1':
        return scorer(state, now)
    try:
        if enabled!='1' or version not in ('1','2'):
            raise ValueError('invalid explicit activation')
        cutover = os.environ.get('HOURLY_TEMP_EVIDENCE_CUTOVER')
        selected = []
        assessment = None
        def select(*, target, assessed_at):
            nonlocal assessment
            assessment = assessed_at
            selected.append(target.isoformat())
            return None
        preview = {k: deepcopy(state[k]) for k in ('hourly_temp_targets', 'hourly_temp_model') if k in state}
        scorer(preview, now, qualified_reader=select, evidence_cutover=cutover)
        results = {}
        native_context = {}
        if selected:
            request={'targets':selected,'assessed_at':assessment.isoformat()};command='--read'
            if version=='2':
                policy,epoch=_native_outdoor_policy(os.environ.get('HOURLY_TEMP_POLICY'))
                native_context = {'evidence_policy': policy, 'sensor_epoch': epoch}
                request.update(receipt_version=2,sensor_epoch=epoch);command='--read-v2'
            result = subprocess.run([sys.executable,str(Path(__file__).resolve()),command],
                input=json.dumps(request), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=30, check=True)
            if len(result.stdout.encode()) > 32768:
                raise ValueError('oversize evidence result')
            results = json.loads(result.stdout)
            if not isinstance(results, dict) or set(results) != set(selected):
                raise ValueError('unexpected evidence result')
            for target,evidence in results.items():
                if evidence is not None:
                    if not isinstance(evidence, dict):
                        raise ValueError('invalid evidence result')
                    for key in ('receivedAt','storedAt','validUntil'):evidence[key]=_utc(evidence[key])
                    if version=='2':
                        validate_temperature_metadata_v2(evidence,_utc(target),policy=policy,sensor_epoch=epoch)
        count = scorer(state, now, qualified_reader=lambda **kw: results.get(kw['target'].isoformat()),
                       evidence_cutover=cutover, **native_context)
        print(f'hourly qualified evidence: targets={len(selected)} scored={count}')
        return count
    except Exception:
        print('hourly qualified evidence unavailable; learning skipped without fallback', file=sys.stderr)
        return 0


def main():
    try:
        if sys.argv[1:] not in (['--read'],['--read-v2']):
            raise ValueError('read-only worker invocation required')
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ValueError('oversize request')
        collector=collect_v2 if sys.argv[1:]==['--read-v2'] else collect
        results = collector(json.loads(raw),config_path=os.environ.get('HOURLY_TEMP_DB_CONFIG'),
                          policy_path=os.environ.get('HOURLY_TEMP_POLICY'))
        print(json.dumps(results, allow_nan=False, separators=(',', ':')))
    except Exception:
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
