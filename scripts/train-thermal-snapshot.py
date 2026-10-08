#!/usr/bin/env python3
"""Verify private inputs or explicitly fit a shadow candidate on an off-host worker."""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from thermal_model.artifacts import ArtifactRegistry
from thermal_model.forcing_capture import _canonical,_private_directory
from thermal_model.pipeline import TrainingRefused
from thermal_model.training_inputs import read_training_inputs
from thermal_model.offline_training import run_snapshot_training
from thermal_intel import _release_runtime_paths
from thermal_model.origin_capture import _source_bytes

ROOT=Path(__file__).resolve().parents[1]


def _fit_code_revision():
    names=["openhab/scripts/"+name for name in _release_runtime_paths()]
    names+= ["openhab/scripts/thermal_model/training_inputs.py",
        "openhab/scripts/thermal_model/offline_training.py","scripts/train-thermal-snapshot.py"]
    digest=sha256()
    for name in dict.fromkeys(names):
        raw=_source_bytes(ROOT/name,maximum=2000000);encoded=name.encode()
        digest.update(len(encoded).to_bytes(4,"big"));digest.update(encoded)
        digest.update(len(raw).to_bytes(8,"big"));digest.update(raw)
    return digest.hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True,type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify-only',action='store_true')
    mode.add_argument('--fit',action='store_true')
    parser.add_argument('--state-dir',type=Path)
    parser.add_argument('--fit-evidence-dir',type=Path)
    args=parser.parse_args(argv)
    if args.fit and (args.state_dir is None or args.fit_evidence_dir is None):parser.error('fit requires explicit state and proof directories')
    if args.verify_only and (args.state_dir is not None or args.fit_evidence_dir is not None):parser.error('verification does not use fit directories')
    try:
        if args.fit:
            if os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT')!='1':raise ValueError('explicit remote fitting opt-in required')
            state=_private_directory(args.state_dir);proof=_private_directory(args.fit_evidence_dir)
            if state==proof or state.is_relative_to(proof) or proof.is_relative_to(state):raise ValueError('separate fit directories required')
            if any(state.iterdir()) or any(proof.iterdir()):raise ValueError('new empty fit directories required')
        record=read_training_inputs(args.snapshot)
        if args.verify_only:
            result=dict(status='inputs_verified',snapshot_sha256=record['snapshot_sha256'],release_authorized=False)
        else:
            trained=run_snapshot_training(record,registry=ArtifactRegistry(state),fit_evidence_directory=proof,
                clock=lambda:datetime.now(timezone.utc),revision_reader=_fit_code_revision)
            result=dict(status='shadow_candidate',snapshot_sha256=record['snapshot_sha256'],
                artifact_sha256=sha256(_canonical(asdict(trained.artifact))).hexdigest(),release_authorized=False,automatic_actuation=False)
    except TrainingRefused:
        print(json.dumps(dict(status='training_refused',release_authorized=False)))
        return 1
    except (OSError,RuntimeError,TypeError,ValueError):
        print('offline thermal training refused; check private inputs and isolated destinations',file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__':raise SystemExit(main())
