"""Opt-in directional comparisons without invented operator or device state."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from .contracts import closed, number
from ..codec import identity
from ..control_contracts import instant

SCHEMA = 'earthship-provisional-advice-preferences/v1'
FIELDS = {'schema', 'enabled', 'comfort_min_f', 'comfort_max_f', 'timezone'}


def validate_preferences(value):
    closed(value, FIELDS)
    if value['schema'] != SCHEMA or type(value['enabled']) is not bool:
        raise ValueError('explicit provisional preference opt-in required')
    low = number(value['comfort_min_f'], 40, 95)
    high = number(value['comfort_max_f'], 45, 100)
    if not 1 <= high - low <= 30:
        raise ValueError('bounded ordered provisional comfort band required')
    ZoneInfo(value['timezone'])
    return dict(value)


def evaluate(report, snapshot, projections, state, now):
    from . import _reading, _domain, _compare
    preferences = validate_preferences(projections['provisional_preferences'])
    if not preferences['enabled']:
        return False
    low, high = preferences['comfort_min_f'], preferences['comfort_max_f']
    band = f'Provisional comfort band {low:g}–{high:g}°F.'
    report['policy_sha256'] = identity(preferences)
    report['timezone'] = preferences['timezone']
    report['domains']['energy'] = _domain('insufficient_evidence', 'approved_flexible_task_missing', ['approved_flexible_task'])
    air = _reading(snapshot, 'thermal', 'air_temperature', now)
    out = _reading(snapshot, 'weather', 'outdoor_temperature', now)

    def comparison(domain, action, reason, sources):
        deadline = min(instant(report['valid_until']), *(r['until'] for r in sources))
        result = _domain('conditional', 'provisional_comfort_comparison', comparison=[
            _compare('Leave unchanged', 'Compare with keeping existing settings and independent schedules.', deadline),
            _compare(action, f'{reason} {band}', deadline),
        ])
        result['valid_until'] = deadline.isoformat()
        report['domains'][domain] = result

    if air is None:
        for domain in ('shades', 'ventilation'):
            report['domains'][domain] = _domain('insufficient_evidence', 'provisional_temperature_unavailable', ['air_temperature'])
        return True

    # Current publishers always supply forecast context, including an explicit
    # unavailable marker. Legacy inputs retain their original replay behavior.
    if 'thermal_evaluation_context' in projections:
        from .anticipatory import forecast_advice
        try:
            forecast = forecast_advice(projections['thermal_evaluation_context'], snapshot=snapshot,
                now=now, low=low, high=high, timezone_name=preferences['timezone'], glazing=projections.get('passive_solar_geometry'))
        except (ValueError, TypeError, KeyError, OverflowError):
            for domain in ('shades', 'ventilation'):
                report['domains'][domain] = _domain('insufficient_evidence', 'provisional_forecast_unavailable', ['thermal_forecast'])
            return True
        sources = [air, {'until': forecast['until']}]
        recent_deadlines = [instant(row['stop_observed_at']) + timedelta(seconds=600)
            for row in state['shade_movements'] if 0 <= (now-instant(row['stop_observed_at'])).total_seconds() < 600]
        action, reason = forecast['action'], forecast['reason']
        if recent_deadlines:
            action, reason = 'Keep the recent shade setting', 'Allow the recent setting time to settle; reassess the forecast afterwards.'
            sources.append({'until':min(recent_deadlines)})
        comparison('shades', action, reason, sources)
        adverse = [row for row in state['checks'].values()
            if instant(row['observed_at']) <= now < instant(row['valid_until']) and not row['clear']]
        vent = 'Avoid ventilation for now' if adverse else forecast['ventilation']
        if out is None:
            report['domains']['ventilation'] = _domain('insufficient_evidence', 'provisional_temperature_unavailable', ['outdoor_temperature'])
        else:
            vent_sources = [*sources, out]
            for row in state['checks'].values():
                if instant(row['observed_at']) <= now < instant(row['valid_until']):
                    vent_sources.append({'until':instant(row['valid_until'])})
            comparison('ventilation', vent, 'Forecast-led comparison; check wind, rain, smoke and security before opening. Reassess after at most 15 minutes.', vent_sources)
        return True

    if out is None:
        report['domains']['ventilation'] = _domain('insufficient_evidence', 'provisional_temperature_unavailable', ['outdoor_temperature'])
    else:
        adverse = any(not row['clear'] and instant(row['observed_at']) <= now < instant(row['valid_until']) for row in state['checks'].values())
        if adverse:
            action, reason = 'Avoid ventilation for now', 'An observed environmental constraint is adverse.'
        elif air['value'] > high and out['value'] <= air['value'] - 2:
            action, reason = 'Ventilate briefly', f'{air["value"]:g}°F indoors and {out["value"]:g}°F outdoors; cooler air can help reduce indoor heat.'
        elif air['value'] < low and out['value'] < air['value']:
            action, reason = 'Keep heat in', f'{air["value"]:g}°F indoors is below the comfort band; outdoors is colder at {out["value"]:g}°F.'
        elif air['value'] < low and out['value'] >= air['value'] + 2:
            action, reason = 'Use warmer outdoor air', f'{out["value"]:g}°F outdoors is warmer than the {air["value"]:g}°F interior.'
        elif air['value'] > high:
            action, reason = 'Wait for cooler outdoor air', f'{out["value"]:g}°F outdoors offers little cooling relative to {air["value"]:g}°F indoors.'
        else:
            action, reason = 'Keep ventilation steady', f'{air["value"]:g}°F indoors is within the comfort band.'
        sources = [air, out]
        for check in state['checks'].values():
            if instant(check['observed_at']) <= now < instant(check['valid_until']):
                sources.append({'until': instant(check['valid_until'])})
        comparison('ventilation', action, reason, sources)

    solar = projections.get('solar')
    valid_solar = False
    try:
        closed(solar, {'snapshot_id', 'source_ref', 'available_at', 'valid_until', 'direct_gain_available'})
        from ..evidence import digest
        digest(solar['source_ref'])
        valid_solar = (solar['snapshot_id'] == report['snapshot_id']
                       and instant(solar['available_at']) <= now < instant(solar['valid_until'])
                       and type(solar['direct_gain_available']) is bool)
    except (ValueError, TypeError, KeyError):
        pass
    if not valid_solar:
        report['domains']['shades'] = _domain('insufficient_evidence', 'provisional_solar_basis_unavailable', ['solar_gain_basis'])
        return True
    recent_deadlines = [instant(row['stop_observed_at']) + timedelta(seconds=600) for row in state['shade_movements']
                        if 0 <= (now - instant(row['stop_observed_at'])).total_seconds() < 600]
    recent = bool(recent_deadlines)
    gain = solar['direct_gain_available']
    if recent:
        action, reason = 'Keep the recent shade setting', 'Allow the recent setting time to settle before reconsidering.'
    elif gain and air['value'] > high:
        action, reason = 'Reduce solar heat gain', f'{air["value"]:g}°F indoors is above the comfort band while direct sun is available.'
    elif gain and air['value'] < low:
        action, reason = 'Use available solar heat', f'{air["value"]:g}°F indoors is below the comfort band while direct sun is available.'
    else:
        action, reason = 'No solar-driven shade change', 'No current solar/temperature advantage supports changing solar shading.'
    sources = [air, {'until': instant(solar['valid_until'])}]
    if recent:
        sources.append({'until': min(recent_deadlines)})
    comparison('shades', action, reason, sources)
    return True
