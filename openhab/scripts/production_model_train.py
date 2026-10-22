#!/usr/bin/env python3
"""Explicit current-time production fitting from retained original populations.

No selector, service, public forecast, cloud request or control is changed.
"""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
from weather_source_files import _read
from weather_learning.contracts import identity,digest
from weather_learning.probabilistic_retained import restore_population
from weather_learning.production_training import fit_production,retain_production

ROOT=Path(__file__).resolve().parents[2]


def run(*,population,cohort_sha256,state_root,family,policy,authorization,apply=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    digest(cohort_sha256);root=Path(state_root)
    if type(apply) is not bool or not root.is_absolute() or root.resolve()!=root:raise ValueError('explicit resolved private production training state required')
    rows,meta=restore_population(Path(population),policy=policy,read=_read,guard=guard)
    selected=[p for p in rows if p.forecast.cohort_sha256==cohort_sha256]
    if not selected or len(selected)>10000:raise ValueError('one bounded original production training cohort required')
    f=selected[0].forecast;partition=meta.get('partitions',{}).get(cohort_sha256);parent=cohort_sha256 if partition is None else partition['parent_cohort_sha256']
    context=meta['metadata']['quality_contexts'][parent]
    if context['kind']!=f.kind:raise ValueError('original production measurement context differs')
    from weather_learning.probabilistic import _lead
    ctx=dict(kind=f.kind,measurement_quality=context['measurement_quality'],grid_sha256=f.grid_sha256,availability_basis=f.availability_basis,lead_scope_hours=_lead(f.origin,f.target_end),timezone=f.timezone)
    guard();prepared=fit_production(selected,family=family,training_context=ctx,cutoff=clock(),policy=policy,population_sha256=meta['population_sha256'],authorization=authorization,authorization_sha256=identity(authorization),partition=partition,guard=guard)
    if prepared is None:return dict(status='insufficient_training_support',kind=f.kind,family=family,retained=False,production_installed=False,selection_installed=False,automatic_actuation=False)
    guard();body=prepared.bundle.to_dict();reference=None
    if apply:
        from weather_learning.shadow import ShadowStore
        from weather_learning.worker import collector_lock
        state=ShadowStore(root)
        with collector_lock(state.root/'production-fit.lock'):reference=retain_production(state,prepared,policy=policy)
    return dict(status='production_fit_retained' if apply else 'production_fit_prepared',kind=body['kind'],family=family,retained=apply,
        training_cohort_sha256=body['training_cohort_sha256'],serving_cohort_sha256=body['cohort_sha256'],training_availability_basis=body['training_availability_basis'],
        training_support=body['support'],bundle_sha256=body['bundle_sha256'],model_sha256=body['models'][family]['model_sha256'],actual_completed_at=body['actual_completed_at'],
        artifact=reference,production_installed=False,selection_installed=False,issued=False,local_coverage_qualified=False,probability_claim=False,parallel_shadow_required=False,automatic_actuation=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('population','state'):parser.add_argument('--'+key,required=True,type=Path)
    parser.add_argument('--cohort',required=True);parser.add_argument('--family',required=True,choices=('temperature_normal','nonnegative','empirical'));parser.add_argument('--apply',action='store_true');args=parser.parse_args(argv)
    began=time.monotonic()
    from household_cycle_pressure import PublicationHeadroom
    pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if time.monotonic()-began>120:raise TimeoutError('production training120second owner deadline elapsed')
    try:
        policy=json.loads(_read(ROOT/'docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json',65536,source=True))
        authorization=json.loads(_read(ROOT/'docs/operations/weathernext3-capabilities/deployment-policy.json',65536,source=True))
        print(json.dumps(run(population=args.population,cohort_sha256=args.cohort,state_root=args.state,family=args.family,policy=policy,authorization=authorization,apply=args.apply,guard=guard),allow_nan=False));return 0
    except Exception as error:
        print(json.dumps(dict(status='production_training_unavailable',failure_kind=type(error).__name__,production_installed=False,selection_installed=False,automatic_actuation=False)));return 1


if __name__=='__main__':raise SystemExit(main())
