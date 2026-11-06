"""
Air quality and pollen, fetched independently of the weather provider.

Neither weather provider exposes forecasts for these (WeatherAPI only has the
current air quality, no pollen), so they always come from Open-Meteo's Air
Quality API (CAMS data), whatever provider answered the weather request.
Results are cached on their own key (per ~1 km cell, shared across languages).
A failure never breaks the weather response: air_quality just stays None.
"""
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone

import requests
from django.core.cache import cache

from api.providers.base import get_forecast_days
from api.providers.schemas import AirQuality, AirQualityDay, AirQualityValues, Pollen

logger = logging.getLogger(__name__)

AIR_QUALITY_CACHE_TTL = int(os.getenv('WEATHER_AIR_QUALITY_CACHE_TTL', 3600))
_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'
_TIMEOUT_SECONDS = 3
_MAX_DAYS = 7  # Air Quality API horizon (pollen: ~4 days)

_POLLUTANTS = {  # our field -> Open-Meteo variable
    'european_aqi': 'european_aqi',
    'us_aqi': 'us_aqi',
    'pm2_5': 'pm2_5',
    'pm10': 'pm10',
    'ozone': 'ozone',
    'nitrogen_dioxide': 'nitrogen_dioxide',
}
_POLLENS = {
    'alder': 'alder_pollen',
    'birch': 'birch_pollen',
    'grass': 'grass_pollen',
    'mugwort': 'mugwort_pollen',
    'olive': 'olive_pollen',
    'ragweed': 'ragweed_pollen',
}
_VARIABLES = ','.join([*_POLLUTANTS.values(), *_POLLENS.values()])


def _provider() -> str:
    # Unset → openmeteo; explicitly empty → disabled.
    return os.getenv('WEATHER_AIR_QUALITY_PROVIDER', 'openmeteo').strip().lower()


def _pollen(get) -> Pollen | None:
    values = {field: get(var) for field, var in _POLLENS.items()}
    if all(v is None for v in values.values()):
        return None
    return Pollen(**values)


def _values(get) -> dict:
    return {
        **{field: get(var) for field, var in _POLLUTANTS.items()},
        'pollen': _pollen(get),
    }


def _max(values):
    present = [v for v in values if v is not None]
    return max(present) if present else None


def _parse(raw: dict) -> AirQuality:
    current_raw = raw['current']
    current = AirQualityValues(**_values(current_raw.get))

    hourly = raw['hourly']
    today = current_raw['time'][:10]  # local date
    dates = sorted({t[:10] for t in hourly['time'] if t[:10] >= today})[:get_forecast_days()]
    days = []
    for date in dates:
        idx = [i for i, t in enumerate(hourly['time']) if t.startswith(date)]

        def daily_max(var, idx=idx):
            return _max(hourly.get(var, [None] * len(hourly['time']))[i] for i in idx)

        ts = int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())
        days.append(AirQualityDay(**_values(daily_max), timestamp=ts))
    return AirQuality(current=current, days=days)


def _from_cache(data: dict) -> AirQuality:
    def values(d, cls, **extra):
        pollen = Pollen(**d['pollen']) if d['pollen'] is not None else None
        return cls(**{**d, 'pollen': pollen, **extra})

    return AirQuality(
        current=values(data['current'], AirQualityValues),
        days=[values(d, AirQualityDay) for d in data['days']],
    )


def get_air_quality(lat: float, lon: float) -> AirQuality | None:
    """Air quality and pollen for a location, or None if disabled or unavailable."""
    provider = _provider()
    if not provider:
        return None
    if provider != 'openmeteo':
        logger.warning('Unknown WEATHER_AIR_QUALITY_PROVIDER=%s, air quality disabled', provider)
        return None

    position = f'{lat:.2f},{lon:.2f}'
    cache_key = f'air_quality_{position}'
    cached = cache.get(cache_key)
    if cached is not None:
        return _from_cache(cached)

    try:
        resp = requests.get(
            _URL,
            params={
                'latitude': f'{lat:.2f}',
                'longitude': f'{lon:.2f}',
                'current': _VARIABLES,
                'hourly': _VARIABLES,
                'timezone': 'auto',
                'forecast_days': min(get_forecast_days(), _MAX_DAYS),
            },
            timeout=_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            logger.warning('Open-Meteo air quality returned HTTP %s', resp.status_code)
            return None
        result = _parse(resp.json())
    except Exception:
        logger.warning('Open-Meteo air quality unavailable for %s', position, exc_info=True)
        return None

    cache.set(cache_key, asdict(result), AIR_QUALITY_CACHE_TTL)
    return result
