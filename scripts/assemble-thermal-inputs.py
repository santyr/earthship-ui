#!/usr/bin/env python3
"""Guardedly assemble private measurement snapshots with a fresh journal view."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'openhab/scripts'))
from thermal_model.capture_guard import verify_resource_limits,run_guarded_capture

RECEIPT_FIELDS={'status','snapshot_sha256','binding_sha256','fitting_executed','installed','release_authorized'}


def _context(parts,dsn_file,destination):
    from thermal_model.training_assembly import inspect_training_parts
    from thermal_model.forcing_capture import _private_directory,_canonical
    from thermal_model.runtime_bundle import _owned_bytes
    from thermal_model.capture_readers import bounded_journal_dsn
    metadata=inspect_training_parts(parts);root=_private_directory(Path(destination));dsn_file=Path(dsn_file)
    if any(root.iterdir()):raise ValueError('new empty private assembly destination required')
    if not dsn_file.is_absolute() or dsn_file.resolve()!=dsn_file:raise ValueError('resolved private journal configuration required')
    _private_directory(dsn_file.parent);raw=_owned_bytes(dsn_file,4096);bounded_journal_dsn(raw.decode().strip())
    for path in [dsn_file]+[Path(row['path']) for row in metadata]:
        if path.is_relative_to(root) or root==path.parent:raise ValueError('separate source and assembly directories required')
    info=dsn_file.lstat()
    identity=dict(parts=metadata,journal=dict(path=str(dsn_file),device=info.st_dev,inode=info.st_ino,size=info.st_size,mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns))
    return metadata,root,sha256(_canonical(identity)).hexdigest()


def _assembly_revision():
    from thermal_model.origin_capture import _source_bytes
    spec=importlib.util.spec_from_file_location('capture_revision_helper',ROOT/'scripts/capture-thermal-inputs.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    digest=sha256(bytes.fromhex(helper._capture_revision()))
    for name in ('openhab/scripts/thermal_model/training_assembly.py','scripts/assemble-thermal-inputs.py'):
        raw=_source_bytes(ROOT/name,maximum=2000000);encoded=name.encode()
        digest.update(len(encoded).to_bytes(4,'big'));digest.update(encoded)
        digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
    return digest.hexdigest()


def _worker(parts,dsn_file,root,expected):
    from thermal_model.training_assembly import read_training_parts,assemble_training_inputs,write_training_assembly
    from thermal_model.training_inputs import write_training_inputs
    from thermal_model.capture_backends import configured_capture_journal
    from thermal_model.capture_readers import ReadBudget
    from thermal_model.runtime_bundle import _owned_bytes,_write_private,_sync_directory
    from thermal_model.forcing_capture import _canonical
    revision=_assembly_revision();records=read_training_parts(parts)
    if _context(parts,dsn_file,root)[-1]!=expected:raise ValueError('assembly sources changed while loading')
    journal=configured_capture_journal(dsn=_owned_bytes(Path(dsn_file),4096).decode().strip(),budget=ReadBudget(70))
    record,binding=assemble_training_inputs(records,journal=journal,clock=lambda:datetime.now(timezone.utc),revision_reader=_assembly_revision)
    if record['collection_code_revision']!=revision or _context(parts,dsn_file,root)[-1]!=expected:
        raise ValueError('assembly code or sources changed during collection')
    write_training_assembly(root,record,binding,records)
    write_training_inputs(root,record)
    receipt=dict(status='inputs_assembled',snapshot_sha256=record['snapshot_sha256'],binding_sha256=binding['binding_sha256'],fitting_executed=False,installed=False,release_authorized=False)
    _write_private(root/'assembly-receipt.json',_canonical(receipt));_sync_directory(root)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--part',required=True,action='append',type=Path)
    parser.add_argument('--journal-dsn-file',required=True,type=Path)
    parser.add_argument('--destination',required=True,type=Path)
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--expected-context-digest',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    try:
        if not args.check_only and os.environ.get('EARTHSHIP_THERMAL_INPUT_CAPTURE')!='1':raise ValueError('explicit assembly intent required')
        verify_resource_limits()
        if args.worker and (args.check_only or os.environ.get('EARTHSHIP_GUARDED_CAPTURE_WORKER')!='1' or os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT')!='0' or os.getpriority(os.PRIO_PROCESS,0)<15):
            raise ValueError('guarded assembly worker required')
        metadata,root,digest=_context(args.part,args.journal_dsn_file,args.destination)
        if args.check_only:receipt=dict(status='assembly_paths_verified',release_authorized=False)
        elif args.worker:
            if digest!=args.expected_context_digest:raise ValueError('assembly context changed')
            _worker(args.part,args.journal_dsn_file,root,digest);return 0
        else:
            worker=[sys.executable,str(Path(__file__).resolve()),'--journal-dsn-file',str(args.journal_dsn_file),'--destination',str(root),'--worker','--expected-context-digest',digest]
            for path in args.part:worker+=['--part',str(path)]
            if run_guarded_capture(worker,seconds=90)!=0:raise ValueError('assembly worker refused')
            from thermal_model.runtime_bundle import _owned_bytes
            from thermal_model.origin_capture import _object
            from thermal_model.graduation_policy import _sha
            receipt=json.loads(_owned_bytes(root/'assembly-receipt.json',2048),object_pairs_hook=_object)
            if set(receipt)!=RECEIPT_FIELDS or receipt['status']!='inputs_assembled' or any(receipt[key] is not False for key in ('fitting_executed','installed','release_authorized')):
                raise ValueError('closed assembly receipt required')
            _sha(receipt['snapshot_sha256']);_sha(receipt['binding_sha256'])
    except (OSError,RuntimeError,TypeError,ValueError):
        print('thermal input assembly refused; check private sources, caps and source permissions',file=sys.stderr);return 2
    print(json.dumps(receipt,sort_keys=True,separators=(',',':')));return 0


if __name__=='__main__':raise SystemExit(main())
