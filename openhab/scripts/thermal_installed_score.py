#!/usr/bin/env python3
"""Check private scoring settings or explicitly collect one mature horizon."""
import argparse
import json
import os
from pathlib import Path
from thermal_model.capture_guard import SharedScoreLock



def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--contract-version',type=int,choices=(1,2,3,4),default=2,
        help='4 scores compressed original-query publications; 3 scores original-query base/calibrated publications; 2 scores raw calibrated publications; 1 scores legacy base origins')
    intent=parser.add_mutually_exclusive_group()
    intent.add_argument('--collect',action='store_true')
    intent.add_argument('--batch',action='store_true')
    intent.add_argument('--update-release-index',action='store_true')
    parser.add_argument('--release-reference',type=Path)
    parser.add_argument('--additional-pairs',type=Path)
    parser.add_argument('--queue',type=Path)
    parser.add_argument('--origin',type=Path)
    parser.add_argument('--shared-lock',type=Path)
    parser.add_argument('--horizon',type=int,choices=(1,6,12,24))
    args=parser.parse_args(argv)
    if args.collect and (args.origin is None or args.horizon is None or args.shared_lock is None or args.queue is not None):parser.error('explicit original publication, mature horizon and shared lock required')
    if args.batch and (args.queue is None or args.shared_lock is None or args.origin is not None or args.horizon is not None):parser.error('explicit queue and shared lock required for batch')
    if args.update_release_index and (args.contract_version!=4 or args.release_reference is None or (args.additional_pairs is None)==(args.queue is None) or args.shared_lock is None or any(value is not None for value in (args.origin,args.horizon))):parser.error('index update requires profile4, release reference, exactly one original-pairs index or declared queue, and shared lock')
    if not args.update_release_index and (args.release_reference is not None or args.additional_pairs is not None):parser.error('release index paths require explicit index-update intent')
    if not (args.collect or args.batch or args.update_release_index) and any(value is not None for value in (args.origin,args.horizon,args.shared_lock,args.queue)):parser.error('source reads require explicit collection intent')
    try:
        if args.collect or args.batch or args.update_release_index:
            from thermal_installed_intel import _resource_preflight
            _resource_preflight()
            if args.update_release_index:
                from thermal_model.capture_guard import verify_host_headroom
                verify_host_headroom()
            os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        from thermal_model.installed_shade_score_inputs import load_score_settings,load_raw_score_settings,load_source_score_settings,load_compressed_source_score_settings,ScoreReader
        loader={1:load_score_settings,2:load_raw_score_settings,3:load_source_score_settings,4:load_compressed_source_score_settings}[args.contract_version]
        settings=loader(args.config)
        if not (args.collect or args.batch or args.update_release_index):
            print(json.dumps(dict(status='configuration_verified',collection_executed=False,release_authorized=False)));return 0
        from thermal_model.installed_shade_score_collection import collect_published_score,collect_raw_published_score,collect_source_published_score
        from thermal_model.installed_shade_score_jobs import collect_compressed_original_score
        collect={1:collect_published_score,2:collect_raw_published_score,3:collect_source_published_score,4:collect_compressed_original_score}[args.contract_version]
        with SharedScoreLock(args.shared_lock) as held:
            if args.update_release_index:
                from thermal_model.installed_shade_release_index import append_compressed_release_sources,append_compressed_completed_queue
                def index_guard():
                    held.verify()
                    if loader(args.config)!=settings:raise ValueError('original scorer settings changed')
                    held.verify()
                if args.queue is not None:
                    result=append_compressed_completed_queue(reference_path=args.release_reference,queue_path=args.queue,output_directory=settings['output_directory'],guard=index_guard)
                else:
                    result=append_compressed_release_sources(reference_path=args.release_reference,additional_pairs_path=args.additional_pairs,guard=index_guard)
            else:
                backend=ScoreReader(settings,shared_lock_guard=held.verify)
            if args.batch:
                from thermal_model.installed_shade_score_jobs import collect_queued_score,collect_raw_queued_score,collect_source_queued_score,collect_compressed_queued_score
                queued={1:collect_queued_score,2:collect_raw_queued_score,3:collect_source_queued_score,4:collect_compressed_queued_score}[args.contract_version]
                result=queued(queue_path=args.queue,output_directory=settings['output_directory'],backend=backend)
            elif args.collect:
                result=collect(origin_path=args.origin,horizon_hours=args.horizon,
                    output_directory=settings['output_directory'],backend=backend)
            held.verify()
        print(json.dumps(result,sort_keys=True));return 0 if result['status'] in ('scored','pending','busy','queue_complete','completion_verified','index_updated','index_unchanged','index_pending') else 1
    except BlockingIOError:
        print(json.dumps(dict(status='busy',collection_executed=False,release_authorized=False)));return 75
    except Exception:
        # Never emit credential/config/transport exception bytes or tracebacks.
        print(json.dumps(dict(status='withheld',collection_executed=False,release_authorized=False)));return 1


if __name__=='__main__':raise SystemExit(main())
