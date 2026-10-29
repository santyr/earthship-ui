#!/usr/bin/env python3
"""Retain a captured read-only motor acquisition; never issue a device command."""
import argparse
from pathlib import Path
from household.codec import loads
from household_observation import _private_file,_directory
from household.advice.shade_state import normalize_event,ShadeHistory


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('mapping','acquisition','history'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    _directory(args.history.absolute().parent)
    mapping=loads(_private_file(args.mapping.absolute(),8192)[0]);packet=loads(_private_file(args.acquisition.absolute(),8192)[0])
    result=ShadeHistory(args.history.absolute()).ingest(normalize_event(mapping,packet))
    print(result);return 0


if __name__=='__main__':raise SystemExit(main())
