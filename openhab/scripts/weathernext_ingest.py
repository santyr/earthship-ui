#!/usr/bin/env python3
"""Bounded WeatherNext access proof or private shadow archive collection."""
import argparse,json,os,pathlib,resource,sys
from time import monotonic
from weather_learning.archive import Archive
from weather_learning.config import AccessPolicy,Site
from weather_learning.transport import AccessRefused
from weather_learning.weathernext_ee import EarthEngineReader
from weather_learning.worker import collect_once

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group();modes.add_argument('--probe',action='store_true');modes.add_argument('--collect',action='store_true')
    parser.add_argument('--credential',default='/home/sat/.config/earthship-weather/weathernext-reader.json')
    parser.add_argument('--archive',required=True)
    parser.add_argument('--hours',type=int,default=360)
    args=parser.parse_args(argv)
    reader=None;started=monotonic()
    try:
        if not 1<=args.hours<=360:raise ValueError('forecast horizon outside bound')
        # Reuse the established private OpenHAB token, but never its site fallback.
        from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
        site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH))
        policy=AccessPolicy(backend='earthengine',noncommercial_verified=True)
        reader=EarthEngineReader(policy=policy,site=site,credential_path=args.credential)
        archive=Archive(pathlib.Path(args.archive))
        result=collect_once(reader,archive,probe=not args.collect,horizon=args.hours)
        result.update(bytes_received=reader.transport.bytes_received,requests=reader.transport.requests,
            noncommercial_verified=reader.transport.noncommercial_verified,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        print(json.dumps(result,allow_nan=False));return 0
    except Exception as exc:
        # No arbitrary exception text: upstream/library errors may contain inputs.
        result=dict(schema='earthship-weathernext-ingest-result/v1',status='UNAVAILABLE',
                    reason=str(exc) if isinstance(exc,AccessRefused) else type(exc).__name__,
                    production_writes=False,automatic_actuation=False,
                    elapsed_seconds=max(0.,monotonic()-started))
        if reader is not None:
            for name in ('requests','bytes_received'):
                number=getattr(reader.transport,name,None)
                if type(number) is int and number>=0:result[name]=number
        print(json.dumps(result));return 1
    finally:
        if reader is not None:reader.transport.close()

if __name__=='__main__':sys.exit(main())
