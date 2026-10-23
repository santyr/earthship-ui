#!/usr/bin/env python3
"""Bounded WeatherNext access proof or private shadow archive collection."""
import argparse,json,os,pathlib,resource,sys
from datetime import datetime,timezone
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
    from weather_learning.capabilities import PROFILES,enabled_profiles
    parser.add_argument('--capability-profile',action='append',default=[],choices=[name for name,p in PROFILES.items() if p.optional and p.remote_allowed],
        help='explicit optional statistics profile; shares all existing collection budgets')
    args=parser.parse_args(argv)
    if args.capability_profile and (not args.collect or args.hours not in (48,360)):
        parser.error('optional capability profiles require --collect with an existing 48 or 360 hour horizon')
    reader=None;archive=None;started=monotonic()
    try:
        if not 1<=args.hours<=360:raise ValueError('forecast horizon outside bound')
        enabled_profiles(tuple(args.capability_profile))
        # Reuse the established private OpenHAB token, but never its site fallback.
        from weather_learning.openhab import oh_get,I18N_CONFIG_PATH
        site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH))
        policy=AccessPolicy(backend='earthengine',noncommercial_verified=True)
        reader=EarthEngineReader(policy=policy,site=site,credential_path=args.credential)
        archive=Archive(pathlib.Path(args.archive))
        result=collect_once(reader,archive,probe=not args.collect,horizon=args.hours,include_interim=args.collect and args.hours==360,
            optional_profiles=tuple(args.capability_profile))
        result.update(bytes_received=reader.transport.bytes_received,requests=reader.transport.requests,
            noncommercial_verified=reader.transport.noncommercial_verified,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if args.collect:
            from weather_learning.operations import persist_ingestion
            persist_ingestion(archive,result,profiles=tuple(args.capability_profile),now=datetime.now(timezone.utc))
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
        if args.collect and archive is None:
            try:archive=Archive.open_readonly(pathlib.Path(args.archive),allow_missing=True)
            except (OSError,ValueError):pass
        if args.collect and archive is not None:
            from weather_learning.operations import persist_ingestion
            persist_ingestion(archive,result,profiles=tuple(args.capability_profile),now=datetime.now(timezone.utc))
        print(json.dumps(result));return 1
    finally:
        if reader is not None:reader.transport.close()

if __name__=='__main__':sys.exit(main())
