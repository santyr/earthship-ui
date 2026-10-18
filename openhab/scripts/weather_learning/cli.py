"""Disabled-by-default operational entrypoints; Google access stays in ingestion."""
import argparse,json,sys
from datetime import datetime,timezone
from .archive import Archive
from .config import Site
from .shadow import ShadowStore,shadow_once,train_once


def _parser(description):
    parser=argparse.ArgumentParser(description=description)
    parser.add_argument('--archive',required=True)
    parser.add_argument('--state',required=True)
    parser.add_argument('--temperature-policy',required=True)
    parser.add_argument('--code-revision',required=True)
    return parser


def _context(args):
    from forecast_intel import oh_get,I18N_CONFIG_PATH
    from hourly_temperature_runtime import _native_outdoor_policy
    site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH))
    policy,epoch=_native_outdoor_policy(args.temperature_policy)
    return Archive(args.archive),ShadowStore(args.state),site,policy,epoch


def main_shadow(argv=None):
    parser=_parser('Retain a read-only WeatherNext shadow issue; publication is opt-in')
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--include-incumbent',action='store_true')
    parser.add_argument('--hours',type=int,default=336)
    args=parser.parse_args(argv)
    try:
        archive,state,site,policy,epoch=_context(args)
        incumbent=None
        if args.include_incumbent:
            from forecast_intel import oh_get
            from .incumbent import capture_incumbent
            try:
                raw=oh_get('/items/Forecast_10Day_JSON')['state']
                incumbent=capture_incumbent(raw,observed_at=datetime.now(timezone.utc),site=site)
            except Exception:pass  # Missing control never authorizes a substitute.
        put=None
        if args.publish:
            from forecast_intel import oh_put_state
            put=oh_put_state
        payload=shadow_once(archive,state,now=datetime.now(timezone.utc),site=site,sensor_epoch=epoch,
            code_revision=args.code_revision,horizon=args.hours,incumbent=incumbent,put_state=put)
        print(json.dumps(dict(status=payload['status'],generation=payload['generation'],published=args.publish,automatic_actuation=False)))
        return 0
    except Exception as exc:
        print(json.dumps(dict(status='UNAVAILABLE',reason=type(exc).__name__,automatic_actuation=False)))
        return 1


def main_train(argv=None):
    parser=_parser('Fit a separate shadow WeatherNext candidate; installation is opt-in')
    parser.add_argument('--temperature-db-config',required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--days',type=int,default=90)
    parser.add_argument('--algorithm',choices=('bias','residual'),default='bias')
    args=parser.parse_args(argv)
    try:
        archive,state,site,policy,epoch=_context(args)
        from hourly_temperature_runtime import read_db_config
        config=read_db_config(args.temperature_db_config)
        def read(targets,assessed_at):
            import psycopg2
            from weather_temperature_history import fetch_temperature_grid_v2
            groups={};result={}
            for at in targets:groups.setdefault(at.date(),[]).append(at)
            for group in groups.values():
                result.update(fetch_temperature_grid_v2(lambda:psycopg2.connect(**config,connect_timeout=3),
                    targets=group,assessed_at=assessed_at,stream='outdoor',policy=policy,sensor_epoch=epoch))
            return result
        result=train_once(archive,state,reader=read,site=site,sensor_epoch=epoch,cutoff=datetime.now(timezone.utc),
            code_revision=args.code_revision,apply=args.apply,days=args.days,algorithm=args.algorithm)
        print(json.dumps(result));return 0
    except Exception as exc:
        print(json.dumps(dict(status='UNAVAILABLE',reason=type(exc).__name__,automatic_actuation=False)))
        return 1
