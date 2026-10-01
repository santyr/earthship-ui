#!/usr/bin/env python3
"""Reuse one isolated JDBC pair for Moon state/history recovery.

Synthetic phase/fraction values, Group fixture, rollback and restart never touch
production. This is not a natural Astro writer or live-history qualification.
"""
from decimal import Decimal, InvalidOperation
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'moon_jdbc_rehearsal', ROOT / 'scripts/qualify-forecast-json-jdbc.py')
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)
spec = importlib.util.spec_from_file_location(
    'moon_provider_source', ROOT / 'scripts/qualify-moon-phase-provider.py')
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)

VALUES = {'Moon_MoonPhaseName': 'WAXING_GIBBOUS', 'Moon_MoonIllumination': '0.425'}
TYPES = {name: reading['type'] for name, reading in provider.READINGS.items()}
BASE_SAME_STATE = rehearsal.same_state


def same_state(actual, expected, item_type='String'):
    if item_type != 'Number:Dimensionless':
        return BASE_SAME_STATE(actual, expected, item_type)
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    try:
        left, right = Decimal(actual), Decimal(expected)
        return (left.is_finite() and right.is_finite()
                and 0 <= left <= 1 and 0 <= right <= 1 and left == right)
    except InvalidOperation:
        return False


def main():
    provider.checked_source()  # Fail before any allocation on staged-source drift.
    # The actual Astro Item defaults to unit 'one'. Do not silently accept a
    # percent reconfiguration, remove units, or test a 100x different quantity.
    illumination = rehearsal.oh.get('/items/Moon_MoonIllumination?metadata=.*')
    if not provider.exact_definition(illumination, 'Moon_MoonIllumination', managed=True):
        raise ValueError('live Moon dimensionless contract changed')
    rehearsal.same_state = same_state
    rehearsal.main(items=VALUES, source_path=provider.SOURCE, types=TYPES,
                   setup_sources=(('items/moon-group-fixture.items', b'Group Moon\n'),))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Moon JDBC rehearsal failed: ' + type(error).__name__) from None
