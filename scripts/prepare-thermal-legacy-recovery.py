#!/usr/bin/env python3
"""Prepare or verify original v4 recovery bytes; never installs or executes them."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from thermal_model.environment_bundle import _pacer
from thermal_model.forcing_capture import _private_directory
from thermal_model.legacy_recovery import FLAGS, _document, prepare_legacy_generation, verify_legacy_generation
from thermal_model.rollback import REASONS
from thermal_model.runtime_bundle import _owned_bytes

INPUT_FIELDS={'artifact_path','output_path','source_bundle','source_root','revision_paths',
              'environment_bundles','interpreter','native_bindings'}
MAX_INPUT_BYTES=128000


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,help='owned mode-0600 JSON in a private directory; exact API input fields')
    parser.add_argument('--destination',required=True,type=Path)
    parser.add_argument('--reason',required=True,choices=sorted(REASONS))
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--max-read-bytes-per-second',type=int,help='optional aggregate read pacing; continue using the resource-limited scope')
    args=parser.parse_args(argv)
    if args.verify_only and args.inputs is not None:parser.error('--inputs is only used during preparation')
    if not args.verify_only and args.inputs is None:parser.error('--inputs is required during preparation')
    try:
        rate=args.max_read_bytes_per_second
        pace=_pacer(rate)
        if args.verify_only:
            record=verify_legacy_generation(args.destination,max_read_bytes_per_second=rate)
            if record['reason']!=args.reason:raise ValueError('legacy recovery reason differs')
        else:
            _private_directory(args.inputs.parent)
            if pace is not None:pace.reserve(MAX_INPUT_BYTES)
            inputs=_document(_owned_bytes(args.inputs,MAX_INPUT_BYTES))
            if not isinstance(inputs,dict) or set(inputs)!=INPUT_FIELDS:raise ValueError('exact preparation inputs required')
            record=prepare_legacy_generation(args.destination,reason=args.reason,max_read_bytes_per_second=rate,**inputs)
    except (OSError,RuntimeError,TypeError,ValueError):
        print('legacy thermal recovery refused; check private inputs, retained archives and destination',file=sys.stderr)
        return 2
    receipt={key:record[key] for key in {'schema','generation_sha256','reason'}|FLAGS}
    print(json.dumps(receipt,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__':raise SystemExit(main())
