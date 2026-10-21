"""Generate/check synthetic public v2 fixtures through the actual offline producer.

Run from the repo with PYTHONPATH=.:openhab/scripts:openhab/scripts/weather_learning/tests.
No household sources, credentials, sockets, selectors or live publication.
"""
import argparse,json
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import capability_fixtures as fixture
import test_moisture_context as moisture
from weather_learning.archive import Archive
from weather_learning.worker import collect_once
from weather_learning.atmospheric_publish import build_atmospheric_report


def build():
    fixture.T=datetime(2026,10,21,16,tzinfo=timezone.utc)
    with TemporaryDirectory(prefix='earthship-atmospheric-fixture-') as directory:
        reader,clock=fixture.reader();archive=Archive(Path(directory)/'archive')
        collect_once(reader,archive,probe=False,horizon=360,include_interim=True,clock=lambda:clock[0],free_bytes=10**9,optional_profiles=('atmosphere-v1',))
        moisture.DECISION=clock[0]
        variants=dict(outdoor=build_atmospheric_report(archive,decision=clock[0],site=fixture.SITE,horizons=(24,)),
            qualified=build_atmospheric_report(archive,decision=clock[0],site=fixture.SITE,horizons=(24,),indoor=moisture.indoor(),zone='room'))
        raw=(json.dumps(variants,sort_keys=True,separators=(',',':'))+'\n').encode()
        assert all(word.encode() not in raw for word in ('latitude','longitude','registry_raw','/home/','device_id'))
        return raw


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
    raw=build();target=Path(__file__).with_name('weather-atmosphere.json')
    if args.write:target.write_bytes(raw)
    else:
        if target.read_bytes()!=raw:raise ValueError('retained public fixture differs from actual Python v2 producer')
    print(json.dumps(dict(status='written' if args.write else 'verified',bytes=len(raw),sha256=sha256(raw).hexdigest(),variants=['outdoor','qualified'])))
