import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from api.providers.base import WeatherProvider, WeatherServiceUnavailableError, get_forecast_days
from api.providers.schemas import (
    Condition, CurrentWeather, DailyForecast, HourlyForecast, Location, MinutelyPrecipitation, WeatherData,
    YesterdayWeather,
)
from api.utils.conditions import get_condition_by_code, get_condition_by_wmo_code
from api.utils.ip_geolocation import resolve_ip
from api.utils.timezone import get_time_for_timezone, local_to_epoch

logger = logging.getLogger(__name__)

_position_regex = re.compile(r'^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$')

_FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
_GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search'
_NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
# Nominatim's usage policy requires an identifying User-Agent.
_NOMINATIM_USER_AGENT = os.getenv(
    'NOMINATIM_USER_AGENT', 'WeatherAppApi/1.0 (+https://github.com/Crisxzu/weather-api)'
)

_CURRENT_VARS = (
    'temperature_2m,apparent_temperature,weather_code,is_day,relative_humidity_2m,'
    'wind_speed_10m,wind_direction_10m,wind_gusts_10m,uv_index,precipitation,cloud_cover,visibility'
)
_HOURLY_VARS = (
    'temperature_2m,relative_humidity_2m,weather_code,is_day,precipitation_probability,'
    'precipitation,apparent_temperature,wind_speed_10m,uv_index,cloud_cover,visibility,snowfall'
)
_DAILY_VARS = (
    'temperature_2m_max,temperature_2m_min,weather_code,relative_humidity_2m_max,'
    'precipitation_probability_max,precipitation_sum,wind_speed_10m_max,uv_index_max,sunrise,sunset,'
    'snowfall_sum'
)
_MINUTELY_STEPS = 8  # 8 x 15 min = next 2 hours


def _at(block: dict, key: str, i: int):
    """Value of block[key][i], or None if the variable or index is missing."""
    values = block.get(key)
    if values is None or i >= len(values):
        return None
    return values[i]


def _m_to_km(meters):
    """Open-Meteo reports visibility in meters; the API exposes km like WeatherAPI."""
    return None if meters is None else round(meters / 1000, 2)


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
        hourly = raw['hourly']
        # past_days=1 puts yesterday first in the daily arrays: locate today
        # rather than assuming its position.
        today_idx = self._index_of(raw['daily']['time'], now.strftime('%Y-%m-%d'))
        daily = {k: v[today_idx:] for k, v in raw['daily'].items()}
        yesterday = (
            self._build_yesterday(raw['daily'], today_idx - 1, hourly, now_hour, lang_iso)
            if today_idx > 0 else None
        )

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
                humidity=current.get('relative_humidity_2m'),
                wind_kph=current.get('wind_speed_10m'),
                wind_degree=current.get('wind_direction_10m'),
                gust_kph=current.get('wind_gusts_10m'),
                uv=current.get('uv_index'),
                precip_mm=current.get('precipitation'),
                cloud_cover=current.get('cloud_cover'),
                visibility_km=_m_to_km(current.get('visibility')),
            ),
            next_24h=self._build_24h(now_hour, hourly, tz_id, lang_iso),
            next_days=self._build_days(daily, tz_id, lang_iso),
            next_minutes=self._build_minutes(raw.get('minutely_15'), tz_id),
            # Open-Meteo has no official weather alerts: None = "not supported", not "no alert".
            alerts=None,
            yesterday=yesterday,
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
                headers={'User-Agent': _NOMINATIM_USER_AGENT},
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
            'current': _CURRENT_VARS,
            'hourly': _HOURLY_VARS,
            'daily': _DAILY_VARS,
            'minutely_15': 'precipitation',
            'forecast_minutely_15': _MINUTELY_STEPS,
            'timezone': 'auto',
            'forecast_days': get_forecast_days(),
            'past_days': 1,
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

    def _build_24h(self, now_hour, hourly, tz_id, lang_iso) -> list[HourlyForecast]:
        limit = now_hour + timedelta(hours=24)
        times = hourly['time']
        temps = hourly['temperature_2m']
        humidities = hourly['relative_humidity_2m']
        codes = hourly['weather_code']
        is_days = hourly['is_day']

        result = []
        for i, time_str in enumerate(times):
            # With timezone=auto, Open-Meteo returns wall-clock times in the location's timezone.
            ts = local_to_epoch(time_str, None, tz_id)
            if ts is not None and now_hour.timestamp() <= ts <= limit.timestamp():
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
                    chance_of_rain=_at(hourly, 'precipitation_probability', i),
                    # No snow probability in Open-Meteo; better null than a made-up value.
                    chance_of_snow=None,
                    precip_mm=_at(hourly, 'precipitation', i),
                    feels_like=_at(hourly, 'apparent_temperature', i),
                    wind_kph=_at(hourly, 'wind_speed_10m', i),
                    uv=_at(hourly, 'uv_index', i),
                    cloud_cover=_at(hourly, 'cloud_cover', i),
                    visibility_km=_m_to_km(_at(hourly, 'visibility', i)),
                    snow_cm=_at(hourly, 'snowfall', i),
                ))
        return result

    def _build_days(self, daily, tz_id, lang_iso) -> list[DailyForecast]:
        result = []
        for i, date_str in enumerate(daily['time']):
            # Day timestamps are midnight UTC of the calendar date, on purpose:
            # it matches WeatherAPI's date_epoch, so clients see the same convention
            # whichever provider answered.
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
                chance_of_rain=_at(daily, 'precipitation_probability_max', i),
                chance_of_snow=None,
                total_precip_mm=_at(daily, 'precipitation_sum', i),
                max_wind_kph=_at(daily, 'wind_speed_10m_max', i),
                uv=_at(daily, 'uv_index_max', i),
                sunrise=local_to_epoch(_at(daily, 'sunrise', i), None, tz_id),
                sunset=local_to_epoch(_at(daily, 'sunset', i), None, tz_id),
                total_snow_cm=_at(daily, 'snowfall_sum', i),
            ))
        return result

    @staticmethod
    def _index_of(values: list, value) -> int:
        try:
            return values.index(value)
        except ValueError:
            return 0

    def _build_yesterday(self, daily, i, hourly, now_hour, lang_iso) -> YesterdayWeather:
        # Same wall-clock hour yesterday (pytz arithmetic keeps the local fields).
        same_hour = (now_hour - timedelta(days=1)).strftime('%Y-%m-%dT%H:00')
        try:
            temp_same_hour = hourly['temperature_2m'][hourly['time'].index(same_hour)]
        except (ValueError, KeyError, IndexError):
            temp_same_hour = None

        code = _at(daily, 'weather_code', i)
        condition = None
        if code is not None:
            mapped = get_condition_by_wmo_code(code)
            condition = Condition(
                code=mapped.code,
                text=get_condition_by_code(mapped.code, True, lang_iso),
                icon=mapped.icon,
            )
        return YesterdayWeather(
            min_temp=_at(daily, 'temperature_2m_min', i),
            max_temp=_at(daily, 'temperature_2m_max', i),
            temp_same_hour=temp_same_hour,
            condition=condition,
        )

    def _build_minutes(self, minutely, tz_id) -> list[MinutelyPrecipitation] | None:
        # Real 15-minute data only exists over Central Europe and North America;
        # elsewhere Open-Meteo interpolates hourly values.
        if not minutely or not minutely.get('time'):
            return None
        result = []
        for i, time_str in enumerate(minutely['time']):
            ts = local_to_epoch(time_str, None, tz_id)
            if ts is not None:
                result.append(MinutelyPrecipitation(timestamp=ts, precip_mm=_at(minutely, 'precipitation', i)))
        return result
