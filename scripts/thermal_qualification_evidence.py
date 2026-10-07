"""Bounded, read-only thermal qualification accounting.

These summaries never authorize release. Raw captures and native receipts remain
primary evidence; incomplete origin/runtime bindings remain explicit blockers.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import gzip
from io import BytesIO
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from zoneinfo import ZoneInfo

from thermal_model.temperature_history import _validate_receipt

CAPSULE_SCHEMA = 'earthship-thermal-qualification-capsule/v1'
CAPSULE_FIELDS = {'schema', 'assessed_at', 'purpose', 'exact_repeat',
    'repeat_normalization', 'runtime_revision', 'requested_horizons',
    'production_writes', 'source_queries', 'files'}
HORIZONS = (1, 6, 12, 24, 48, 72)
HEX = re.compile('[0-9a-f]{64}')
SITE = ZoneInfo('America/Denver')


def _utc(value):
    if isinstance(value, str):
        try: value = datetime.fromisoformat(value)
        except ValueError: raise ValueError('aware evidence timestamp required') from None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware evidence timestamp required')
    return value.astimezone(timezone.utc)


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('finite evidence number required')
    return float(value)


def _digest(value):
    if not isinstance(value, str) or HEX.fullmatch(value) is None:
        raise ValueError('full evidence digest required')
    return value


def _metrics(values):
    if not values: return None
    return dict(mae_f=sum(map(abs, values))/len(values),
        rmse_f=math.sqrt(sum(value*value for value in values)/len(values)),
        bias_f=sum(values)/len(values))


def summarize_pairs(pairs, *, horizon_hours, artifact_sha256=None):
    """Summarize one immutable artifact, keeping missing comparator support visible."""
    if type(horizon_hours) is not int or horizon_hours not in HORIZONS:
        raise ValueError('supported evidence horizon required')
    if not isinstance(pairs, (list, tuple)) or len(pairs) > 1000:
        raise ValueError('bounded evidence pairs required')
    if artifact_sha256 is not None: _digest(artifact_sha256)
    prepared, identities, seen = [], set(), set()
    for row in pairs:
        if not isinstance(row, dict): raise ValueError('evidence pair required')
        issue, target = _utc(row.get('issue_at')), _utc(row.get('target_at'))
        if (not issue < target or
                abs((target-issue).total_seconds()-horizon_hours*3600) > 1800):
            raise ValueError('pair does not match declared horizon')
        artifact = _digest(row.get('artifact_sha256'))
        identity = (issue, target, artifact)
        if identity in seen: raise ValueError('duplicate evidence pair')
        seen.add(identity); identities.add(artifact)
        model, persistence = map(_number, (row.get('model_error_f'), row.get('persistence_error_f')))
        covered = row.get('interval_covered')
        if type(covered) is not bool or _number(row.get('interval_width_f')) < 0:
            raise ValueError('invalid interval evidence')
        baseline = row.get('recent_cycle_baseline', {})
        if not isinstance(baseline, dict): raise ValueError('comparator evidence required')
        recent = (_number(baseline.get('signed_error_f'))
                  if baseline.get('status') == 'available' else None)
        regime=row.get('regime','unbound')
        if regime not in {'warm','shoulder','winter','unbound'}:
            raise ValueError('declared evidence regime invalid')
        prepared.append((issue, target, artifact, model, persistence, recent, covered, regime))
    if artifact_sha256 is None and len(identities) > 1:
        raise ValueError('single artifact required; stratify changing candidates')
    artifact = artifact_sha256 or next(iter(identities), None)
    retained = [row for row in prepared if row[2] == artifact]
    independent, previous_target = [], None
    for row in sorted(retained, key=lambda value: (value[0], value[1])):
        if previous_target is None or row[0] >= previous_target:
            independent.append(row); previous_target = row[1]
    paired = [row for row in independent if row[5] is not None]
    return dict(schema='earthship-thermal-evidence-summary/v1',
        artifact_sha256=artifact, horizon_hours=horizon_hours,
        raw_pair_count=len(retained), independent_window_count=len(independent),
        unique_local_days=len({row[0].astimezone(SITE).date() for row in retained}),
        excluded_other_artifact_count=len(prepared)-len(retained),
        paired_three_predictor_count=len(paired),
        independent_local_days=len({row[0].astimezone(SITE).date() for row in independent}),
        independent_regime_counts={regime:sum(row[7]==regime for row in independent)
            for regime in ('warm','shoulder','winter','unbound')},
        metrics=dict(model=_metrics([row[3] for row in independent]),
                     persistence=_metrics([row[4] for row in independent]),
                     recent_cycle=_metrics([row[5] for row in paired])),
        three_predictor_metrics={name:_metrics([row[index] for row in paired])
            for name,index in (('model',3),('persistence',4),('recent_cycle',5))},
        interval_coverage=(sum(row[6] for row in independent)/len(independent)
                           if independent else None),
        independent_origins=[row[0].isoformat() for row in independent],
        nonoverlap_policy='UTC next_issue_at_or_after_prior_actual_target',
        release_qualification_claimed=False)


def _object(pairs):
    value = {}
    for key, entry in pairs:
        if key in value: raise ValueError('duplicate evidence key')
        value[key] = entry
    return value


def _json(raw):
    def reject(_): raise ValueError('nonfinite evidence JSON')
    try: return json.loads(raw, object_pairs_hook=_object, parse_constant=reject)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('invalid evidence JSON') from None


def _read_private(path, *, limit):
    try: info = path.lstat()
    except OSError: raise ValueError('evidence file missing') from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > limit):
        raise ValueError('owned bounded private evidence file required')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('evidence file changed')
        with os.fdopen(fd, 'rb', closefd=False) as stream: raw = stream.read(limit+1)
    finally: os.close(fd)
    if len(raw) != info.st_size or len(raw) > limit: raise ValueError('evidence size changed')
    return raw



def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()


def _captured_score_bindings(bodies, report, native):
    """Verify issued values against the captured output and native outcome.

    This verifies integrity/parity, not fit eligibility or a legacy model's
    scientific quality. Release proof still requires a new original binding.
    """
    values_fields={'output','current','raw_forecast','forecast_rows','artifact'}
    captures={}
    regimes={}
    for name,compressed in bodies.items():
        if not name.startswith('captures/') or not name.endswith('.json.gz'):
            continue
        if len(compressed)>256000:raise ValueError('compressed capture exceeds bound')
        try:
            with gzip.GzipFile(fileobj=BytesIO(compressed)) as stream:raw=stream.read(1000001)
        except (OSError,EOFError):raise ValueError('invalid compressed capture') from None
        if len(raw)>1000000:raise ValueError('capture exceeds decompressed bound')
        capture=_json(raw)
        if (not isinstance(capture,dict) or set(capture)!=values_fields|{
                'schema','decision_at','inputs_available_at','published_at','sha256'} or
                capture['schema']!='earthship-thermal-shadow-forcing-capture/v2' or
                not isinstance(capture['sha256'],dict) or set(capture['sha256'])!=values_fields):
            raise ValueError('closed artifact-bound original capture required')
        for field in values_fields:
            if sha256(_canonical(capture[field])).hexdigest()!=_digest(capture['sha256'][field]):
                raise ValueError('original capture input digest differs')
        issue=_utc(capture['decision_at'])
        if not _utc(capture['inputs_available_at'])<=issue<=_utc(capture['published_at']):
            raise ValueError('capture inputs were unavailable at issue')
        output=capture['output'];artifact=capture['artifact']
        if (not isinstance(output,dict) or type(output.get('version')) is not int or
                output['version']!=1 or output.get('status')!='shadow' or
                _utc(output.get('generatedAt'))!=issue or not isinstance(artifact,dict) or
                output.get('model',{}).get('codeRevision')!=artifact.get('code_revision')):
            raise ValueError('capture output/artifact binding differs')
        identity=(issue,capture['sha256']['artifact'])
        if identity in captures:raise ValueError('duplicate issued capture')
        captures[identity]=capture
        rows=capture['forecast_rows']
        eligible=([row for row in rows if isinstance(row,dict) and _utc(row.get('at'))<=issue]
                  if isinstance(rows,list) else [])
        mode='unbound'
        if eligible:
            latest=max(eligible,key=lambda row:_utc(row['at']))
            mode=latest.get('mode','unbound')
            timeline=latest.get('_modeTimeline',[])
            for entry in timeline:
                if not isinstance(entry,list) or len(entry)!=2:
                    raise ValueError('captured mode timeline invalid')
                if _utc(entry[0])<=issue:mode=entry[1]
        regime={'warm':'warm','spring':'shoulder','fall_charge':'shoulder','winter':'winter'}.get(mode,'unbound')
        regimes.setdefault(identity[1],{})[identity[0].isoformat()]=regime
    if not isinstance(report.get('results'),dict):raise ValueError('scored results missing')
    verified=0
    for raw_horizon,result in report['results'].items():
        try:horizon=int(raw_horizon)
        except (ValueError,TypeError):raise ValueError('scored horizon invalid') from None
        if str(horizon)!=raw_horizon or horizon not in HORIZONS or not isinstance(result,dict):
            raise ValueError('scored horizon invalid')
        pairs=result.get('pairs',[])
        artifacts={row.get('artifact_sha256') for row in pairs if isinstance(row,dict)}
        for artifact in artifacts:summarize_pairs(pairs,horizon_hours=horizon,artifact_sha256=artifact)
        for row in pairs:
            identity=(_utc(row['issue_at']),row['artifact_sha256'])
            capture=captures.get(identity)
            if capture is None:raise ValueError('score original capture missing')
            target=_utc(row['target_at'])
            receipt=native.get(('indoor',target))
            if receipt is None:raise ValueError('score native outcome missing')
            observed=_number(receipt['temperatureF'])
            output=capture['output']
            trajectory=output.get('forecast',{}).get('trajectory')
            if not isinstance(trajectory,list):raise ValueError('issued trajectory missing')
            matching=[point for point in trajectory if isinstance(point,dict) and _utc(point.get('at'))==target]
            if len(matching)!=1:raise ValueError('issued target missing or duplicated')
            point=matching[0]
            predicted,low,high=map(_number,(point.get('hallwayF'),point.get('lowF'),point.get('highF')))
            if not -40<=low<=predicted<=high<=140:raise ValueError('issued forecast outside bounds')
            current=_number(output.get('current',{}).get('hallwayF'))
            expected={'model_error_f':predicted-observed,'persistence_error_f':current-observed,
                      'interval_width_f':high-low}
            for field,value in expected.items():
                if not math.isclose(_number(row.get(field)),value,rel_tol=0,abs_tol=0.00051):
                    raise ValueError('score differs from original capture/native outcome')
            if row.get('interval_covered') is not (low<=observed<=high):
                raise ValueError('interval outcome differs')
            baseline=row.get('recent_cycle_baseline',{})
            if baseline.get('status')=='available':
                from thermal_recent_cycles import compare
                def read(targets,assessment):
                    values=[]
                    for at in targets:
                        original=native.get(('indoor',at))
                        receipt=(None if original is None else {**original,**{
                            key:_utc(original[key]) for key in ('receivedAt','storedAt','validUntil')}})
                        values.append((at,receipt))
                    return values
                calculated=compare(issue=identity[0],target=target,current_f=current,grid_reader=read)
                if (calculated['status']!='available' or
                        calculated['evidence_sha256']!=baseline.get('evidence_sha256') or
                        not math.isclose(_number(baseline.get('signed_error_f')),
                            calculated['prediction_f']-observed,rel_tol=0,abs_tol=0.00051)):
                    raise ValueError('recent-cycle baseline source binding differs')
            verified+=1
    return verified,len(captures),regimes


def verify_capsule(directory):
    """Verify immutable source bytes and native receipts without executing saved code.

    A v1 acquisition capsule is development evidence. It does not establish
    original runtime/initial-epoch identity merely from its acquisition manifest.
    """
    root = Path(directory)
    info = root.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != 0o700 or root.resolve() != root):
        raise ValueError('owned private capsule directory required')
    manifest_raw = _read_private(root/'manifest.json', limit=262144)
    manifest = _json(manifest_raw)
    if (not isinstance(manifest, dict) or set(manifest) != CAPSULE_FIELDS or
            manifest['schema'] != CAPSULE_SCHEMA or
            manifest['purpose'] != 'development_reassessment_not_release_holdout' or
            manifest['exact_repeat'] is not True or
            manifest['repeat_normalization'] != 'only verifier_runtime_root location; all scores and source hashes equal' or
            type(manifest['production_writes']) is not int or
            manifest['production_writes'] != 0 or type(manifest['source_queries']) is not int or
            not 0 <= manifest['source_queries'] <= 5000 or
            not isinstance(manifest['files'], dict) or not 3 <= len(manifest['files']) <= 512):
        raise ValueError('closed development capsule contract required')
    _utc(manifest['assessed_at']); _digest(manifest['runtime_revision'])
    horizons = manifest['requested_horizons']
    if (not isinstance(horizons, list) or not horizons or len(set(horizons)) != len(horizons) or
            any(type(h) is not int or h not in HORIZONS for h in horizons)):
        raise ValueError('unique supported capsule horizons required')
    total, bodies = 0, {}
    for name, expected in manifest['files'].items():
        if not isinstance(name, str): raise ValueError('safe capsule path required')
        relative = PurePosixPath(name)
        if (relative.is_absolute() or str(relative) != name or
                any(part in ('.','..') for part in relative.parts) or name == 'manifest.json'):
            raise ValueError('safe capsule path required')
        path = root/name
        if path.resolve() != path: raise ValueError('non-symlink evidence required')
        raw = _read_private(path, limit=20000000)
        total += len(raw)
        if total > 100000000 or sha256(raw).hexdigest() != _digest(expected):
            raise ValueError('source evidence changed or exceeds bound')
        bodies[name] = raw
    required = {'report.json','repeat-report.json','source-receipt-queries.json'}
    if not required <= bodies.keys(): raise ValueError('capsule source reports missing')
    report, repeat = map(_json, (bodies['report.json'],bodies['repeat-report.json']))
    if not isinstance(report,dict) or report != repeat:
        raise ValueError('source-bound repeat differs')
    queries = _json(bodies['source-receipt-queries.json'])
    if not isinstance(queries, list) or len(queries) != manifest['source_queries']:
        raise ValueError('native source query count differs')
    epochs, receipts, native = defaultdict(set), Counter(), {}
    for entry in queries:
        if not isinstance(entry, dict) or set(entry) != {'request','result'}:
            raise ValueError('closed native query required')
        request = entry['request']
        if (not isinstance(request, dict) or set(request) != {'stream','targets','assessed_at'} or
                request['stream'] not in {'indoor','north_wall','outdoor'} or
                not isinstance(request['targets'], list) or not 1 <= len(request['targets']) <= 289):
            raise ValueError('closed bounded thermal source request required')
        targets = [_utc(value) for value in request['targets']]
        assessed = _utc(request['assessed_at'])
        if targets != sorted(set(targets)) or targets[-1] > assessed:
            raise ValueError('native targets not qualified as of assessment')
        result = entry['result']
        if not isinstance(result,list) or len(result) != len(targets):
            raise ValueError('native grid incomplete')
        for target, row in zip(targets,result):
            if not isinstance(row,list) or len(row) != 2 or _utc(row[0]) != target:
                raise ValueError('native grid target mismatch')
            if row[1] is not None:
                _validate_receipt(row[1],target)
                identity=(request['stream'],target)
                if identity in native and native[identity]!=row[1]:
                    raise ValueError('conflicting native source receipts')
                native[identity]=row[1]
                epochs[request['stream']].add(row[1]['streamEpoch'])
                receipts[request['stream']] += 1
    pair_count,capture_count,regimes=_captured_score_bindings(bodies,report,native)
    if _read_private(root/'manifest.json',limit=262144) != manifest_raw:
        raise ValueError('capsule manifest changed during verification')
    return dict(schema='earthship-thermal-capsule-verification/v1',
        purpose=manifest['purpose'], report=report,
        manifest_sha256=sha256(manifest_raw).hexdigest(),
        source_file_count=len(bodies), qualified_native_receipts=dict(receipts),
        verified_as_issued_pairs=pair_count, original_capture_count=capture_count,
        captured_regimes=regimes,
        native_stream_epochs={key:sorted(value) for key,value in epochs.items()},
        release_qualification_claimed=False,
        release_binding_blockers=['initial_sensor_epochs_not_bound_at_issue',
                                  'publication_runtime_not_bound_at_issue'])


def reassess_capsule(directory, *, artifact_sha256=None):
    """Produce a source-bound descriptive report, stratified by full artifact ID."""
    verified=verify_capsule(directory)
    raw=verified.pop('report')
    regimes=verified.pop('captured_regimes')
    for result in raw.get('results',{}).values():
        for row in result.get('pairs',[]):
            row['regime']=regimes.get(row['artifact_sha256'],{}).get(_utc(row['issue_at']).isoformat(),'unbound')
    results=raw.get('results',{})
    artifacts=sorted({row['artifact_sha256'] for result in results.values()
                      for row in result.get('pairs',[])})
    if artifact_sha256 is not None:
        _digest(artifact_sha256)
        if artifact_sha256 not in artifacts:raise ValueError('selected artifact has no captured scored pair')
        artifacts=[artifact_sha256]
    return dict(schema='earthship-thermal-development-reassessment/v1',
        assessed_at=raw.get('assessed_at'),verification=verified,
        error_precision_f=0.001,regime_definition='as_issued_thermal_mode_warm_shouldering_winter',
        by_artifact={artifact:{horizon:summarize_pairs(result.get('pairs',[]),
            horizon_hours=int(horizon),artifact_sha256=artifact)
            for horizon,result in results.items()} for artifact in artifacts},
        recommended_mode='shadow',release_qualification_claimed=False,
        interpretation='Development evidence; no untouched holdout or release decision.')


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capsule',type=Path,required=True)
    parser.add_argument('--artifact-sha256')
    args=parser.parse_args()
    try:report=reassess_capsule(args.capsule,artifact_sha256=args.artifact_sha256)
    except (ValueError,OSError,KeyError,TypeError):
        print(json.dumps({'status':'refused','release_qualification_claimed':False}))
        return 2
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
