"""
Weather alerts fetched independently of the weather provider.

Open-Meteo has no official alerts, so when the provider that answered returns
alerts=None we ask WeatherAPI's lightweight alerts.json endpoint instead.
Results are cached on their own key (per ~1 km cell, shared across languages)
so the shorter nowcast TTL of weather responses does not multiply calls.
A failure never breaks the weather response: alerts just stay None.
"""
import logging
import os

import requests
from django.core.cache import cache

from api.providers.schemas import WeatherAlert
from api.providers.weatherapi import parse_alerts

logger = logging.getLogger(__name__)

ALERTS_CACHE_TTL = int(os.getenv('WEATHER_ALERTS_CACHE_TTL', 1800))
_TIMEOUT_SECONDS = 3


def _alerts_provider() -> str:
    # Unset → weatherapi; explicitly empty → disabled.
    return os.getenv('WEATHER_ALERTS_PROVIDER', 'weatherapi').strip().lower()


def get_alerts(lat: float, lon: float) -> list[WeatherAlert] | None:
    """Alerts for a location, or None if disabled, misconfigured or unavailable."""
    provider = _alerts_provider()
    if not provider:
        return None
    if provider != 'weatherapi':
        logger.warning('Unknown WEATHER_ALERTS_PROVIDER=%s, alerts disabled', provider)
        return None

    api_key = os.getenv('WEATHER_API_KEY')
    base_url = os.getenv('WEATHER_API_BASE_URL')
    if not api_key or not base_url:
        return None

    position = f'{lat:.2f},{lon:.2f}'
    cache_key = f'alerts_{position}'
    cached = cache.get(cache_key)
    if cached is not None:  # [] is a valid cached value
        return [WeatherAlert(**a) for a in cached]

    try:
        resp = requests.get(
            f'{base_url}/alerts.json',
            params={'key': api_key, 'q': position},
            timeout=_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            logger.warning('WeatherAPI alerts returned HTTP %s', resp.status_code)
            return None
        alerts = parse_alerts(resp.json().get('alerts'))
    except Exception:
        logger.warning('WeatherAPI alerts unavailable for %s', position, exc_info=True)
        return None

    if alerts is not None:
        cache.set(cache_key, [a.__dict__ for a in alerts], ALERTS_CACHE_TTL)
    return alerts
