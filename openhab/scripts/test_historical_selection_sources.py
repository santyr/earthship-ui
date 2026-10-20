"""New measured-target fits must retain the added numerical source dependency."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import pytest
from weather_learning.contracts import canonical,identity,instant


@pytest.mark.parametrize('kind',['outdoor_temperature_c','wind_m_s'])
def test_selected_new_weighted_model_requires_exact_weights_source(tmp_path,kind):
    from weather_learning.historical_serving import load_selection
    scripts=Path(__file__).parent/'weather_learning'
    epoch='00000000-0000-4000-8000-000000000001' if kind=='outdoor_temperature_c' else None
    if kind=='outdoor_temperature_c':
        from test_weather_site_calibration import rows
        from weather_learning.site_calibration import fit_residual,evaluate
        data=rows(12);start=instant(data[0]['origin']).replace(hour=0)
        for row in data:
            row['features'].update(hour_sin=0.,hour_cos=1.,season_sin=0.,season_cos=1.,origin_bias_decay_c=2.)
            row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
        now=start+timedelta(days=20);cutoff=start+timedelta(days=8);end=start+timedelta(days=12)
        training=fit_residual(data,kind=kind,cutoff=cutoff,trained_at=now,correction_limit=6.)
        report=evaluate(training,data,holdout_start=cutoff,holdout_end=end)
        model=fit_residual(data,kind=kind,cutoff=end,trained_at=now,correction_limit=6.)
        names=('site_calibration.py','historical_pairs.py','contracts.py','weights.py')
    else:
        from test_weather_site_response import rows
        from weather_learning.weather_response import fit_gain,evaluate_gain
        data=rows();start=instant(data[0]['origin']).replace(hour=0)
        now=start+timedelta(days=20);cutoff=start+timedelta(days=7);end=start+timedelta(days=12)
        training=fit_gain(data,kind=kind,cutoff=cutoff,trained_at=now)
        report=evaluate_gain(training,data,start=cutoff,end=end)
        model=fit_gain(data,kind=kind,cutoff=end,trained_at=now)
        assert report['selected'] is True
        names=('weather_response.py','contracts.py','weights.py')
    runtime={'openhab/scripts/weather_learning/'+name:sha256((scripts/name).read_bytes()).hexdigest() for name in names}
    original=dict(final_models={kind:model['model_sha256']},reports={kind:report},runtime_manifest=runtime)
    def write(omit=False):
        body=dict(original,runtime_manifest={k:v for k,v in runtime.items() if not omit or not k.endswith('/weights.py')})
        body['receipt_sha256']=identity(body);raw=canonical(body);experiment=tmp_path/'experiment.json';experiment.write_bytes(raw);experiment.chmod(0o600)
        model_raw=canonical(model);model_path=tmp_path/'model.json';model_path.write_bytes(model_raw);model_path.chmod(0o600)
        selection=dict(schema='earthship-historical-weather-selection/v1',kind=kind,experiment_path=str(experiment),
            experiment_file_sha256=sha256(raw).hexdigest(),experiment_receipt_sha256=body['receipt_sha256'],model_path=str(model_path),
            model_file_sha256=sha256(model_raw).hexdigest(),model_sha256=model['model_sha256'],target_dates=10,sensor_epoch=epoch,
            available_at=now.isoformat(),automatic_actuation=False)
        selection['selection_sha256']=identity(selection);path=tmp_path/'selected.json';path.write_bytes(canonical(selection));path.chmod(0o600)
        return path
    assert load_selection(write(),kind=kind,now=now,sensor_epoch=epoch)[0]==model
    with pytest.raises(ValueError,match='runtime'):
        load_selection(write(omit=True),kind=kind,now=now,sensor_epoch=epoch)
