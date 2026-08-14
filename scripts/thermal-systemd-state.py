#!/usr/bin/env python3
"""Fail-closed exact state probes for the four staged thermal user units."""

import argparse
import subprocess


SERVICES = (
    "thermal-model-train.service",
    "thermal-model-shadow.service",
)
TIMERS = (
    "thermal-model-train.timer",
    "thermal-model-shadow.timer",
)
UNITS = SERVICES + TIMERS
_BASE_PROPERTIES = ("LoadState", "ActiveState", "UnitFileState")


def _property(unit, property_name, *, run=subprocess.run):
    result = run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            f"--property={property_name}",
            "--value",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"systemctl probe failed for {unit} {property_name}"
        )
    value = result.stdout.rstrip("\n")
    if "\n" in value or "\r" in value:
        raise RuntimeError(
            f"systemctl probe returned multiple values for {unit} {property_name}"
        )
    return value


def snapshot(*, properties=_BASE_PROPERTIES, run=subprocess.run):
    return {
        unit: {
            property_name: _property(unit, property_name, run=run)
            for property_name in properties
        }
        for unit in UNITS
    }


def _missing(state):
    return all(
        values
        == {
            "LoadState": "not-found",
            "ActiveState": "inactive",
            "UnitFileState": "",
        }
        for values in state.values()
    )


def _installed_disabled(state):
    for unit, values in state.items():
        expected_file_state = "static" if unit in SERVICES else "disabled"
        if values != {
            "LoadState": "loaded",
            "ActiveState": "inactive",
            "UnitFileState": expected_file_state,
        }:
            return False
    return True


def _installed_known(state):
    service_active = {
        "inactive", "active", "activating", "deactivating", "failed"
    }
    timer_active = {
        "inactive", "active", "activating", "deactivating", "failed"
    }
    for unit, values in state.items():
        if values["LoadState"] != "loaded":
            return False
        if unit in SERVICES:
            if (
                values["ActiveState"] not in service_active
                or values["UnitFileState"] != "static"
            ):
                return False
        elif (
            values["ActiveState"] not in timer_active
            or values["UnitFileState"] not in {"disabled", "enabled"}
        ):
            return False
    return True


def assert_profile(profile, *, run=subprocess.run):
    if profile == "services-succeeded":
        state = snapshot(run=run)
        if not _installed_disabled(state):
            raise RuntimeError(
                "systemd state does not satisfy services-succeeded"
            )
        for unit in SERVICES:
            if (
                _property(unit, "Result", run=run) != "success"
                or _property(unit, "ExecMainStatus", run=run) != "0"
            ):
                raise RuntimeError(
                    f"systemd state does not satisfy {profile}: {unit}"
                )
        return profile

    state = snapshot(run=run)
    if profile == "first-install":
        if not _missing(state):
            raise RuntimeError("systemd state does not satisfy first-install")
        return profile
    if profile in {"installed-disabled", "rollback-quiescent"}:
        if not _installed_disabled(state):
            raise RuntimeError(f"systemd state does not satisfy {profile}")
        return profile
    if profile == "timers-enabled":
        for unit, values in state.items():
            expected = {
                "LoadState": "loaded",
                "ActiveState": "active" if unit in TIMERS else "inactive",
                "UnitFileState": "enabled" if unit in TIMERS else "static",
            }
            if values != expected:
                raise RuntimeError(
                    f"systemd state does not satisfy {profile}: {unit}"
                )
        return profile
    if profile == "rollback-precheck":
        if _missing(state):
            return "missing"
        if _installed_known(state):
            return "installed"
        raise RuntimeError("systemd state is mixed or unexpected for rollback")
    raise ValueError(f"unknown systemd profile: {profile}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "profile",
        choices=(
            "first-install",
            "installed-disabled",
            "services-succeeded",
            "timers-enabled",
            "rollback-precheck",
            "rollback-quiescent",
        ),
    )
    args = parser.parse_args(argv)
    print(assert_profile(args.profile))


if __name__ == "__main__":
    main()
