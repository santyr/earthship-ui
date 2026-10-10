"""Prior-regularized provisional learning; no calibration or graduation claim."""
import math
import time
import numpy as np
from scipy.optimize import Bounds,minimize
from .installed_shade_dynamics import InstalledShadeDynamics,LOWER,UPPER
from .installed_shade_fit import _prepare_batches,_objective,_constraints,_check_deadline,HORIZONS
from .installed_shade_inputs import build_development_inputs,select_development_endpoints
from .offline_training import require_fitting_optin
from .graduation_policy import _utc

# Explicit conservative physical prior, not a measurement or learned model.
DEFAULT_PRIOR=(.002,.02,.0005,.001,.005,0.,.01,.001,.0002,.0004)
REGULARIZATION_STRENGTH=1.0


def fit_points(points,*,initial=DEFAULT_PRIOR,deadline):
    require_fitting_optin();_check_deadline(deadline)
    original=InstalledShadeDynamics(initial);batches=_prepare_batches(points)
    lower=np.asarray(LOWER);spans=np.asarray(UPPER)-lower
    x0=(np.asarray(initial)-lower)/spans
    initial_loss,_,sensitivity=_objective(initial,batches,deadline=deadline)
    scaled=sensitivity*spans
    rank=int(np.linalg.matrix_rank(scaled))
    singular=np.linalg.svd(scaled,compute_uv=False)
    condition=float(singular[0]/singular[-1]) if rank==10 else None
    def objective(x):
        _check_deadline(deadline)
        value,gradient,_=_objective(lower+spans*x,batches,deadline=deadline)
        distance=x-x0
        return value+REGULARIZATION_STRENGTH*float(distance@distance),gradient*spans+2*REGULARIZATION_STRENGTH*distance
    result=minimize(objective,x0,jac=True,method='SLSQP',bounds=Bounds(np.zeros(10),np.ones(10)),
        constraints=_constraints(lower,spans),options={'maxiter':300,'ftol':1e-9})
    _check_deadline(deadline)
    if result.success is not True and result.success!=np.bool_(True):raise ValueError('provisional optimizer failed')
    coefficients=tuple(float(x) for x in lower+spans*result.x)
    model=InstalledShadeDynamics(coefficients)
    final_loss,_,_=_objective(coefficients,batches,deadline=deadline)
    if not math.isfinite(final_loss) or final_loss>initial_loss+1e-6:raise ValueError('provisional fit worsened development loss')
    for point in points:
        _check_deadline(deadline)
        model.rollout(origin_at=point.origin.at,air_f=point.origin.air_f,mass_f=point.origin.mass_f,forcings=point.forcings)
    return dict(mode='provisional',confidence='low',coefficients=list(model.coefficients),initial_coefficients=list(original.coefficients),
        initial_objective=float(initial_loss),final_objective=float(final_loss),regularization_strength=REGULARIZATION_STRENGTH,
        conditioning_rank=rank,normalized_condition_number=condition,iterations=int(result.nit),endpoint_count=len(points),
        fit_executed=True,stability_assessed=False,graduated=False,prediction_intervals=None,automatic_actuation=False)


def fit_inputs(record,*,expected_snapshot_sha256,sensor_epochs,assessed_at,training_start,training_end,
               initial=DEFAULT_PRIOR,timeout_seconds=60):
    require_fitting_optin()
    if type(timeout_seconds) not in (int,float) or not math.isfinite(timeout_seconds) or not 0<timeout_seconds<=85:raise ValueError('bounded provisional fit deadline required')
    deadline=time.monotonic()+timeout_seconds
    data=build_development_inputs(record,expected_snapshot_sha256=expected_snapshot_sha256,sensor_epochs=sensor_epochs,assessed_at=assessed_at)
    start,end=map(_utc,(training_start,training_end))
    if not data.start<=start<end<=data.end:raise ValueError('development-only training interval required')
    points=[];support={}
    for horizon in HORIZONS:
        selected=select_development_endpoints(data,horizon_hours=horizon,start=start,end=end)
        points.extend(selected);support[str(horizon)]=len(selected)
    if not points:raise ValueError('no supported real development endpoints')
    result=fit_points(tuple(points),initial=initial,deadline=deadline)
    from .actions import DENVER
    result.update(source_snapshot_sha256=data.source_snapshot_sha256,sensor_epochs=dict(data.sensor_epochs),
        training_start=start.isoformat(),training_end=end.isoformat(),horizon_support=support,
        independent_origin_dates=len({point.origin.at.astimezone(DENVER).date() for point in points}))
    return result
