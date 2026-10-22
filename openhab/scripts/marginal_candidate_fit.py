#!/usr/bin/env python3
"""Explicit actual-time candidate fitting; no model selector or timer installation."""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
from weather_source_files import _read
from weather_learning.contracts import digest
from weather_learning.probabilistic_retained import restore_population
from weather_learning.probabilistic_artifacts import fit_candidates,retain_candidates


def run(*,population,cohort_sha256,state_root,policy,apply=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    digest(cohort_sha256);root=Path(state_root)
    if type(apply) is not bool or not root.is_absolute() or root.resolve()!=root:raise ValueError('explicit private marginal candidate retention context required')
    rows,metadata=restore_population(Path(population),policy=policy,read=_read,guard=guard)
    selected=[p for p in rows if p.forecast.cohort_sha256==cohort_sha256]
    if not selected or len(selected)>10000 or any(p.forecast.availability_basis!='recorded_ingestion_availability' for p in selected):raise ValueError('one recorded-ingestion cohort required for actual candidates')
    guard();prepared=fit_candidates(selected,cutoff=clock(),policy=policy,population_sha256=metadata['population_sha256'],guard=guard);guard()
    body=prepared.bundle.to_dict();reference=None
    if apply:
        from weather_learning.shadow import ShadowStore
        reference=retain_candidates(ShadowStore(root),prepared,policy=policy)
    count=sum(model is not None for model in body['models'].values())
    return dict(status='unselected_candidates_retained' if apply and count else 'cold_unselected_bundle_retained' if apply else 'unretained_candidate_preparation',
        retained=apply,cohort_sha256=cohort_sha256,kind=body['kind'],training_support=body['support'],fitted_models=count,bundle_sha256=body['bundle_sha256'],artifact=reference,
        actual_completed_at=body['actual_completed_at'],selection_installed=False,local_coverage_qualified=False,automatic_actuation=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('population','state'):parser.add_argument('--'+key,required=True,type=Path)
    parser.add_argument('--cohort',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args(argv);started=time.monotonic()
    def guard():
        if time.monotonic()-started>120:raise TimeoutError('actual marginal candidate120second fitting deadline elapsed')
    try:
        root=Path(__file__).resolve().parents[2];policy=json.loads(_read(root/'docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json',65536,source=True))
        print(json.dumps(run(population=args.population,cohort_sha256=args.cohort,state_root=args.state,policy=policy,apply=args.apply,guard=guard)));return 0
    except Exception as error:
        print(json.dumps(dict(status='marginal_candidate_unavailable',reason=type(error).__name__,selection_installed=False,automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
