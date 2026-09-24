"""Pure guards for streaming Bitcoin price JDBC prefix checks."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import pytest

spec = spec_from_file_location('bitcoin_history_digest',
    Path(__file__).with_name('bitcoin-price-history-digest.py'))
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_cutoff_requires_aware_nonfuture_time():
    assert module.parse_cutoff('2026-09-24T03:12:00Z').isoformat() == \
        '2026-09-24T03:12:00+00:00'
    with pytest.raises(ValueError, match='timezone'):
        module.parse_cutoff('2026-09-24T03:12:00')
    with pytest.raises(ValueError, match='future'):
        module.parse_cutoff('2099-01-01T00:00:00Z')


def test_digest_sink_streams_bytes_without_retaining_rows():
    sink = module.DigestSink()
    sink.write('one,two\n')
    sink.write(b'three,four\n')
    assert sink.bytes_written == len(b'one,two\nthree,four\n')
    assert sink.digest.hexdigest() == \
        '88e508133fcb483dc730f288987abe673d38ac03e43d730920f835d86acb12dd'
    assert not hasattr(sink, 'rows')
