#!/usr/bin/env python3
"""Verify one natural radiation-enabled shadow publication; no service starts.

Default is GET/read-only. --record-proof updates only the exact private rollout
receipt after immutable capture, explicit-runtime replay, source-expiry, actual
systemd invocation/timer, live Item and JDBC checks all pass. No learning,
journal label, model promotion, timer change or household command is supplied.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path('/home/sat/openhab/scripts')
SERVICE = 'thermal-model-shadow.service'
TIMER = 'thermal-model-shadow.timer'
ITEM = 'Thermal_Model_JSON'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def aware(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware publication timestamp required')
    return value.astimezone(timezone.utc)


def from_us(value):
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError('positive exact systemd timestamp required')
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=value)


def validate_delivery(capture, *, run, live_output, rows, installed_after, assessed_at=None):
    assessed = aware(assessed_at or datetime.now(timezone.utc))
    if (run.get('ActiveState') != 'inactive' or run.get('MainPID') != '0'
            or run.get('Result') != 'success' or run.get('ExecMainCode') != '1'
            or run.get('ExecMainStatus') != '0' or run.get('timer_active') is not True
            or not isinstance(run.get('InvocationID'), str)
            or re.fullmatch('[0-9a-f]{32}', run['InvocationID']) is None):
        raise ValueError('successful terminal natural invocation required')
    start, finish, trigger = (from_us(run[name]) for name in ('started_us','finished_us','triggered_us'))
    if (not aware(installed_after) < start <= finish <= assessed
            or not timedelta(0) <= start-trigger <= timedelta(seconds=5)):
        raise ValueError('post-installation timer-bound invocation required')
    decision, published, inputs = map(aware, (capture['decision_at'],
        capture['published_at'], capture['inputs_available_at']))
    output = capture['output']
    if (capture['schema'] != 'earthship-thermal-shadow-forcing-capture/v2'
            or not start <= inputs <= decision <= published <= finish
            or aware(output['generatedAt']) != decision or output.get('status') != 'shadow'
            or output['confidence']['grade'] == 'unavailable'
            or digest(output) != capture['sha256']['output'] or output != live_output):
        raise ValueError('original available capture and current Item must match actual run')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('bounded original JDBC rows required')
    matches, previous = [], -1
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'time','state'}
                or type(row['time']) is not int or row['time'] <= previous
                or not isinstance(row['state'], str) or len(row['state'].encode()) > 16384):
            raise ValueError('strict ordered original JDBC row required')
        previous = row['time']
        value = json.loads(row['state'])
        if aware(value['generatedAt']) == decision:
            stored = datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=row['time'])
            if (value != output or not decision <= stored <= min(assessed,finish+timedelta(seconds=30))):
                raise ValueError('durable publication has conflicting data or invalid source clock')
            matches.append(row)
    if len(matches) != 1:
        raise ValueError('exactly one original persisted publication required')
    radiation_sha = capture['current']['radiation']['sourceEvidence']['snapshotSha256']
    for value in (radiation_sha, capture['sha256']['artifact']):
        if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
            raise ValueError('original artifact and radiation identities required')
    return dict(version=1, scope='verified_natural_thermal_radiation_publication',
        invocation_id=run['InvocationID'], unit_started_at=start.isoformat(),
        unit_finished_at=finish.isoformat(), timer_triggered_at=trigger.isoformat(),
        decision_at=decision.isoformat(), published_at=published.isoformat(),
        jdbc_stored_at=datetime.fromtimestamp(matches[0]['time']/1000,timezone.utc).isoformat(),
        jdbc_row_sha256=digest(matches[0]), output_sha256=capture['sha256']['output'],
        artifact_sha256=capture['sha256']['artifact'], radiation_source_sha256=radiation_sha,
        verified_at=assessed.isoformat(), learning_enabled=False, controls_enabled=False)


def precise_property(unit, interface, property):
    suffix = '_2eservice' if unit.endswith('.service') else '_2etimer'
    obj = '/org/freedesktop/systemd1/unit/thermal_2dmodel_2dshadow' + suffix
    completed = subprocess.run(['busctl','--user','get-property','org.freedesktop.systemd1',
        obj,'org.freedesktop.systemd1.'+interface,property], capture_output=True,
        text=True, timeout=10, check=True)
    match = re.fullmatch(r't ([0-9]+)\s*', completed.stdout)
    if match is None: raise ValueError('exact unsigned systemd property required')
    return int(match[1])


def run_evidence(rollout):
    fields = ('ActiveState','MainPID','Result','ExecMainCode','ExecMainStatus','InvocationID')
    raw = rollout.systemctl('show', *[arg for field in fields for arg in ('-p',field)], SERVICE)
    result = dict(line.split('=',1) for line in raw.splitlines())
    if set(result) != set(fields): raise ValueError('complete invocation state required')
    result.update(started_us=precise_property(SERVICE,'Service','ExecMainStartTimestamp'),
        finished_us=precise_property(SERVICE,'Service','ExecMainExitTimestamp'),
        triggered_us=precise_property(TIMER,'Timer','LastTriggerUSec'),
        timer_active=rollout.systemctl('show','-p','ActiveState','--value',TIMER)=='active')
    return result


def load_rollout():
    spec = importlib.util.spec_from_file_location('natural_radiation_rollout',
        ROOT/'scripts/thermal-radiation-files.py')
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def commit_proof(rollout, receipt, before, proof):
    """Durable evidence first, then qualification pin; recover interrupted pins."""
    if rollout._state(receipt)!=before:
        raise ValueError('rollout changed before proof commit')
    path=receipt/'natural-publication.json'
    if before['status']=='installed_natural_publication_verified':
        prior=json.loads(rollout.q.bundle._read(path,private=True))
        if prior['invocation_id']!=proof['invocation_id'] or prior['output_sha256']!=proof['output_sha256']:
            raise ValueError('existing natural proof belongs to another invocation')
        return prior
    if before['status']!='installed_waiting_natural_publication':
        raise ValueError('pending installed rollout required')
    raw=canonical(proof)+b'\n'
    if path.exists() or path.is_symlink():
        old_raw=rollout.q.bundle._read(path,private=True)
        old=json.loads(old_raw)
        if (set(old)!=set(proof) or any(old[key]!=proof[key] for key in proof if key!='verified_at')
                or not aware(proof['unit_finished_at'])<=aware(old['verified_at'])<=aware(proof['verified_at'])):
            raise ValueError('existing natural proof differs from reverified invocation')
        proof,raw=old,old_raw
    else:
        rollout.q.files._atomic_write_private(path,raw,0o600,parent_mode=0o700)
    after={**before,'status':'installed_natural_publication_verified',
           'natural_publication_sha256':sha256(raw).hexdigest()}
    rollout._save_state(receipt,after)
    rollout._state(receipt)
    return proof


def verify(receipt, *, record=False):
    # File-recovery helpers import the artifact validator too. Select the
    # installed closure before loading them, not after a repository v5 validator
    # has already entered sys.modules and could refuse the deployed v4 artifact.
    sys.path.insert(0,str(LIVE))
    rollout = load_rollout()
    if rollout.LIVE != LIVE: raise ValueError('exact installed runtime root required')
    if (receipt.parent != rollout.RECEIPTS or receipt.parent.resolve(strict=True) != rollout.RECEIPTS
            or not re.fullmatch(r'radiation-current-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}', receipt.name)):
        raise ValueError('exact private rollout receipt required')
    before = rollout._state(receipt)
    if before['status'] not in {'installed_waiting_natural_publication','installed_natural_publication_verified'}:
        raise ValueError('installed radiation rollout required')
    if rollout._revision(rollout.LIVE) != rollout.NEW:
        raise ValueError('qualified installed publication source required')
    if rollout.q.bundle._read(rollout.UNIT) != rollout.q.bundle._read(receipt/'source'/rollout.UNIT_SOURCE):
        raise ValueError('exact installed radiation drop-in required')
    # A fresh process selects the installed legacy model closure before imports.
    import openhab_sanity_check as oh
    from thermal_model.forcing_capture import verify_capture, _private_directory, _artifact_payload
    from thermal_model.artifacts import _artifact_from_payload
    from thermal_radiation_runtime import _validate_receipt, _utc
    from thermal_temperature_runtime import validate_shadow_receipt_expiry
    run = run_evidence(rollout)
    live_output = json.loads(oh.get('/items/'+ITEM)['state'])
    issued = aware(live_output['generatedAt'])
    digest_output = digest(live_output)
    directory = _private_directory(_private_directory(rollout.STATE/'forcing-captures')/issued.strftime('%Y-%m'))
    capture_path = directory/(issued.strftime('%Y%m%dT%H%M%SZ')+'-'+digest_output[:16]+'.json.gz')
    capture = verify_capture(capture_path)
    accepted = _artifact_from_payload(json.loads(rollout.q.bundle._read(
        rollout.STATE/'models/accepted.json',private=True)))
    if digest(_artifact_payload(accepted,capture['output'])) != capture['sha256']['artifact']:
        raise ValueError('captured original accepted artifact required')
    initial = aware(capture['decision_at']); published = aware(capture['published_at'])
    radiation = capture['current']['radiation']
    native = _validate_receipt(radiation['sourceEvidence'], target=initial,
        cutover=aware(rollout.RAD_ENV['THERMAL_RADIATION_EVIDENCE_CUTOVER']))
    if (aware(radiation['at']) != native['radioDecodedAt']
            or radiation['value'] != native['irradianceWm2']
            or aware(radiation['validUntil']) != native['validUntil']
            or not published < native['validUntil']):
        raise ValueError('original unexpired radiation input required')
    for at in (initial,published):
        current = {role:{**reading,'at':_utc(reading['at']),'validUntil':_utc(reading['validUntil'])}
                   for role in ('air','mass','outdoor') for reading in (capture['current'][role],)}
        validate_shadow_receipt_expiry(current,at)
    start, finish = (from_us(run[name]) for name in ('started_us','finished_us'))
    query = urlencode(dict(serviceId='jdbc', starttime=(start-timedelta(seconds=1)).isoformat(),
                           endtime=(finish+timedelta(seconds=30)).isoformat()))
    rows = oh.get('/persistence/items/'+ITEM+'?'+query)['data']
    if before['status'] == 'installed_natural_publication_verified':
        prior = json.loads(rollout.q.bundle._read(receipt/'natural-publication.json',private=True))
        installed_after = aware(prior['installed_after'])
    else:
        installed_after = datetime.fromtimestamp((receipt/'qualification.json').stat().st_mtime,timezone.utc)
    proof = validate_delivery(capture,run=run,live_output=live_output,rows=rows,installed_after=installed_after)
    replay = rollout.q._replay(rollout.LIVE,capture_path,rollout.NEW)
    if replay['capture_output_sha256'] != proof['output_sha256']:
        raise ValueError('exact as-issued installed-runtime replay required')
    proof.update(publication_runtime_revision=rollout.NEW, capture_path=str(capture_path),
        capture_file_sha256=sha256(rollout.q.bundle._read(capture_path,private=True)).hexdigest(),
        artifact_training_revision=replay['artifact_code_revision'], installed_after=installed_after.isoformat(),
        native_radiation_decoded_at=native['radioDecodedAt'].isoformat(),
        native_radiation_valid_until=native['validUntil'].isoformat(), exact_as_issued=True)
    if (run_evidence(rollout) != run or rollout._revision(rollout.LIVE) != rollout.NEW
            or rollout._state(receipt) != before or json.loads(oh.get('/items/'+ITEM)['state']) != live_output):
        raise ValueError('invocation, configuration, runtime or publication changed during verification')
    if record:
        proof=commit_proof(rollout,receipt,before,proof)
    return dict(status='installed_natural_publication_verified',proof=proof,proof_recorded=record)


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',required=True,type=Path)
    parser.add_argument('--record-proof',action='store_true')
    args=parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.receipt,record=args.record_proof),sort_keys=True))
        return 0
    except Exception:
        print('natural publication not verified; no release or control enabled',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
