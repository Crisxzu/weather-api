from datetime import datetime, timedelta

import os
import pytz
import requests
import json
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
import re

from rest_framework_api_key.permissions import HasAPIKey
from rest_framework_simplejwt.authentication import JWTAuthentication

from api.serializers import WeatherDataSerializer

# Create your views here.

position_regex = "\-?\d+(\.\d+)?,-?\d+(\.\d+)?"
ip_address_regex = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'

conditions = []

with open("conditions.json", 'r') as f:
    conditions = json.load(f)

class WeatherDataView(APIView):
    permission_classes = [HasAPIKey]
    def get(self, request):
        position = request.query_params.get('position')
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        lang_iso = request.query_params.get('lang_iso', 'en')

        print(f'position: {position}')
        print(f'lang_iso: {lang_iso}')
        print(f'ip_address: {ip_address}')
        weather_data = get_current_weather(
            position=position,
            ip_address=ip_address,
            lang_iso=lang_iso,
        )

        if not weather_data:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        serializer = WeatherDataSerializer(data=weather_data)

        if not serializer.is_valid():
            print(serializer.errors)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.data)



def get_current_weather(position : str = None, ip_address : str = None, lang_iso : str = None):
    url = f"{os.getenv('WEATHER_API_BASE_URL')}/forecast.json"
    params = {
        'key': os.getenv('WEATHER_API_KEY'),
        'days': 3,
        'aqi': 'no',
        'alerts': 'no'
    }
    if position and re.match(position_regex, position):
        params['q'] = position
    elif ip_address and re.match(ip_address_regex, ip_address):
        params['q'] = ip_address

    if params.get('q') is None:
        return None

    try:
        response = requests.get(url, params=params)

        if response.status_code != 200:
            return None

        data = response.json()
        now = get_time_for_timezone(tz_id=data['location']['tz_id'])

        if now is None:
            return None

        now_hour = now - timedelta(minutes=now.minute, seconds=now.second, microseconds=now.microsecond)

        current_is_day = bool(data['current']['is_day'])
        forecast_days = data['forecast']['forecastday']

        return {
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
                    )
                } ,
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

    except Exception as e:
        print(e)
        return None



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
        print(f"Fuseau horaire inconnu : {tz_id}")
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
                )
            }
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
                )
            }
        }
        for forecast_day in forecast_days
    ]

    return result