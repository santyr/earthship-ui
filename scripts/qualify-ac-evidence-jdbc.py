#!/usr/bin/env python3
"""Disconnected AC-exclusion and immutable-JDBC rehearsal; no production writes."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('jdbc_fixture',
    Path(__file__).with_name('qualify-persistence-jdbc.py'))
jdbc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jdbc)

if __name__ == '__main__':
    candidate = ROOT / 'openhab/file-config/persistence/jdbc.persist'
    with jdbc.Database(candidate_ac=True) as database:
        jdbc.provider.main(database, candidate=candidate)
