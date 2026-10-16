"""Observational infrastructure health. Activity never qualifies sensor state."""
from datetime import timedelta
import urllib.request
from services.observations.contract import instant


def gateway_health(engine,now):
    result=[]
    for gateway in engine.registry.config.get('gateways',[]):
        row=engine.store.state('gateway:'+gateway['gateway_id'])
        last=None if row is None else row['last_stats_received_at']
        recent=last is not None and 0<=(instant(now)-instant(last)).total_seconds()<gateway['offline_seconds']
        result.append(dict(gateway_id=gateway['gateway_id'],name=gateway['name'],
            health='ONLINE' if recent else 'OFFLINE' if last else 'UNKNOWN',last_stats_received_at=last,
            basis='authenticated_mqtt_stats_activity',radio_verified=False))
    return result


def chirpstack_probe(url):
    if url is None:return 'not_configured'
    # Fixed local service endpoint, no generic user-controlled URL fetch.
    if url not in ('http://chirpstack:8080/','http://127.0.0.1:18085/'):
        raise ValueError('fixed local ChirpStack probe endpoint required')
    try:
        with urllib.request.urlopen(url,timeout=2) as response:
            return 'http_responding' if response.status==200 else 'unavailable'
    except OSError:return 'unavailable'
