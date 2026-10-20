"""Disposable browser auth must refuse absent opt-in and production config."""
import json
import pytest

from services.lorawan.tests.browser_auth import prepare_browser_auth, private_config_token


def test_browser_auth_requires_explicit_integration_before_reading_config(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.delenv('SENSOR_INTEGRATION',raising=False)
    monkeypatch.setattr('services.lorawan.tests.browser_auth.request',lambda *a,**k:pytest.fail('unexpected network'))
    with pytest.raises(ValueError,match='explicit disposable simulation'):
        prepare_browser_auth()
    assert list(tmp_path.iterdir())==[]


def test_browser_auth_refuses_production_config_before_network_or_account_creation(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('SENSOR_INTEGRATION','1')
    monkeypatch.setattr('services.lorawan.tests.browser_auth.request',lambda *a,**k:pytest.fail('unexpected network'))
    root=tmp_path/'.superpowers/lorawan-private';root.mkdir(parents=True)
    path=root/'ingest.json'
    path.write_text(json.dumps(dict(environment='production',mqtt_host='localhost',mqtt_port=1883,
        mqtt_username='fixture',mqtt_password='fixture',database_dsn='sqlite:fixture')));path.chmod(0o600)
    with pytest.raises(ValueError,match='explicit disposable simulation'):
        prepare_browser_auth()
    assert not (root/'browser-auth.json').exists()


def test_browser_token_rejects_nonprivate_permissions(tmp_path):
    path=tmp_path/'browser-auth.json';path.write_text('{"token":"fixture"}');path.chmod(0o644)
    with pytest.raises(ValueError,match='private fixture token permissions'):
        private_config_token(path)
