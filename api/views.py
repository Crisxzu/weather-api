from datetime import datetime, timedelta
from pathlib import Path

import logging
import os
import pytz
import requests
import json
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
import re

from rest_framework_api_key.permissions import HasAPIKey

logger = logging.getLogger(__name__)

from api.serializers import WeatherDataSerializer


class WeatherServiceUnavailableError(Exception):
    pass

class WeatherServiceError(Exception):
    MESSAGES = {
        1002: 'API key not provided.',
        1003: "Parameter 'q' not provided.",
        1005: 'API request URL is invalid.',
        1006: 'No location found matching the provided parameter.',
        2006: 'API key is invalid.',
        2007: 'API key has exceeded its monthly call quota.',
        2008: 'API key has been disabled.',
        2009: 'API key does not have access to this resource.',
        9000: 'Invalid JSON body in request.',
        9001: 'Too many locations in bulk request.',
        9999: 'Internal weather service error.',
    }

    def __init__(self, http_status, error_code=None):
        self.http_status = http_status
        self.error_code = error_code
        self.message = self.MESSAGES.get(error_code, 'An unexpected error occurred with the weather service.')
        super().__init__(self.message)

position_regex = "\-?\d+(\.\d+)?,-?\d+(\.\d+)?"
ip_address_regex = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'

CACHE_TTL = int(os.getenv('WEATHER_CACHE_TTL', 3600))

_conditions_path = Path(__file__).resolve().parent.parent / 'conditions.json'
with open(_conditions_path, 'r') as f:
    conditions = json.load(f)

def _log_cache_backend():
    from django.conf import settings
    backend = settings.CACHES['default']['BACKEND']
    if 'redis' in backend.lower():
        logger.info('Cache backend: Redis (%s)', settings.CACHES['default'].get('LOCATION'))
    else:
        logger.info('Cache backend: LocMemCache (in-process memory)')

_log_cache_backend()

class WeatherDataView(APIView):
    permission_classes = [HasAPIKey]
    def get(self, request):
        position = request.query_params.get('position')
        city = request.query_params.get('city')
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        lang_iso = request.query_params.get('lang_iso', 'en')

        logger.debug('Incoming request — position=%s city=%s ip=%s lang=%s', position, city, ip_address, lang_iso)
        try:
            weather_data = get_current_weather(
                position=position,
                city=city,
                ip_address=ip_address,
                lang_iso=lang_iso,
            )
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

        serializer = WeatherDataSerializer(data=weather_data)

        if not serializer.is_valid():
            logger.error('Serializer validation failed: %s', serializer.errors)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.data)



def get_current_weather(position : str = None, city: str = None, ip_address : str = None, lang_iso : str = None):
    url = f"{os.getenv('WEATHER_API_BASE_URL')}/forecast.json"
    params = {
        'key': os.getenv('WEATHER_API_KEY'),
        'days': 3,
        'aqi': 'no',
        'alerts': 'no'
    }
    if position and re.match(position_regex, position):
        params['q'] = position
    elif city and city.strip():
        params['q'] = city.strip()
    elif ip_address and re.match(ip_address_regex, ip_address):
        params['q'] = ip_address

    if params.get('q') is None:
        raise ValueError('No valid position, city or IP address provided')

    cache_key = f"weather_{params['q']}_{lang_iso}"
    cached = cache.get(cache_key)
    if cached:
        logger.info('Cache hit for key=%s', cache_key)
        return cached

    logger.info('Cache miss for key=%s — fetching from weather API', cache_key)

    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.ConnectionError as e:
        logger.error('Weather API unreachable: %s', e)
        raise WeatherServiceUnavailableError('Weather API unreachable')
    except requests.exceptions.Timeout as e:
        logger.error('Weather API timed out: %s', e)
        raise WeatherServiceUnavailableError('Weather API timed out')

    if response.status_code != 200:
        error_code = None
        try:
            error_code = response.json().get('error', {}).get('code')
        except Exception:
            pass
        logger.warning('Weather API returned %s, error code: %s', response.status_code, error_code)
        raise WeatherServiceError(http_status=response.status_code, error_code=error_code)

    try:
        data = response.json()
        now = get_time_for_timezone(tz_id=data['location']['tz_id'])

        if now is None:
            raise WeatherServiceError('Invalid timezone in weather response')

        now_hour = now - timedelta(minutes=now.minute, seconds=now.second, microseconds=now.microsecond)

        current_is_day = bool(data['current']['is_day'])
        forecast_days = data['forecast']['forecastday']

        result = {
            'last_updated': data['current']['last_updated_epoch'],
            'source': os.getenv('WEATHER_API_SOURCE_NAME'),
            'source_link': os.getenv('WEATHER_API_SOURCE_LINK'),
            'location': data['location'],
            'current': {
                'temp': data['current']['temp_c'],
                'min_temp': forecast_days[0]['day']['mintemp_c'],
                'max_temp': forecast_days[0]['day']['maxtemp_c'],
                'is_day': current_is_day,
                'feels_like': data['current']['feelslike_c'],
                'condition': {
                    'code': data['current']['condition']['code'],
                    'text': get_condition_by_code(
                        code=data['current']['condition']['code'],
                        is_day=current_is_day,
                        lang_iso=lang_iso
                    ),
                    'icon': int(f"{data['current']['condition']['icon'].split('/')[-1].split('.')[0]}"),
                },
            },
            'next_24h': get_next_24h_forecast(
                now=now_hour,
                forecast_data=forecast_days,
                lang_iso=lang_iso
            ),
            'next_days': get_next_days_forecast(
                now=now_hour,
                forecast_data=forecast_days,
                lang_iso=lang_iso
            )
        }
        cache.set(cache_key, result, CACHE_TTL)
        logger.info('Weather data cached for key=%s (TTL=%ss)', cache_key, CACHE_TTL)
        return result

    except (WeatherServiceError, WeatherServiceUnavailableError):
        raise
    except Exception as e:
        logger.exception('Unexpected error while processing weather data: %s', e)
        raise



def get_time_for_timezone(tz_id):
    """
    Obtient l'heure actuelle pour un fuseau horaire donné.

    Args:
        tz_id: L'ID du fuseau horaire (par exemple, "America/Los_Angeles", "Europe/Paris").

    Returns:
        Une chaîne représentant l'heure actuelle dans le fuseau horaire spécifié,
        ou None si le fuseau horaire est invalide.
    """
    try:
        timezone = pytz.timezone(tz_id)
        now_in_tz = datetime.now(timezone)
        return now_in_tz
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error('Unknown timezone: %s', tz_id)
        return None


def get_condition_by_code(code : int, is_day : bool, lang_iso : str = None):
    for condition in conditions:
        if condition['code'] == code:
            default = condition['day'] if is_day else condition['night']

            if lang_iso:
                result = [language for language in condition['languages'] if language['lang_iso'] == lang_iso]
                if not result:
                    return default

                language = result[0]
                return language['day_text'] if is_day else language['night_text']
            else:
                return default

    return None


def get_next_24h_forecast(now, forecast_data, lang_iso : str = None):
    datetime_in_24h = now + timedelta(hours=24)
    result = [forecast_day['hour'] for forecast_day in forecast_data]
    forecast_hours = []

    for day in result:
        forecast_hours.extend(day)

    result = [
        {
            'temp': forecast_hour['temp_c'],
            'humidity': forecast_hour['humidity'],
            'timestamp': forecast_hour['time_epoch'],
            'condition': {
                'code': forecast_hour['condition']['code'],
                'text': get_condition_by_code(
                    code=forecast_hour['condition']['code'],
                    is_day=forecast_hour['is_day'],
                    lang_iso=lang_iso
                ),
                'icon': int(f"{forecast_hour['condition']['icon'].split('/')[-1].split('.')[0]}"),
            },
            'is_day': forecast_hour['is_day'],
        }
            for forecast_hour in forecast_hours
                if now.timestamp() <= forecast_hour['time_epoch'] <= datetime_in_24h.timestamp()
    ]

    return result

def get_next_days_forecast(now, forecast_data, lang_iso : str = None):
    forecast_days = [{'date_epoch': forecast_day['date_epoch'], **forecast_day['day']} for forecast_day in forecast_data]

    result = [
        {
            'min_temp': forecast_day['mintemp_c'],
            'max_temp': forecast_day['maxtemp_c'],
            'humidity': forecast_day['avghumidity'],
            'timestamp': forecast_day['date_epoch'],
            'condition': {
                'code': forecast_day['condition']['code'],
                'text': get_condition_by_code(
                    code=forecast_day['condition']['code'],
                    is_day=True,
                    lang_iso=lang_iso
                ),
                'icon': int(f"{forecast_day['condition']['icon'].split('/')[-1].split('.')[0]}"),
            },
            'is_day': True,
        }
        for forecast_day in forecast_days
    ]

    return result