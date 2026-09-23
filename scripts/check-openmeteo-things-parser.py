#!/usr/bin/env python3
"""Offline syntax check of the prepared OpenMeteo Thing DSL using installed jars."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
jars = sorted(str(path) for path in Path('/usr/share/openhab/runtime/system').rglob('*.jar'))
parsers = [path for path in jars if Path(path).name.startswith('org.openhab.core.model.thing-')]
if len(parsers) != 1 or Path(parsers[0]).name != 'org.openhab.core.model.thing-5.2.1.jar':
    raise SystemExit('review installed Thing parser version before qualification')
result = subprocess.run(
    ['java', '-Xmx256m', '--class-path', ':'.join(jars),
     str(root / 'scripts/HexOpenMeteoThingsParse.java'),
     str(root / 'openhab/file-config/things/openmeteo.things')],
    capture_output=True, text=True, timeout=45,
)
expected = ['model=ThingModel', 'declarations=3',
            'negative_syntax_rejected=true', 'syntax_errors=0']
actual = [line for line in result.stdout.splitlines() if line.startswith((
    'model=', 'declarations=', 'negative_syntax_rejected=', 'syntax_errors='))]
if result.returncode or actual != expected:
    raise SystemExit('offline OpenMeteo Thing parser qualification failed; inspect parser/dependencies')
print('OpenHAB 5.2.1: prepared OpenMeteo Things syntax parsed; malformed syntax rejected')
print('Effective configuration, dynamic channels and provider handoff remain unqualified')
