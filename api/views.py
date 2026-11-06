import logging
import os
import re
from dataclasses import asdict

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_api_key.permissions import HasAPIKey

from api.providers.air_quality import get_air_quality
from api.providers.alerts import get_alerts
from api.providers.base import WeatherServiceError, WeatherServiceUnavailableError
from api.providers.registry import get_primary_provider, get_fallback_provider
from api.serializers import WeatherDataSerializer

logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv('WEATHER_CACHE_TTL', 3600))
# Shorter TTL when the response carries 15-minute precipitation ("rain in ~20 min").
NOWCAST_CACHE_TTL = int(os.getenv('WEATHER_NOWCAST_CACHE_TTL', 900))

_position_regex = re.compile(r'^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$')
POSITION_PRECISION = 2  # ~1.1 km: nearby users share cache entries and upstream calls


def round_position(position: str | None) -> str | None:
    """Round "lat,lon" to POSITION_PRECISION decimals; leave anything else untouched."""
    if not position:
        return position
    m = _position_regex.match(position)
    if not m:
        return position
    # "+ 0.0" turns -0.0 into 0.0 so both spellings share one cache key
    lat, lon = (round(float(g), POSITION_PRECISION) + 0.0 for g in m.groups())
    return f'{lat:.{POSITION_PRECISION}f},{lon:.{POSITION_PRECISION}f}'


class WeatherDataView(APIView):
    permission_classes = [HasAPIKey]

    def get(self, request):
        # Rounded before both the cache key and the provider call, so a cached
        # entry is exactly what any user in that ~1 km cell would have received.
        position = round_position(request.query_params.get('position'))
        city = request.query_params.get('city')
        country_code = request.query_params.get('country_code')
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        lang_iso = request.query_params.get('lang_iso', 'en')

        logger.debug('Incoming request — position=%s city=%s country_code=%s ip=%s lang=%s', position, city, country_code, ip_address, lang_iso)

        query_key = position or (f'{city},{country_code}' if city and country_code else city) or ip_address or 'unknown'
        cache_key = f'weather_{query_key}_{lang_iso}'

        cached = cache.get(cache_key)
        if cached:
            logger.info('Cache hit for key=%s', cache_key)
            return Response(cached)

        logger.info('Cache miss for key=%s — fetching from provider', cache_key)

        query_kwargs = dict(position=position, city=city, country_code=country_code, ip_address=ip_address, lang_iso=lang_iso)

        try:
            weather_data = self._fetch_with_fallback(query_kwargs)
        except ValueError as e:
            logger.warning('Bad request: %s', e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except WeatherServiceUnavailableError as e:
            logger.error('Weather service unavailable: %s', e)
            return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except WeatherServiceError as e:
            logger.error('Weather service error (HTTP %s, code %s): %s', e.http_status, e.error_code, e.message)
            return Response({'error': e.message}, status=e.http_status)
        except Exception:
            logger.exception('Unexpected exception while handling weather request')
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if weather_data.alerts is None:
            weather_data.alerts = get_alerts(weather_data.location.lat, weather_data.location.lon)
        if weather_data.air_quality is None:
            weather_data.air_quality = get_air_quality(weather_data.location.lat, weather_data.location.lon)

        serializer = WeatherDataSerializer(data=asdict(weather_data))
        if not serializer.is_valid():
            logger.error('Serializer validation failed: %s', serializer.errors)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        ttl = min(CACHE_TTL, NOWCAST_CACHE_TTL) if serializer.data.get('next_minutes') else CACHE_TTL
        cache.set(cache_key, serializer.data, ttl)
        logger.info('Weather data cached for key=%s (TTL=%ss)', cache_key, ttl)
        return Response(serializer.data)

    def _fetch_with_fallback(self, query_kwargs: dict) -> dict:
        primary = get_primary_provider()
        try:
            return primary.get_weather(**query_kwargs)
        except WeatherServiceUnavailableError as primary_exc:
            logger.warning('Primary provider failed (%s), trying fallback', primary_exc)
            fallback = get_fallback_provider()
            if fallback is None:
                raise
            return fallback.get_weather(**query_kwargs)
