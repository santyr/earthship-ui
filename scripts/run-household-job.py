#!/usr/bin/env python3
"""Repository entry point for the sealed shared-resource job launcher."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from household_job_run import main

if __name__ == '__main__':raise SystemExit(main())
