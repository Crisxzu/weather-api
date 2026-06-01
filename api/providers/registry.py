import logging
import os

from api.providers.base import WeatherProvider

logger = logging.getLogger(__name__)

_REGISTRY = None


def _get_registry() -> dict:
    global _REGISTRY
    if _REGISTRY is None:
        from api.providers.weatherapi import WeatherAPIProvider
        from api.providers.openmeteo import OpenMeteoProvider
        _REGISTRY = {
            'weatherapi': WeatherAPIProvider,
            'openmeteo': OpenMeteoProvider,
        }
    return _REGISTRY


def get_primary_provider() -> WeatherProvider:
    name = os.getenv('WEATHER_PRIMARY_PROVIDER', 'weatherapi').lower()
    cls = _get_registry().get(name)
    if cls is None:
        logger.warning('Unknown WEATHER_PRIMARY_PROVIDER=%s, falling back to weatherapi', name)
        from api.providers.weatherapi import WeatherAPIProvider
        cls = WeatherAPIProvider
    return cls()


def get_fallback_provider() -> WeatherProvider | None:
    name = os.getenv('WEATHER_FALLBACK_PROVIDER', '').lower()
    if not name:
        return None
    cls = _get_registry().get(name)
    if cls is None:
        logger.warning('Unknown WEATHER_FALLBACK_PROVIDER=%s, ignoring', name)
        return None
    return cls()
