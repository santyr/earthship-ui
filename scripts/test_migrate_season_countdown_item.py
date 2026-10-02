"""No-network checks of the exact countdown display writer contract."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('countdown_item_contract', Path(__file__).with_name('migrate-season-countdown-item.py'))
m = module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def writer(monkeypatch, tmp_path):
    row = {'uid': m.RULE, 'editable': False,
        'status': {'status': 'IDLE', 'statusDetail': 'NONE'},
        'triggers': [{'type': 'core.ItemStateChangeTrigger',
                      'configuration': {'itemName': 'Sun_TimeLeft'}}],
        'conditions': [], 'actions': [{'type': 'jsr223.ScriptedAction',
                                     'configuration': {'privId': 'i4'}}]}
    source = Path(__file__).resolve().parents[1]/'openhab/file-config/automation/js/update_days_until_season.js'
    installed = tmp_path/'update_days_until_season.js'
    installed.write_bytes(source.read_bytes())
    monkeypatch.setattr(m, 'WRITER_TARGET', installed)
    def get(path):
        assert path == '/rules/'+m.RULE
        return deepcopy(row)
    monkeypatch.setattr(m.migration.oh, 'get', get)
    return row, installed


@pytest.mark.parametrize('identifier', ['i0', 'i4', 'i512'])
def test_writer_registration_id_can_change_after_restart(writer, identifier):
    row, _ = writer
    row['actions'][0]['configuration']['privId'] = identifier
    assert m.rule_idle() == row


@pytest.mark.parametrize('identifier', [None, True, 4, '', 'i', 'i-1', 'other', 'i4\n', 'i'+'1'*100])
def test_unknown_registration_identifier_is_not_accepted(writer, identifier):
    row, _ = writer
    row['actions'][0]['configuration']['privId'] = identifier
    with pytest.raises(RuntimeError): m.rule_idle()


@pytest.mark.parametrize('damage', ['extra_action', 'wrong_action', 'extra_config',
    'wrong_trigger', 'extra_trigger', 'conditions', 'managed', 'wrong_uid', 'unhealthy'])
def test_runtime_id_flexibility_preserves_exact_writer_contract(writer, damage):
    row, _ = writer
    if damage == 'extra_action': row['actions'].append(deepcopy(row['actions'][0]))
    elif damage == 'wrong_action': row['actions'][0]['type'] = 'other.Action'
    elif damage == 'extra_config': row['actions'][0]['configuration']['script'] = 'unknown'
    elif damage == 'wrong_trigger': row['triggers'][0]['configuration']['itemName'] = 'BMS_SOC'
    elif damage == 'extra_trigger': row['triggers'].append(deepcopy(row['triggers'][0]))
    elif damage == 'conditions': row['conditions'] = [{'type':'unknown.Condition'}]
    elif damage == 'managed': row['editable'] = True
    elif damage == 'wrong_uid': row['uid'] = 'different_rule'
    else: row['status']['status'] = 'UNINITIALIZED'
    with pytest.raises(RuntimeError): m.rule_idle()


def test_source_pin_remains_required_for_valid_runtime_identifier(writer):
    _, installed = writer
    installed.write_bytes(b'changed source')
    with pytest.raises(RuntimeError, match='source drift'): m.rule_idle()


def test_symlinked_writer_source_is_not_accepted(writer, tmp_path):
    _, installed = writer
    other = tmp_path/'other.js'
    installed.rename(other)
    installed.symlink_to(other)
    with pytest.raises(RuntimeError, match='source drift'): m.rule_idle()


def test_closed_apply_gate_still_refuses_before_preflight(monkeypatch):
    monkeypatch.setattr(m, 'preflight', lambda *_: pytest.fail('preflight reached'))
    with pytest.raises(SystemExit): m.main(['--apply'])
