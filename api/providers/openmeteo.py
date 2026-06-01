import logging
import re
from datetime import datetime, timedelta, timezone

import requests

from api.providers.base import WeatherProvider, WeatherServiceUnavailableError
from api.providers.schemas import (
    Condition, CurrentWeather, DailyForecast, HourlyForecast, Location, WeatherData,
)
from api.utils.conditions import get_condition_by_code, get_condition_by_wmo_code
from api.utils.ip_geolocation import resolve_ip
from api.utils.timezone import get_time_for_timezone

logger = logging.getLogger(__name__)

_position_regex = re.compile(r'^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$')

_FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
_GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search'
_NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'


class OpenMeteoProvider(WeatherProvider):

    @property
    def supports_ip_query(self) -> bool:
        return True

    def get_weather(self, *, position, city, country_code, ip_address, lang_iso) -> WeatherData:
        ip_meta = None

        if position:
            m = _position_regex.match(position)
            if m:
                lat, lon = float(m.group(1)), float(m.group(2))
            else:
                raise ValueError('Invalid position format, expected "lat,lon"')
        elif city and city.strip():
            lat, lon = self._geocode_city(city.strip(), country_code.strip() if country_code and country_code.strip() else None)
        elif ip_address:
            ip_meta = resolve_ip(ip_address)
            lat, lon = ip_meta.lat, ip_meta.lon
        else:
            raise ValueError('No valid position, city or IP address provided')

        raw = self._fetch_forecast(lat, lon)

        tz_id = raw['timezone']
        now = get_time_for_timezone(tz_id)
        if now is None:
            raise WeatherServiceUnavailableError('Invalid timezone in Open-Meteo response')

        now_hour = now - timedelta(minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
        now_epoch = int(now.timestamp())

        if ip_meta:
            loc_name = ip_meta.city or f'{lat},{lon}'
            loc_region = ip_meta.region
            loc_country = ip_meta.country or 'Unknown'
        else:
            geo = self._reverse_geocode(lat, lon)
            loc_name = geo['name']
            loc_region = geo['region']
            loc_country = geo['country']

        current = raw['current']
        daily = raw['daily']
        hourly = raw['hourly']

        is_day = bool(current['is_day'])
        mapped = get_condition_by_wmo_code(current['weather_code'])

        return WeatherData(
            last_updated=now_epoch,
            source='Open-Meteo',
            source_link='https://open-meteo.com/',
            location=Location(
                name=loc_name,
                region=loc_region,
                country=loc_country,
                lat=lat,
                lon=lon,
                tz_id=tz_id,
                localtime_epoch=now_epoch,
                localtime=now.strftime('%Y-%m-%d %H:%M'),
            ),
            current=CurrentWeather(
                temp=current['temperature_2m'],
                min_temp=daily['temperature_2m_min'][0],
                max_temp=daily['temperature_2m_max'][0],
                is_day=is_day,
                feels_like=current['apparent_temperature'],
                condition=Condition(
                    code=mapped.code,
                    text=get_condition_by_code(mapped.code, is_day, lang_iso),
                    icon=mapped.icon,
                ),
            ),
            next_24h=self._build_24h(now_hour, hourly, lang_iso),
            next_days=self._build_days(daily, lang_iso),
        )

    def _geocode_city(self, city: str, country_code: str | None = None) -> tuple[float, float]:
        params = {'name': city, 'count': 10, 'language': 'en', 'format': 'json'}
        try:
            resp = requests.get(_GEOCODING_URL, params=params, timeout=5)
        except requests.exceptions.RequestException as e:
            raise WeatherServiceUnavailableError(f'Open-Meteo geocoding unreachable: {e}') from e

        if resp.status_code != 200 or not resp.json().get('results'):
            raise WeatherServiceUnavailableError('No location found for city: ' + city)

        results = resp.json()['results']
        if country_code:
            cc = country_code.upper()
            match = next((r for r in results if r.get('country_code', '').upper() == cc), None)
            if match is None:
                raise WeatherServiceUnavailableError(f'No location found for city "{city}" in country "{country_code}"')
            result = match
        else:
            result = results[0]

        return float(result['latitude']), float(result['longitude'])

    def _reverse_geocode(self, lat: float, lon: float) -> dict:
        try:
            resp = requests.get(
                _NOMINATIM_URL,
                params={'lat': lat, 'lon': lon, 'format': 'json'},
                headers={'User-Agent': 'WeatherAppApi/1.0'},
                timeout=5,
            )
            if resp.status_code == 200:
                addr = resp.json().get('address', {})
                name = addr.get('city') or addr.get('town') or addr.get('village') or addr.get('county', '')
                return {
                    'name': name or f'{lat},{lon}',
                    'region': addr.get('state', ''),
                    'country': addr.get('country') or 'Unknown',
                }
        except Exception:
            logger.warning('Nominatim reverse geocoding failed for lat=%s lon=%s', lat, lon)
        return {'name': f'{lat},{lon}', 'region': '', 'country': 'Unknown'}

    def _fetch_forecast(self, lat: float, lon: float) -> dict:
        params = {
            'latitude': lat,
            'longitude': lon,
            'current': 'temperature_2m,apparent_temperature,weather_code,is_day',
            'hourly': 'temperature_2m,relative_humidity_2m,weather_code,is_day',
            'daily': 'temperature_2m_max,temperature_2m_min,weather_code,relative_humidity_2m_max',
            'timezone': 'auto',
            'forecast_days': 3,
        }
        try:
            resp = requests.get(_FORECAST_URL, params=params, timeout=10)
        except requests.exceptions.ConnectionError as e:
            raise WeatherServiceUnavailableError('Open-Meteo unreachable') from e
        except requests.exceptions.Timeout as e:
            raise WeatherServiceUnavailableError('Open-Meteo timed out') from e

        if resp.status_code != 200:
            raise WeatherServiceUnavailableError(f'Open-Meteo returned HTTP {resp.status_code}')

        return resp.json()

    def _build_24h(self, now_hour, hourly, lang_iso) -> list[HourlyForecast]:
        limit = now_hour + timedelta(hours=24)
        times = hourly['time']
        temps = hourly['temperature_2m']
        humidities = hourly['relative_humidity_2m']
        codes = hourly['weather_code']
        is_days = hourly['is_day']

        result = []
        for i, time_str in enumerate(times):
            ts = int(datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc).timestamp())
            if now_hour.timestamp() <= ts <= limit.timestamp():
                is_day = bool(is_days[i])
                mapped = get_condition_by_wmo_code(codes[i])
                result.append(HourlyForecast(
                    temp=temps[i],
                    humidity=humidities[i],
                    timestamp=ts,
                    is_day=is_day,
                    condition=Condition(
                        code=mapped.code,
                        text=get_condition_by_code(mapped.code, is_day, lang_iso),
                        icon=mapped.icon,
                    ),
                ))
        return result

    def _build_days(self, daily, lang_iso) -> list[DailyForecast]:
        result = []
        for i, date_str in enumerate(daily['time']):
            ts = int(datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc).timestamp())
            mapped = get_condition_by_wmo_code(daily['weather_code'][i])
            result.append(DailyForecast(
                min_temp=daily['temperature_2m_min'][i],
                max_temp=daily['temperature_2m_max'][i],
                humidity=daily['relative_humidity_2m_max'][i],
                timestamp=ts,
                is_day=True,
                condition=Condition(
                    code=mapped.code,
                    text=get_condition_by_code(mapped.code, True, lang_iso),
                    icon=mapped.icon,
                ),
            ))
        return result
