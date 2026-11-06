import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from api.providers.base import (
    WeatherProvider, WeatherServiceError, WeatherServiceUnavailableError, get_forecast_days,
)
from api.providers.schemas import (
    Condition, CurrentWeather, DailyForecast, HourlyForecast, Location, WeatherAlert, WeatherData,
    YesterdayWeather,
)
from api.utils.conditions import get_condition_by_code
from api.utils.timezone import get_time_for_timezone, local_to_epoch

logger = logging.getLogger(__name__)

_position_regex = r"-?\d+(\.\d+)?,-?\d+(\.\d+)?"
_HISTORY_TIMEOUT_SECONDS = 3
_ip_regex = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'


def _condition(cond: dict, is_day, lang_iso) -> Condition:
    code = cond['code']
    return Condition(
        code=code,
        # A code missing from conditions.json (WeatherAPI adds some over time, see
        # `manage.py update_conditions`) would give a null text, fail validation and return a 500.
        text=get_condition_by_code(code, is_day, lang_iso) or cond.get('text') or '',
        icon=int(cond['icon'].split('/')[-1].split('.')[0]),
    )


def _iso_to_epoch(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def parse_alerts(alerts_block: dict | None) -> list[WeatherAlert] | None:
    """Map WeatherAPI's {"alert": [...]} block. None if the block is absent."""
    if alerts_block is None:
        return None
    return [
        WeatherAlert(
            event=a.get('event') or '',
            headline=a.get('headline') or '',
            severity=a.get('severity') or '',
            effective=_iso_to_epoch(a.get('effective')),
            expires=_iso_to_epoch(a.get('expires')),
        )
        for a in alerts_block.get('alert') or []
    ]


class WeatherAPIProvider(WeatherProvider):

    @property
    def supports_ip_query(self) -> bool:
        return True

    def get_weather(self, *, position, city, country_code, ip_address, lang_iso) -> WeatherData:
        url = f"{os.getenv('WEATHER_API_BASE_URL')}/forecast.json"
        params = {
            'key': os.getenv('WEATHER_API_KEY'),
            'days': get_forecast_days(),
            'aqi': 'no',
            'alerts': 'yes',
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
        cur = data['current']

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
                humidity=cur.get('humidity'),
                wind_kph=cur.get('wind_kph'),
                wind_degree=cur.get('wind_degree'),
                gust_kph=cur.get('gust_kph'),
                uv=cur.get('uv'),
                precip_mm=cur.get('precip_mm'),
                cloud_cover=cur.get('cloud'),
                visibility_km=cur.get('vis_km'),
            ),
            next_24h=self._build_24h(now_hour, forecast_days, lang_iso),
            next_days=self._build_days(forecast_days, loc['tz_id'], lang_iso),
            # 15-minute precipitation is not available on standard WeatherAPI plans.
            next_minutes=None,
            alerts=parse_alerts(data.get('alerts')),
            yesterday=self._fetch_yesterday(loc['lat'], loc['lon'], now_hour, lang_iso),
        )

    def _fetch_yesterday(self, lat, lon, now_hour, lang_iso) -> YesterdayWeather | None:
        """Yesterday's weather from history.json (second call). None on any failure:
        it only feeds comparison messages and must not break the response."""
        same_hour = now_hour - timedelta(days=1)  # same local wall-clock hour
        date = same_hour.strftime('%Y-%m-%d')
        try:
            resp = requests.get(
                f"{os.getenv('WEATHER_API_BASE_URL')}/history.json",
                params={'key': os.getenv('WEATHER_API_KEY'), 'q': f'{lat},{lon}', 'dt': date},
                timeout=_HISTORY_TIMEOUT_SECONDS,
            )
            if resp.status_code != 200:
                logger.warning('WeatherAPI history returned HTTP %s', resp.status_code)
                return None
            day = resp.json()['forecast']['forecastday'][0]
        except Exception:
            logger.warning('WeatherAPI history unavailable', exc_info=True)
            return None
        if day.get('date') != date:
            return None

        hour_key = same_hour.strftime('%Y-%m-%d %H:00')
        temp_same_hour = next((h.get('temp_c') for h in day.get('hour', []) if h.get('time') == hour_key), None)
        return YesterdayWeather(
            min_temp=day['day'].get('mintemp_c'),
            max_temp=day['day'].get('maxtemp_c'),
            temp_same_hour=temp_same_hour,
            condition=_condition(day['day']['condition'], True, lang_iso) if day['day'].get('condition') else None,
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
                chance_of_rain=h.get('chance_of_rain'),
                chance_of_snow=h.get('chance_of_snow'),
                precip_mm=h.get('precip_mm'),
                feels_like=h.get('feelslike_c'),
                wind_kph=h.get('wind_kph'),
                uv=h.get('uv'),
                cloud_cover=h.get('cloud'),
                visibility_km=h.get('vis_km'),
                snow_cm=h.get('snow_cm'),
            )
            for h in forecast_hours
            if now_hour.timestamp() <= h['time_epoch'] <= datetime_in_24h.timestamp()
        ]

    def _build_days(self, forecast_days, tz_id, lang_iso) -> list[DailyForecast]:
        return [
            DailyForecast(
                min_temp=d['day']['mintemp_c'],
                max_temp=d['day']['maxtemp_c'],
                humidity=d['day']['avghumidity'],
                timestamp=d['date_epoch'],
                is_day=True,
                condition=_condition(d['day']['condition'], True, lang_iso),
                chance_of_rain=d['day'].get('daily_chance_of_rain'),
                chance_of_snow=d['day'].get('daily_chance_of_snow'),
                total_precip_mm=d['day'].get('totalprecip_mm'),
                max_wind_kph=d['day'].get('maxwind_kph'),
                uv=d['day'].get('uv'),
                sunrise=self._astro_epoch(d, 'sunrise', tz_id),
                sunset=self._astro_epoch(d, 'sunset', tz_id),
                total_snow_cm=d['day'].get('totalsnow_cm'),
            )
            for d in forecast_days
        ]

    @staticmethod
    def _astro_epoch(forecast_day: dict, key: str, tz_id: str) -> int | None:
        # astro times are local wall-clock like "07:45 AM", or "No sunrise" near the poles.
        value = (forecast_day.get('astro') or {}).get(key)
        if not value:
            return None
        return local_to_epoch(f"{forecast_day['date']} {value}", '%Y-%m-%d %I:%M %p', tz_id)
