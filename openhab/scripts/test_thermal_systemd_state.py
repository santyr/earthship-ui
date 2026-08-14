import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/thermal-systemd-state.py"
SPEC = importlib.util.spec_from_file_location("thermal_systemd_state", SCRIPT)
thermal_systemd_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(thermal_systemd_state)


def fake_runner(values, *, failure=None):
    def run(command, **kwargs):
        unit = command[3]
        property_name = command[4].removeprefix("--property=")
        if failure == (unit, property_name):
            return SimpleNamespace(
                returncode=1, stdout="", stderr="Failed to connect to bus",
            )
        return SimpleNamespace(
            returncode=0,
            stdout=values[(unit, property_name)] + "\n",
            stderr="",
        )
    return run


def missing_values():
    return {
        (unit, property_name): value
        for unit in thermal_systemd_state.UNITS
        for property_name, value in (
            ("LoadState", "not-found"),
            ("ActiveState", "inactive"),
            ("UnitFileState", ""),
        )
    }


def installed_values():
    values = {
        (unit, "LoadState"): "loaded"
        for unit in thermal_systemd_state.UNITS
    }
    values.update({
        (unit, "ActiveState"): "inactive"
        for unit in thermal_systemd_state.UNITS
    })
    values.update({
        (unit, "UnitFileState"): (
            "static" if unit.endswith(".service") else "disabled"
        )
        for unit in thermal_systemd_state.UNITS
    })
    return values


def test_first_install_requires_exact_missing_inactive_unfiled_state():
    assert thermal_systemd_state.assert_profile(
        "first-install", run=fake_runner(missing_values()),
    ) == "first-install"
    values = missing_values()
    values[("thermal-model-shadow.timer", "LoadState")] = "loaded"
    with pytest.raises(RuntimeError, match="first-install"):
        thermal_systemd_state.assert_profile(
            "first-install", run=fake_runner(values),
        )


def test_probe_rejects_user_manager_or_transport_errors():
    with pytest.raises(RuntimeError, match="systemctl probe failed"):
        thermal_systemd_state.assert_profile(
            "first-install",
            run=fake_runner(
                missing_values(),
                failure=("thermal-model-train.service", "LoadState"),
            ),
        )


def test_rollback_precheck_distinguishes_complete_missing_or_installed_sets():
    assert thermal_systemd_state.assert_profile(
        "rollback-precheck", run=fake_runner(missing_values()),
    ) == "missing"
    assert thermal_systemd_state.assert_profile(
        "rollback-precheck", run=fake_runner(installed_values()),
    ) == "installed"
    mixed = installed_values()
    for property_name, value in (
        ("LoadState", "not-found"),
        ("ActiveState", "inactive"),
        ("UnitFileState", ""),
    ):
        mixed[("thermal-model-shadow.timer", property_name)] = value
    with pytest.raises(RuntimeError, match="mixed or unexpected"):
        thermal_systemd_state.assert_profile(
            "rollback-precheck", run=fake_runner(mixed),
        )


def test_installed_quiescent_and_enabled_profiles_are_exact():
    installed = installed_values()
    assert thermal_systemd_state.assert_profile(
        "installed-disabled", run=fake_runner(installed),
    ) == "installed-disabled"
    quiescent = dict(installed)
    assert thermal_systemd_state.assert_profile(
        "rollback-quiescent", run=fake_runner(quiescent),
    ) == "rollback-quiescent"
    enabled = dict(installed)
    for unit in thermal_systemd_state.TIMERS:
        enabled[(unit, "ActiveState")] = "active"
        enabled[(unit, "UnitFileState")] = "enabled"
    assert thermal_systemd_state.assert_profile(
        "timers-enabled", run=fake_runner(enabled),
    ) == "timers-enabled"


def test_service_success_probe_checks_result_and_exec_status_without_conflation():
    values = installed_values()
    for unit in thermal_systemd_state.SERVICES:
        values[(unit, "Result")] = "success"
        values[(unit, "ExecMainStatus")] = "0"
    assert thermal_systemd_state.assert_profile(
        "services-succeeded", run=fake_runner(values),
    ) == "services-succeeded"
    values[("thermal-model-shadow.service", "ExecMainStatus")] = "1"
    with pytest.raises(RuntimeError, match="services-succeeded"):
        thermal_systemd_state.assert_profile(
            "services-succeeded", run=fake_runner(values),
        )
