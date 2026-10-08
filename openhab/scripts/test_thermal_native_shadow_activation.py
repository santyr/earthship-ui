"""Explicit native current-input selection never promotes a legacy model."""
import pytest
import thermal_intel
import thermal_temperature_runtime as runtime
from test_thermal_sensor_epoch_origins import native_grid,NOW,EPOCHS


def test_shadow_cli_explicitly_selects_native_receipts():
    args=thermal_intel._build_parser().parse_args(['shadow','--receipt-version','2'])
    assert args.receipt_version==2 and args.publish is False
    assert thermal_intel._build_parser().parse_args(['shadow']).receipt_version==1


def test_legacy_shadow_caller_can_explicitly_select_native_current_inputs(monkeypatch):
    monkeypatch.setattr(runtime,'_configured_sensor_epochs',lambda _:EPOCHS)
    def grid(env,*,budget,sensor_epochs=None):
        assert budget==90 and sensor_epochs==EPOCHS
        return native_grid()
    monkeypatch.setattr(runtime,'_configured_grid_reader',grid)
    proofs=[]
    selected=runtime.configured_shadow_temperatures(NOW,environ={'THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE':'1','THERMAL_TEMP_SHADOW_RECEIPT_VERSION':'2'},origin_observer=proofs.append)
    assert all(len(value['history'])==287 for value in selected.values())
    assert proofs[0]['schema']=='earthship-thermal-origin-temperatures/v2'
    assert all(row['identity']['sensor_epoch']==EPOCHS[role] for role,row in proofs[0]['roles'].items())


@pytest.mark.parametrize('version',['2','bad'])
def test_explicit_native_or_invalid_shadow_activation_without_optin_refuses(version):
    with pytest.raises(ValueError):runtime.configured_shadow_temperatures(NOW,environ={'THERMAL_TEMP_SHADOW_RECEIPT_VERSION':version})
