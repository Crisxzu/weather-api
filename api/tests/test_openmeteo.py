import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase

from api.providers.base import WeatherServiceUnavailableError
from api.providers.openmeteo import OpenMeteoProvider
from api.providers.schemas import WeatherData

_FIXTURES = Path(__file__).parent / 'fixtures'


def _load_fixture(name):
    with open(_FIXTURES / name) as f:
        return json.load(f)


def _mock_response(data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    return mock


def _make_requests_get_side_effect(forecast, nominatim=None, geocoding=None, ipapi=None):
    """
    Returns a side_effect function that dispatches mock responses based on the URL called.
    """
    def side_effect(url, **kwargs):
        if 'nominatim' in url:
            return _mock_response(nominatim or _load_fixture('nominatim_response.json'))
        if 'geocoding-api' in url:
            return _mock_response(geocoding or _load_fixture('openmeteo_geocoding_response.json'))
        if 'ip-api' in url:
            return _mock_response(ipapi or _load_fixture('ipapi_response.json'))
        return _mock_response(forecast)
    return side_effect


class OpenMeteoProviderHappyPathTests(TestCase):

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_position_query_returns_weather_data(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        provider = OpenMeteoProvider()
        result = provider.get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

        self.assertIsInstance(result, WeatherData)
        self.assertEqual(result.location.lat, 48.8566)
        self.assertEqual(result.location.lon, 2.3522)
        self.assertEqual(result.current.temp, 18.0)
        self.assertEqual(result.current.feels_like, 17.2)
        self.assertTrue(result.current.is_day)
        self.assertEqual(result.source, 'Open-Meteo')

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_city_query_geocodes_then_fetches(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        result = OpenMeteoProvider().get_weather(position=None, city='Paris', country_code=None, ip_address=None, lang_iso='en')
        self.assertIsInstance(result, WeatherData)

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_ip_query_resolves_coordinates_then_fetches(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        mock_ipget.return_value = _mock_response(_load_fixture('ipapi_response.json'))
        result = OpenMeteoProvider().get_weather(position=None, city=None, country_code=None, ip_address='81.2.69.142', lang_iso='en')
        self.assertIsInstance(result, WeatherData)
        # Location metadata comes from ip-api, not Nominatim
        self.assertEqual(result.location.name, 'Paris')
        self.assertEqual(result.location.country, 'France')

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_condition_text_is_localized(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='fr')
        self.assertIsNotNone(result.current.condition.text)

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_next_days_has_three_entries(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertEqual(len(result.next_days), 3)


class OpenMeteoProviderNominatimFallbackTests(TestCase):

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_nominatim_down_uses_coords_as_name(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')

        def side_effect(url, **kwargs):
            if 'nominatim' in url:
                raise Exception('Nominatim unreachable')
            return _mock_response(forecast)

        mock_get.side_effect = side_effect
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertIsInstance(result, WeatherData)
        self.assertIn('48.8566', result.location.name)
        self.assertEqual(result.location.country, 'Unknown')

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_nominatim_non_200_uses_coords_as_name(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')

        def side_effect(url, **kwargs):
            if 'nominatim' in url:
                return _mock_response({}, status_code=503)
            return _mock_response(forecast)

        mock_get.side_effect = side_effect
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertIsInstance(result, WeatherData)
        self.assertIn('48.8566', result.location.name)


class OpenMeteoProviderCountryCodeTests(TestCase):

    @patch('api.providers.openmeteo.requests.get')
    def test_country_code_selects_matching_result(self, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(
            forecast,
            geocoding=_load_fixture('openmeteo_geocoding_ambiguous_response.json'),
        )
        result = OpenMeteoProvider().get_weather(position=None, city='San Jose', country_code='CR', ip_address=None, lang_iso='en')
        self.assertAlmostEqual(result.location.lat, 9.9333)
        self.assertAlmostEqual(result.location.lon, -84.0833)

    @patch('api.providers.openmeteo.requests.get')
    def test_country_code_us_selects_california(self, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(
            forecast,
            geocoding=_load_fixture('openmeteo_geocoding_ambiguous_response.json'),
        )
        result = OpenMeteoProvider().get_weather(position=None, city='San Jose', country_code='US', ip_address=None, lang_iso='en')
        self.assertAlmostEqual(result.location.lat, 37.3382)
        self.assertAlmostEqual(result.location.lon, -121.8863)

    @patch('api.providers.openmeteo.requests.get')
    def test_unknown_country_code_raises_unavailable_error(self, mock_get):
        mock_get.side_effect = _make_requests_get_side_effect(
            {},
            geocoding=_load_fixture('openmeteo_geocoding_ambiguous_response.json'),
        )
        with self.assertRaises(WeatherServiceUnavailableError):
            OpenMeteoProvider().get_weather(position=None, city='San Jose', country_code='JP', ip_address=None, lang_iso='en')


class OpenMeteoProviderErrorTests(TestCase):

    def test_no_query_raises_value_error(self):
        with self.assertRaises(ValueError):
            OpenMeteoProvider().get_weather(position=None, city=None, country_code=None, ip_address=None, lang_iso='en')

    def test_invalid_position_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            OpenMeteoProvider().get_weather(position='not-valid', city=None, country_code=None, ip_address=None, lang_iso='en')

    @patch('api.providers.openmeteo.requests.get')
    def test_geocoding_failure_raises_unavailable_error(self, mock_get):
        mock_get.return_value = _mock_response({'results': []})
        with self.assertRaises(WeatherServiceUnavailableError):
            OpenMeteoProvider().get_weather(position=None, city='UnknownCity', country_code=None, ip_address=None, lang_iso='en')

    @patch('api.providers.openmeteo.requests.get')
    def test_geocoding_connection_error_raises_unavailable_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError
        with self.assertRaises(WeatherServiceUnavailableError):
            OpenMeteoProvider().get_weather(position=None, city='Paris', country_code=None, ip_address=None, lang_iso='en')

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_forecast_timeout_raises_unavailable_error(self, mock_ipget, mock_get):
        import requests as req

        def side_effect(url, **kwargs):
            if 'geocoding-api' in url:
                return _mock_response(_load_fixture('openmeteo_geocoding_response.json'))
            raise req.exceptions.Timeout

        mock_get.side_effect = side_effect
        with self.assertRaises(WeatherServiceUnavailableError):
            OpenMeteoProvider().get_weather(position=None, city='Paris', country_code=None, ip_address=None, lang_iso='en')


def _frozen_paris_now(_tz_id):
    import pytz
    from datetime import datetime
    return pytz.timezone('Europe/Paris').localize(datetime(2025, 6, 1, 12, 30))


# 2025-06-01 12:00 Europe/Paris (CEST, UTC+2) == 10:00 UTC
_PARIS_NOON_EPOCH = 1748772000
_UTC_MIDNIGHT_2025_06_01 = 1748736000


@patch('api.providers.openmeteo.get_time_for_timezone', side_effect=_frozen_paris_now)
@patch('api.providers.openmeteo.requests.get')
class OpenMeteoTimestampTests(TestCase):

    def _get(self, mock_get, forecast=None):
        mock_get.side_effect = _make_requests_get_side_effect(forecast or _load_fixture('openmeteo_response.json'))
        return OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

    def test_hourly_times_are_read_in_location_timezone(self, mock_get, _now):
        result = self._get(mock_get)
        # Local 12:00 must be 10:00 UTC, not 12:00 UTC (the old +2h shift).
        self.assertEqual(result.next_24h[0].timestamp, _PARIS_NOON_EPOCH)

    def test_next_24h_window_starts_at_current_local_hour(self, mock_get, _now):
        result = self._get(mock_get)
        # 12:00 today through 12:00 tomorrow, inclusive
        self.assertEqual(len(result.next_24h), 25)
        self.assertEqual(result.next_24h[-1].timestamp, _PARIS_NOON_EPOCH + 24 * 3600)

    def test_day_timestamps_stay_utc_midnight_like_weatherapi(self, mock_get, _now):
        result = self._get(mock_get)
        self.assertEqual(result.next_days[0].timestamp, _UTC_MIDNIGHT_2025_06_01)

    def test_sunrise_and_sunset_are_converted_from_local_time(self, mock_get, _now):
        result = self._get(mock_get)
        # 05:47 / 21:50 CEST
        self.assertEqual(result.next_days[0].sunrise, _UTC_MIDNIGHT_2025_06_01 + 3 * 3600 + 47 * 60)
        self.assertEqual(result.next_days[0].sunset, _UTC_MIDNIGHT_2025_06_01 + 19 * 3600 + 50 * 60)


@patch('api.providers.openmeteo.get_time_for_timezone', side_effect=_frozen_paris_now)
@patch('api.providers.openmeteo.requests.get')
class OpenMeteoV2FieldsTests(TestCase):

    def _get(self, mock_get, forecast=None):
        mock_get.side_effect = _make_requests_get_side_effect(forecast or _load_fixture('openmeteo_response.json'))
        return OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

    def test_requests_v2_variables(self, mock_get, _now):
        self._get(mock_get)
        forecast_call = next(c for c in mock_get.call_args_list if 'api.open-meteo.com' in c[0][0])
        params = forecast_call[1]['params']
        self.assertIn('precipitation_probability', params['hourly'])
        self.assertIn('sunrise', params['daily'])
        self.assertEqual(params['minutely_15'], 'precipitation')
        self.assertEqual(params['forecast_minutely_15'], 8)

    def test_current_v2_fields(self, mock_get, _now):
        current = self._get(mock_get).current
        self.assertEqual(current.humidity, 62)
        self.assertEqual(current.wind_kph, 14.4)
        self.assertEqual(current.wind_degree, 250)
        self.assertEqual(current.gust_kph, 22.3)
        self.assertEqual(current.uv, 6.0)
        self.assertEqual(current.precip_mm, 0.0)

    def test_hourly_v2_fields(self, mock_get, _now):
        forecast = _load_fixture('openmeteo_response.json')
        hour = self._get(mock_get, forecast).next_24h[0]
        i = forecast['hourly']['time'].index('2025-06-01T12:00')
        self.assertEqual(hour.chance_of_rain, forecast['hourly']['precipitation_probability'][i])
        self.assertEqual(hour.precip_mm, forecast['hourly']['precipitation'][i])
        self.assertEqual(hour.feels_like, forecast['hourly']['apparent_temperature'][i])
        self.assertEqual(hour.wind_kph, forecast['hourly']['wind_speed_10m'][i])
        self.assertEqual(hour.uv, forecast['hourly']['uv_index'][i])

    def test_chance_of_snow_is_null_rather_than_guessed(self, mock_get, _now):
        result = self._get(mock_get)
        self.assertIsNone(result.next_24h[0].chance_of_snow)
        self.assertIsNone(result.next_days[0].chance_of_snow)

    def test_daily_v2_fields(self, mock_get, _now):
        day = self._get(mock_get).next_days[1]
        self.assertEqual(day.chance_of_rain, 60)
        self.assertEqual(day.total_precip_mm, 3.2)
        self.assertEqual(day.max_wind_kph, 25.2)
        self.assertEqual(day.uv, 5.0)

    def test_null_values_in_response_are_passed_through(self, mock_get, _now):
        # Open-Meteo returns null probabilities beyond some models' horizon
        self.assertIsNone(self._get(mock_get).next_days[2].chance_of_rain)

    def test_missing_v2_variables_do_not_crash(self, mock_get, _now):
        forecast = _load_fixture('openmeteo_response.json')
        del forecast['hourly']['uv_index']
        del forecast['daily']['sunrise']
        del forecast['minutely_15']
        result = self._get(mock_get, forecast)
        self.assertIsNone(result.next_24h[0].uv)
        self.assertIsNone(result.next_days[0].sunrise)
        self.assertIsNone(result.next_minutes)

    def test_next_minutes_15_minute_steps(self, mock_get, _now):
        minutes = self._get(mock_get).next_minutes
        self.assertEqual(len(minutes), 8)
        self.assertEqual(minutes[0].timestamp, _PARIS_NOON_EPOCH)
        self.assertEqual(minutes[1].timestamp - minutes[0].timestamp, 900)
        self.assertEqual(minutes[3].precip_mm, 0.4)

    def test_alerts_are_null_because_unsupported(self, mock_get, _now):
        self.assertIsNone(self._get(mock_get).alerts)

    def test_forecast_days_follows_env(self, mock_get, _now):
        with patch.dict('os.environ', {'WEATHER_FORECAST_DAYS': '7'}):
            self._get(mock_get)
        forecast_call = next(c for c in mock_get.call_args_list if 'api.open-meteo.com' in c[0][0])
        self.assertEqual(forecast_call[1]['params']['forecast_days'], 7)


@patch('api.providers.openmeteo.get_time_for_timezone', side_effect=_frozen_paris_now)
@patch('api.providers.openmeteo.requests.get')
class OpenMeteoSkyAndSnowTests(TestCase):

    def _get(self, mock_get, forecast=None):
        mock_get.side_effect = _make_requests_get_side_effect(forecast or _load_fixture('openmeteo_response.json'))
        return OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

    def test_current_cloud_cover_and_visibility_in_km(self, mock_get, _now):
        current = self._get(mock_get).current
        self.assertEqual(current.cloud_cover, 25)
        self.assertEqual(current.visibility_km, 24.14)

    def test_hourly_cloud_visibility_snow(self, mock_get, _now):
        forecast = _load_fixture('openmeteo_response.json')
        forecast['hourly']['snowfall'] = [1.4] * len(forecast['hourly']['time'])
        hour = self._get(mock_get, forecast).next_24h[0]
        i = forecast['hourly']['time'].index('2025-06-01T12:00')
        self.assertEqual(hour.cloud_cover, forecast['hourly']['cloud_cover'][i])
        self.assertEqual(hour.visibility_km, forecast['hourly']['visibility'][i] / 1000)
        self.assertEqual(hour.snow_cm, 1.4)

    def test_fog_visibility_is_kept_precise(self, mock_get, _now):
        forecast = _load_fixture('openmeteo_response.json')
        i = forecast['hourly']['time'].index('2025-06-01T12:00')
        forecast['hourly']['visibility'][i] = 350.0
        self.assertEqual(self._get(mock_get, forecast).next_24h[0].visibility_km, 0.35)

    def test_daily_total_snow(self, mock_get, _now):
        self.assertEqual(self._get(mock_get).next_days[2].total_snow_cm, 3.5)


def _with_yesterday(forecast):
    """Prepend 2025-05-31 to the fixture, as Open-Meteo does with past_days=1."""
    h, d = forecast['hourly'], forecast['daily']
    past_hours = [f'2025-05-31T{i:02d}:00' for i in range(24)]
    for key, values in h.items():
        if key == 'time':
            h[key] = past_hours + values
        elif key == 'temperature_2m':
            h[key] = [10.0 + i * 0.5 for i in range(24)] + values  # 12:00 -> 16.0
        else:
            h[key] = values[:24] + values
    yesterday_daily = {
        'time': '2025-05-31', 'weather_code': 61, 'temperature_2m_max': 15.0, 'temperature_2m_min': 8.0,
    }
    for key, values in d.items():
        d[key] = [yesterday_daily.get(key, values[0])] + values
    return forecast


@patch('api.providers.openmeteo.get_time_for_timezone', side_effect=_frozen_paris_now)
@patch('api.providers.openmeteo.requests.get')
class OpenMeteoYesterdayTests(TestCase):

    def _get(self, mock_get, forecast):
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        return OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

    def test_requests_past_day(self, mock_get, _now):
        self._get(mock_get, _with_yesterday(_load_fixture('openmeteo_response.json')))
        forecast_call = next(c for c in mock_get.call_args_list if 'api.open-meteo.com' in c[0][0])
        self.assertEqual(forecast_call[1]['params']['past_days'], 1)

    def test_yesterday_block(self, mock_get, _now):
        yesterday = self._get(mock_get, _with_yesterday(_load_fixture('openmeteo_response.json'))).yesterday
        self.assertEqual(yesterday.min_temp, 8.0)
        self.assertEqual(yesterday.max_temp, 15.0)
        self.assertEqual(yesterday.temp_same_hour, 16.0)  # 2025-05-31T12:00
        self.assertEqual(yesterday.condition.code, get_condition_code_for_wmo(61))

    def test_yesterday_does_not_leak_into_today(self, mock_get, _now):
        plain = self._get(mock_get, _load_fixture('openmeteo_response.json'))
        shifted = self._get(mock_get, _with_yesterday(_load_fixture('openmeteo_response.json')))
        self.assertEqual(shifted.current.min_temp, plain.current.min_temp)
        self.assertEqual(shifted.current.max_temp, plain.current.max_temp)
        self.assertEqual(len(shifted.next_days), 3)
        self.assertEqual(shifted.next_days[0].timestamp, _UTC_MIDNIGHT_2025_06_01)
        self.assertEqual([h.timestamp for h in shifted.next_24h], [h.timestamp for h in plain.next_24h])

    def test_no_past_day_gives_null(self, mock_get, _now):
        self.assertIsNone(self._get(mock_get, _load_fixture('openmeteo_response.json')).yesterday)


def get_condition_code_for_wmo(wmo):
    from api.utils.conditions import get_condition_by_wmo_code
    return get_condition_by_wmo_code(wmo).code


class OpenMeteoCityGeocodingTests(TestCase):

    @patch('api.providers.openmeteo.requests.get')
    def test_country_code_is_sent_to_geocoding(self, mock_get):
        mock_get.side_effect = _make_requests_get_side_effect(
            _load_fixture('openmeteo_response.json'),
            geocoding=_load_fixture('openmeteo_geocoding_ambiguous_response.json'),
        )
        OpenMeteoProvider().get_weather(position=None, city='San Jose', country_code='cr', ip_address=None, lang_iso='en')
        geo_call = next(c for c in mock_get.call_args_list if 'geocoding-api' in c[0][0])
        self.assertEqual(geo_call[1]['params']['countryCode'], 'CR')

    @patch('api.providers.openmeteo.requests.get')
    def test_geocoding_http_error_raises_unavailable(self, mock_get):
        mock_get.return_value = _mock_response({}, status_code=500)
        with self.assertRaises(WeatherServiceUnavailableError):
            OpenMeteoProvider().get_weather(position=None, city='Paris', country_code=None, ip_address=None, lang_iso='en')
