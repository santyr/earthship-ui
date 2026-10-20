from pathlib import Path
import pytest


def test_training_sources_are_original_bytes_and_changes_are_detected(tmp_path):
    from weather_learning.source_bundle import capture_sources, verify_sources, retain_sources
    root=tmp_path/'repo';script=root/'openhab/scripts/a.py';script.parent.mkdir(parents=True);script.write_bytes(b'x=1\n')
    (script.parent/'test_example.py').write_bytes(b'irrelevant test')
    sources=capture_sources(root)
    assert list(sources)==['openhab/scripts/a.py']
    output=tmp_path/'experiment';manifest=retain_sources(output,sources)
    assert (output/'sources/openhab/scripts/a.py').read_bytes()==b'x=1\n'
    assert len(manifest['openhab/scripts/a.py'])==64
    verify_sources(root,sources)
    script.write_bytes(b'x=2\n')
    with pytest.raises(ValueError,match='changed'):verify_sources(root,sources)
