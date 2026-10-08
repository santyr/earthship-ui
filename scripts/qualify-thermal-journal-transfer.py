#!/usr/bin/env python3
"""Run a private transferred-journal rehearsal on the approved off-host worker."""
import argparse,json,sys,subprocess
import psycopg2
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from thermal_journal_restore_transfer import qualify_journal_transfer


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transfer',required=True,type=Path)
    parser.add_argument('--consumer-runtime',required=True,type=Path)
    parser.add_argument('--expected-consumer-revision',required=True)
    parser.add_argument('--expected-interpreter-sha256',required=True)
    parser.add_argument('--proof-directory',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        path=qualify_journal_transfer(package=args.transfer,consumer_runtime=args.consumer_runtime,
            expected_consumer_revision=args.expected_consumer_revision,
            expected_interpreter_sha256=args.expected_interpreter_sha256,proof_directory=args.proof_directory)
    except (OSError,RuntimeError,TypeError,ValueError,subprocess.SubprocessError,psycopg2.Error):
        print('off-host journal rehearsal withheld; check private inputs, pinned consumer and owned cleanup',file=sys.stderr)
        return 2
    print(json.dumps(dict(status='disposable_journal_rehearsal_recorded',report_path=str(path),journal_recovery_qualified=False,installed=False,release_authorized=False)))
    return 0


if __name__=='__main__':raise SystemExit(main())
