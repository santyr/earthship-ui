"""The file-first Astro icon map keeps all phases usable without network icons."""
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / 'transform' / 'astro.map'


def test_astro_map_covers_all_moon_phases_and_day_night_states():
    mapping = {}
    for line in SOURCE.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        assert key and key not in mapping
        assert value.startswith('iconify:mdi:')
        mapping[key] = value
    assert set(mapping) == {
        'NEW', 'FIRST_QUARTER', 'WAXING_CRESCENT', 'WAXING_GIBBOUS',
        'FULL', 'WANING_GIBBOUS', 'THIRD_QUARTER', 'WANING_CRESCENT',
        'CIVIL_DAWN', 'ASTRO_DAWN', 'NAUTIC_DAWN', 'SUN_RISE',
        'SUN_SET', 'CIVIL_DUSK', 'NAUTIC_DUSK', 'ASTRO_DUSK',
        'DAYLIGHT', 'NOON', 'NIGHT', 'MIDNIGHT', 'MORNING_NIGHT', 'EVENING_NIGHT',
    }
    assert all(mapping[key] == 'iconify:mdi:weather-night'
               for key in ('NIGHT', 'MIDNIGHT', 'MORNING_NIGHT', 'EVENING_NIGHT'))
