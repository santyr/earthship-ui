"""A read deadline governs acquisition, not later offline result verification."""
from hashlib import sha256
import pytest


def reader(tmp_path):
    from household_native_score_queries import RecentCycleWindowReader
    from thermal_model.capture_readers import ReadBudget
    from thermal_model.installed_shade_score_inputs import SOURCE_PATHS
    tmp_path.chmod(0o700);clock=[0.];value=RecentCycleWindowReader.__new__(RecentCycleWindowReader)
    value.shared_lock_guard=lambda:None;value.settings={};value.hashes={}
    for name in SOURCE_PATHS:
        path=tmp_path/name;path.write_bytes(b'synthetic private configuration');path.chmod(0o600)
        value.settings[name]=str(path);value.hashes[name]=sha256(path.read_bytes()).hexdigest()
    value.budget=ReadBudget(50,clock=lambda:clock[0],guard=value.shared_lock_guard)
    return value,clock


def test_completed_acquisition_can_verify_sources_under_job_deadline(tmp_path):
    value,clock=reader(tmp_path);clock[0]=51
    value.verify_unchanged()
    with pytest.raises(ValueError,match='capture read deadline'):
        value._acquisition_check()


def test_post_acquisition_verification_still_checks_original_configuration(tmp_path):
    from pathlib import Path
    value,clock=reader(tmp_path);clock[0]=51
    Path(value.settings['token_file']).write_bytes(b'changed synthetic configuration')
    with pytest.raises(ValueError,match='configuration changed'):value.verify_unchanged()


def test_post_acquisition_verification_remains_inside_whole_job_guard(tmp_path):
    value,clock=reader(tmp_path);clock[0]=51
    def expired():raise ValueError('score lifetime elapsed')
    value.shared_lock_guard=expired
    with pytest.raises(ValueError,match='score lifetime elapsed'):value.verify_unchanged()
