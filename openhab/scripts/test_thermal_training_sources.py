"""Canonical sample/native-receipt archives, using real private file transactions."""
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest

from thermal_model.forcing_capture import _canonical
from thermal_model.dataset import _observe_latent_mass,dataset_manifest
from test_thermal_pipeline import training_samples
from test_thermal_temperature_history import receipt
from thermal_model.temperature_history import QualifiedTemperatureHistory,STREAMS
from thermal_model.schema import THERMAL_ITEMS


def module():
    from thermal_model import training_sources
    return training_sources


def inputs():
    samples=training_samples();start=samples[0].at;end=samples[-1].at+timedelta(minutes=5)
    raw={row.at:row for row in samples}
    def grid(stream,targets,assessed):
        role=next(role for role,value in STREAMS.items() if value[0]==stream)
        field={'air':'air_f','mass':'mass_f','outdoor':'outdoor_f'}[role]
        return [(at,receipt(at,getattr(raw[at],field))) for at in targets]
    reader=QualifiedTemperatureHistory(lambda *_:[],grid,cutover=start,assessed_at=end,retain_raw=True)
    for role in STREAMS:reader(THERMAL_ITEMS[role],start,end)
    samples=_observe_latent_mass(samples);manifest=dataset_manifest(samples,[],[])
    manifest['temperature_evidence']=reader.evidence_manifest()
    return samples,reader,SimpleNamespace(data_manifest=manifest)


def test_source_archive_reproduces_canonical_samples_and_original_grid_hashes(tmp_path):
    source=module();samples,reader,artifact=inputs();tmp_path.chmod(0o700)
    record=source.build_training_sources(samples,reader)
    assert record['schema']=='earthship-thermal-training-sources/v1'
    assert record['samples'][0]['north_wall_f']==70
    assert record['temperature_grids']['air'][0][1]['temperatureF']==72
    path=source.write_training_sources(tmp_path,record,artifact)
    assert source.read_training_sources(path,artifact)==record
    assert path.stat().st_mode & 0o777==0o600
    assert source.write_training_sources(tmp_path,record,artifact)==path


@pytest.mark.parametrize('damage',['sample','receipt','extra','missing_role'])
def test_unbound_raw_source_edits_cannot_overwrite_an_original_snapshot(tmp_path,damage):
    source=module();samples,reader,artifact=inputs();tmp_path.chmod(0o700)
    record=source.build_training_sources(samples,reader);path=source.write_training_sources(tmp_path,record,artifact)
    if damage=='sample':record['samples'][0]['air_f']=99
    elif damage=='receipt':record['temperature_grids']['air'][0][1]['temperatureF']=99
    elif damage=='extra':record['qualified']=True
    elif damage=='missing_role':record['temperature_grids'].pop('mass')
    with pytest.raises(ValueError):source.write_training_sources(tmp_path,record,artifact)
    assert source.read_training_sources(path,artifact)['samples'][0]['air_f']==72


def test_source_snapshot_cannot_be_reconstructed_from_summary_only():
    source=module();samples,reader,artifact=inputs()
    with pytest.raises(ValueError):source.build_training_sources(samples,lambda *_:[])


def test_retained_training_snapshot_passes_the_actual_combined_source_verifier():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    from thermal_graduation_decision import verify_training_sources
    source=module();samples,reader,artifact=inputs()
    artifact.trained_from=artifact.data_manifest['start'];artifact.trained_through=artifact.data_manifest['end']
    record=source.build_training_sources(samples,reader)
    epochs={role:record['temperature_grids'][role][0][1]['streamEpoch'] for role in STREAMS}
    assessed=verify_training_sources(record,artifact,epochs)
    assert assessed['sample_count']==4
    assert assessed['training_inputs_sha256']==artifact.data_manifest['canonical_rows_sha256']
