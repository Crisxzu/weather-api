import logging
import os
import re
from datetime import timedelta

import requests

from api.providers.base import WeatherProvider, WeatherServiceError, WeatherServiceUnavailableError
from api.providers.schemas import (
    Condition, CurrentWeather, DailyForecast, HourlyForecast, Location, WeatherData,
)
from api.utils.conditions import get_condition_by_code
from api.utils.timezone import get_time_for_timezone

logger = logging.getLogger(__name__)

_position_regex = r"-?\d+(\.\d+)?,-?\d+(\.\d+)?"
_ip_regex = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'


def _condition(cond: dict, is_day, lang_iso) -> Condition:
    code = cond['code']
    return Condition(
        code=code,
        # Codes missing from conditions.json (e.g. 1036 "Smoky haze", added by WeatherAPI
        # later) would give a null text, fail validation and return a 500.
        text=get_condition_by_code(code, is_day, lang_iso) or cond.get('text') or '',
        icon=int(cond['icon'].split('/')[-1].split('.')[0]),
    )


class WeatherAPIProvider(WeatherProvider):

    @property
    def supports_ip_query(self) -> bool:
        return True

    def get_weather(self, *, position, city, country_code, ip_address, lang_iso) -> WeatherData:
        url = f"{os.getenv('WEATHER_API_BASE_URL')}/forecast.json"
        params = {
            'key': os.getenv('WEATHER_API_KEY'),
            'days': 3,
            'aqi': 'no',
            'alerts': 'no',
        }

        if position and re.match(_position_regex, position):
            params['q'] = position
        elif city and city.strip():
            params['q'] = f"{city.strip()},{country_code.strip()}" if country_code and country_code.strip() else city.strip()
        elif ip_address and re.match(_ip_regex, ip_address):
            params['q'] = ip_address

        if params.get('q') is None:
            raise ValueError('No valid position, city or IP address provided')

        try:
            response = requests.get(url, params=params, timeout=10)
        except requests.exceptions.ConnectionError as e:
            logger.error('WeatherAPI unreachable: %s', e)
            raise WeatherServiceUnavailableError('Weather API unreachable') from e
        except requests.exceptions.Timeout as e:
            logger.error('WeatherAPI timed out: %s', e)
            raise WeatherServiceUnavailableError('Weather API timed out') from e

        if response.status_code != 200:
            error_code = None
            try:
                error_code = response.json().get('error', {}).get('code')
            except Exception:
                pass
            logger.warning('WeatherAPI returned %s, error code: %s', response.status_code, error_code)
            raise WeatherServiceError(http_status=response.status_code, error_code=error_code)

        data = response.json()
        now = get_time_for_timezone(data['location']['tz_id'])
        if now is None:
            raise WeatherServiceUnavailableError('Invalid timezone in WeatherAPI response')

        now_hour = now - timedelta(minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
        current_is_day = bool(data['current']['is_day'])
        forecast_days = data['forecast']['forecastday']
        loc = data['location']

        return WeatherData(
            last_updated=data['current']['last_updated_epoch'],
            source=os.getenv('WEATHER_API_SOURCE_NAME'),
            source_link=os.getenv('WEATHER_API_SOURCE_LINK'),
            location=Location(
                name=loc['name'],
                region=loc.get('region', ''),
                country=loc['country'],
                lat=loc['lat'],
                lon=loc['lon'],
                tz_id=loc['tz_id'],
                localtime_epoch=loc['localtime_epoch'],
                localtime=loc['localtime'],
            ),
            current=CurrentWeather(
                temp=data['current']['temp_c'],
                min_temp=forecast_days[0]['day']['mintemp_c'],
                max_temp=forecast_days[0]['day']['maxtemp_c'],
                is_day=current_is_day,
                feels_like=data['current']['feelslike_c'],
                condition=_condition(data['current']['condition'], current_is_day, lang_iso),
            ),
            next_24h=self._build_24h(now_hour, forecast_days, lang_iso),
            next_days=self._build_days(forecast_days, lang_iso),
        )

    def _build_24h(self, now_hour, forecast_days, lang_iso) -> list[HourlyForecast]:
        datetime_in_24h = now_hour + timedelta(hours=24)
        forecast_hours = []
        for day in forecast_days:
            forecast_hours.extend(day['hour'])

        return [
            HourlyForecast(
                temp=h['temp_c'],
                humidity=h['humidity'],
                timestamp=h['time_epoch'],
                is_day=h['is_day'],
                condition=_condition(h['condition'], h['is_day'], lang_iso),
            )
            for h in forecast_hours
            if now_hour.timestamp() <= h['time_epoch'] <= datetime_in_24h.timestamp()
        ]

    def _build_days(self, forecast_days, lang_iso) -> list[DailyForecast]:
        return [
            DailyForecast(
                min_temp=d['day']['mintemp_c'],
                max_temp=d['day']['maxtemp_c'],
                humidity=d['day']['avghumidity'],
                timestamp=d['date_epoch'],
                is_day=True,
                condition=_condition(d['day']['condition'], True, lang_iso),
            )
            for d in forecast_days
        ]
