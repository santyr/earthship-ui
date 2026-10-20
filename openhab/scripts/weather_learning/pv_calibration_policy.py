"""Shared, evidence-based scope for provisional directional PV correction.

The retained horizon assessment supports the fixed method through 336 hours,
except near the declared skyline. It does not certify physical irradiance,
terrain geometry, array losses or unconstrained production.
"""
from datetime import timedelta
from .contracts import finite,identity,instant
from .pv_directional_calibration import validate_model,sector

POLICY=dict(schema='earthship-pv-calibration-policy/v1',rule='directional_gain_above_declared_skyline_v1',
    maximum_lead_hours=336,minimum_horizon_margin_degrees=5.,
    assessment_sha256='48e5d5047db6f67f1d7c5047e3b0818846d19395732ba343c4e51d7866f56ec5',
    physical_calibration_qualified=False,automatic_actuation=False)
POLICY_SHA256=identity(POLICY)


def project_power(model,watts,*,azimuth_degrees,elevation_degrees,horizon_elevation_degrees,origin,target):
    model=validate_model(model)
    if instant(model['trained_at'])>origin:raise ValueError('directional PV calibration not available at origin')
    return _calculate(model,watts,azimuth_degrees=azimuth_degrees,elevation_degrees=elevation_degrees,
        horizon_elevation_degrees=horizon_elevation_degrees,lead_hours=(target-origin).total_seconds()/3600)


def _calculate(model,watts,*,azimuth_degrees,elevation_degrees,horizon_elevation_degrees,lead_hours):
    """Numerical kernel; retrospective assessments retain their own clock proof."""
    if not finite(lead_hours):raise ValueError('finite PV lead required')
    if not finite(watts) or not 0<=watts<=20000:raise ValueError('bounded physical PV baseline required')
    if not all(finite(v) and -90<=v<=90 for v in (elevation_degrees,horizon_elevation_degrees)):
        raise ValueError('bounded original PV geometry required')
    gain=model['sectors'][sector(azimuth_degrees)]
    applied=(0<lead_hours<=POLICY['maximum_lead_hours'] and
        elevation_degrees-horizon_elevation_degrees>POLICY['minimum_horizon_margin_degrees'] and gain['supported'])
    return (watts*gain['gain'] if applied else watts),bool(applied)
