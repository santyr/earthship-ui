"""Human-only receding-horizon shade comparisons using frozen thermal inputs.

Solar incidence is a timing screen, not a replacement for the learned irradiance
feature. A nominal vertical south aperture is explicit until surveyed geometry
exists. No fictitious causal calibration or night insulation coefficient.
"""
from dataclasses import replace
from datetime import timedelta
from math import cos, sin, radians
from zoneinfo import ZoneInfo
from ..codec import canonical
from ..control_contracts import instant
from ..thermal_model import PreparedProjection, _geometry, NATIVE_SCHEMAS
from .contracts import number


def solar_access(elevation, azimuth, facing=180., tilt_from_horizontal=90.):
    """Direct-beam incidence cosine onto glazing, not heat gain in watts."""
    number(elevation, -90, 90); number(azimuth, 0, 360); number(facing, 0, 360); number(tilt_from_horizontal, 0, 90)
    return 0. if elevation <= 0 else max(0., sin(radians(elevation))*cos(radians(tilt_from_horizontal))
        + cos(radians(elevation))*sin(radians(tilt_from_horizontal))*cos(radians(azimuth-facing)))


def discomfort(states, low, high):
    # Five-minute air exposure includes delayed heat release from latent mass.
    return sum(max(0., low-air, air-high) for air, _mass in states)/12.


def choose_plan(baseline, candidates, low, high):
    """Require a material forecast improvement; stable ties prefer waiting."""
    baseline_cost = discomfort(baseline, low, high)
    ranked = sorted(candidates, key=lambda c: (discomfort(c['states'], low, high), -c['start_hour']))
    if not ranked: return None
    best = ranked[0]
    gain = baseline_cost-discomfort(best['states'], low, high)
    delta = max(abs(a[0]-b[0]) for a,b in zip(baseline,best['states']))
    return best if gain >= .1 and delta >= .2 else None


def forecast_advice(context, *, snapshot, now, low, high, timezone_name, glazing=None):
    value = PreparedProjection(canonical(context['prepared'])).to_dict()
    issue = instant(value['issue'])
    if value['schema'] not in NATIVE_SCHEMAS or value['model_rule'] != 'earthship-native-irradiance-shade-dynamics/v4':
        raise ValueError('irradiance-based four-regime model required')
    if not issue <= now < issue+timedelta(seconds=120):
        raise ValueError('fresh original thermal issue required')
    if context['source_ref'] != value['original_capture_sha256'] or not context.get('training_end') or instant(context['training_end']) >= issue:
        raise ValueError('original predecision model context required')
    from ..advice import _reading
    observed = _reading(snapshot, 'thermal', 'air_temperature', now)
    # Mass remains the original latent observer, not a measured equivalent.
    if observed is None or abs(observed['value']-value['initial']['air']) > 1.:
        raise ValueError('current indoor source differs from forecast')
    geometry = _geometry(value)
    facing, tilt = 180., 90.
    if glazing is not None:
        from .contracts import closed
        closed(glazing, {'schema','azimuth_degrees','tilt_from_horizontal_degrees','basis'})
        if glazing['schema'] != 'earthship-advice-glazing/v1' or glazing['basis'] != 'operator_report':
            raise ValueError('explicit operator glazing geometry required')
        facing = number(glazing['azimuth_degrees'],0,360)
        tilt = number(glazing['tilt_from_horizontal_degrees'],0,90)
    from thermal_model.installed_shade_dynamics import InstalledShadeForcing
    from native_irradiance_shade import NativeIrradianceShadeDynamics
    from ..thermal_weather_conditioning import apply_conditioning
    forcing = tuple(InstalledShadeForcing(**{**r,'at':instant(r['at'])}) for r in value['forcings'])
    if value['schema'] == NATIVE_SCHEMAS[1]:
        forcing = apply_conditioning(forcing,value['weather_conditioning'],issue=issue,available=instant(value['inputs_available_at']),initial_outdoor_f=value['initial']['outdoor'])
    if len(forcing) != 288: raise ValueError('complete 24-hour weather grid required')
    model = NativeIrradianceShadeDynamics(tuple(value['coefficients']),geometry=geometry,expected_series_sha256=value['geometry_series_sha256'])
    def rollout(rows):
        return model.rollout(origin_at=issue,air_f=value['initial']['air'],mass_f=value['initial']['mass'],forcings=rows).states
    baseline = rollout(forcing)
    angles = {instant(r['at']):r for cache in geometry.to_dict()['caches'] for r in cache['positions']}
    # Compare two-hour actions at now, +1h, +2h, +4h and +6h, then revert to
    # the original journal assumption. All share weather, model and mass state.
    candidates=[]
    for start_hour in (0,1,2,4,6):
        start=issue+timedelta(hours=start_hour);end=start+timedelta(hours=2)
        window=[r for r in forcing if start<r.at<=end]
        access=sum(r.radiation_wm2*solar_access(angles[r.at]['elevation_degrees'],angles[r.at]['azimuth_degrees'],facing,tilt) for r in window)/len(window)
        if access < 20.: continue
        for closed in (0.,1.):
            rows=tuple(replace(r,indoor_shade_closed=closed) if start<r.at<=end else r for r in forcing)
            if rows == forcing: continue
            candidates.append(dict(start_hour=start_hour,closed=closed,states=rollout(rows),start=start,end=end))
    best=choose_plan(baseline,candidates,low,high)
    stamp=lambda at:at.astimezone(ZoneInfo(timezone_name)).strftime('%a %-I:%M %p')
    hot=next((r.at for r,s in zip(forcing,baseline) if s[0]>high),None)
    cold=next((r.at for r,s in zip(forcing,baseline) if s[0]<low),None)
    bounds=(min(s[0] for s in baseline),max(s[0] for s in baseline))
    basis=f'Forecast indoors {bounds[0]:.1f}–{bounds[1]:.1f}°F; weather, irradiance and stored heat included. '
    aperture = 'Nominal south vertical glazing' if glazing is None else f'Glazing azimuth {facing:g}°, tilt {tilt:g}° from horizontal'
    limitations=aperture+'; overhang and night insulation uncalibrated. Scenario, not measured benefit.'
    if best:
        when='now' if best['start_hour']==0 else f'at {stamp(best["start"])}'
        action=f'{"Close" if best["closed"] else "Open"} shades {when} to {"limit solar heating" if best["closed"] else "capture solar heat"}'
        risk=hot if best['closed'] else cold
        reason=basis+(f'Anticipate {"heat" if best["closed"] else "cooling"} by {stamp(risk)}. ' if risk else '')+f'Compare a two-hour setting through {stamp(best["end"])}; then reassess. '+limitations
    else:
        action='Keep shades steady; no forecast-supported change'
        reason=basis+'No tested solar-access window materially improves predicted comfort. '+limitations
    # Ventilation uses the predicted path, not a current-temperature trigger.
    near=any(s[0]>high for r,s in zip(forcing,baseline) if r.at<=issue+timedelta(hours=2))
    cool_air=all(r.outdoor_f<=value['initial']['air']-2 for r in forcing[:12])
    vent='Keep ventilation steady; reassess the forecast'
    if near and cool_air and (best is None or best['closed']):
        rows=tuple(replace(r,vent_open=1.) if r.at<=issue+timedelta(minutes=15) else r for r in forcing)
        candidate=dict(start_hour=0,states=rollout(rows))
        if choose_plan(baseline,[candidate],low,high):
            vent='Consider brief ventilation before forecast heat builds'
    return dict(action=action,reason=reason,ventilation=vent,until=issue+timedelta(seconds=120),source=value['prepared_sha256'])
