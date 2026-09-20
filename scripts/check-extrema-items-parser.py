#!/usr/bin/env python3
"""Offline prepared-extrema syntax qualification using installed OpenHAB jars."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
jars = sorted(str(p) for p in Path('/usr/share/openhab/runtime/system').rglob('*.jar'))
parsers = [p for p in jars if Path(p).name.startswith('org.openhab.core.model.item-')]
if len(parsers) != 1 or Path(parsers[0]).name != 'org.openhab.core.model.item-5.2.1.jar':
    raise SystemExit('review installed parser version before qualification')
result = subprocess.run(['java', '-Xmx256m', '--class-path', ':'.join(jars),
                         str(root / 'scripts/HexExtremaItemsParse.java'),
                         str(root / 'openhab/file-config/items/temperature-extrema.items')],
                        capture_output=True, text=True, timeout=45)
actual = [line for line in result.stdout.splitlines()
          if line.startswith(('item=', 'negative_syntax_rejected=', 'syntax_errors='))]
expected = ['item=IndoorTemp_24h_High', 'item=IndoorTemp_24h_Low',
            'item=OutdoorTemp_24h_High', 'item=OutdoorTemp_24h_Low',
            'negative_syntax_rejected=true', 'syntax_errors=0']
if result.returncode or actual != expected:
    raise SystemExit('offline extrema parser qualification failed; inspect parser/dependencies')
print('OpenHAB 5.2.1: four prepared Item identities parsed; malformed syntax rejected')
print('Provider ownership, generated semantics, units and state recovery remain unqualified')
