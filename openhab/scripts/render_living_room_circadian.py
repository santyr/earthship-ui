#!/usr/bin/env python3
"""Render the Git-owned managed lighting rule as a secret-free REST DTO.

This command prints configuration only. It does not contact openHAB or change
providers. Redirect its output to a file for reviewed REST PUT or recovery.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
rule = json.loads((root / 'openhab/living-room-circadian-resources.json').read_text())['rule']
assert rule['uid'] == 'hex_living_room_circadian'
for action in rule['actions']:
    config = action['configuration']
    source = config.pop('scriptSource')
    assert source == 'openhab/rules/living-room-circadian.js'
    config['script'] = (root / source).read_text()
print(json.dumps(rule, indent=2))
