#!/usr/bin/env python3
"""Validate one available thermal shadow JSON document from standard input."""

import json
import sys

from thermal_model.schema import validate_shadow_output


MAX_SHADOW_BYTES = 16 * 1024


def main():
    encoded = sys.stdin.buffer.read(MAX_SHADOW_BYTES)
    if len(encoded) >= MAX_SHADOW_BYTES:
        raise ValueError("thermal shadow state must be below 16 KiB")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("thermal shadow state must be UTF-8 JSON") from exc
    validate_shadow_output(payload)
    if payload["confidence"]["grade"] == "unavailable":
        raise ValueError("unavailable thermal shadow state cannot be published")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError) as exc:
        print(f"invalid thermal shadow state: {exc}", file=sys.stderr)
        raise SystemExit(1)
