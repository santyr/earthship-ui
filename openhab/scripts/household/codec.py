"""Canonical bounded JSON for foundation identity and replay."""
import json
from datetime import datetime
from hashlib import sha256


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def loads(raw):
    def refuse(_): raise ValueError('nonfinite JSON refused')
    result = json.loads(raw, object_pairs_hook=_unique, parse_constant=refuse)
    if not isinstance(result, dict): raise ValueError('JSON object required')
    return result


def canonical(value):
    def encode(item):
        if isinstance(item, datetime): return item.isoformat()
        raise TypeError('unsupported canonical value')
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, default=encode).encode('utf-8')


def identity(value):
    return sha256(canonical(value)).hexdigest()
