import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase

from api.providers.base import WeatherServiceError, WeatherServiceUnavailableError
from api.providers.schemas import WeatherData
from api.providers.weatherapi import WeatherAPIProvider

_FIXTURES = Path(__file__).parent / 'fixtures'


def _load_fixture(name):
    with open(_FIXTURES / name) as f:
        return json.load(f)


def _mock_response(data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    return mock


class WeatherAPIProviderHappyPathTests(TestCase):

    @patch('api.providers.weatherapi.requests.get')
    def test_returns_weather_data_for_position(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        provider = WeatherAPIProvider()
        result = provider.get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

        self.assertIsInstance(result, WeatherData)
        self.assertEqual(result.location.name, 'Paris')
        self.assertEqual(result.location.country, 'France')
        self.assertEqual(result.current.temp, 18.0)
        self.assertEqual(result.current.feels_like, 17.2)
        self.assertTrue(result.current.is_day)
        self.assertEqual(result.current.condition.code, 1000)
        self.assertEqual(result.current.condition.icon, 113)

    @patch('api.providers.weatherapi.requests.get')
    def test_returns_weather_data_for_city(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        provider = WeatherAPIProvider()
        result = provider.get_weather(position=None, city='Paris', country_code=None, ip_address=None, lang_iso='en')
        self.assertIsInstance(result, WeatherData)

    @patch('api.providers.weatherapi.requests.get')
    def test_city_with_country_code_sends_combined_query(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        WeatherAPIProvider().get_weather(position=None, city='Fes', country_code='MA', ip_address=None, lang_iso='en')
        called_params = mock_get.call_args[1]['params']
        self.assertEqual(called_params['q'], 'Fes,MA')

    @patch('api.providers.weatherapi.requests.get')
    def test_city_without_country_code_sends_city_only(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        WeatherAPIProvider().get_weather(position=None, city='Fes', country_code=None, ip_address=None, lang_iso='en')
        called_params = mock_get.call_args[1]['params']
        self.assertEqual(called_params['q'], 'Fes')

    @patch('api.providers.weatherapi.requests.get')
    def test_returns_weather_data_for_ip(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        provider = WeatherAPIProvider()
        result = provider.get_weather(position=None, city=None, country_code=None, ip_address='81.2.69.142', lang_iso='en')
        self.assertIsInstance(result, WeatherData)

    @patch('api.providers.weatherapi.requests.get')
    def test_next_days_has_three_entries(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        result = WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertEqual(len(result.next_days), 3)

    @patch('api.providers.weatherapi.requests.get')
    def test_condition_text_localized_in_french(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        result = WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='fr')
        self.assertIsNotNone(result.current.condition.text)
        self.assertNotEqual(result.current.condition.text, 'Sunny')

    @patch('api.providers.weatherapi.requests.get')
    def test_source_name_from_env(self, mock_get):
        mock_get.return_value = _mock_response(_load_fixture('weatherapi_response.json'))
        result = WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertIsNotNone(result.source)
        self.assertIsNotNone(result.source_link)


class WeatherAPIProviderErrorTests(TestCase):

    def test_no_query_raises_value_error(self):
        with self.assertRaises(ValueError):
            WeatherAPIProvider().get_weather(position=None, city=None, country_code=None, ip_address=None, lang_iso='en')

    def test_invalid_position_format_falls_through_to_value_error(self):
        with self.assertRaises(ValueError):
            WeatherAPIProvider().get_weather(position='not-a-position', city=None, country_code=None, ip_address=None, lang_iso='en')

    @patch('api.providers.weatherapi.requests.get')
    def test_timeout_raises_unavailable_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout
        with self.assertRaises(WeatherServiceUnavailableError):
            WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

    @patch('api.providers.weatherapi.requests.get')
    def test_connection_error_raises_unavailable_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError
        with self.assertRaises(WeatherServiceUnavailableError):
            WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

    @patch('api.providers.weatherapi.requests.get')
    def test_quota_exceeded_raises_service_error(self, mock_get):
        mock_get.return_value = _mock_response({'error': {'code': 2007}}, status_code=403)
        with self.assertRaises(WeatherServiceError) as ctx:
            WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertEqual(ctx.exception.error_code, 2007)

    @patch('api.providers.weatherapi.requests.get')
    def test_location_not_found_raises_service_error(self, mock_get):
        mock_get.return_value = _mock_response({'error': {'code': 1006}}, status_code=400)
        with self.assertRaises(WeatherServiceError) as ctx:
            WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertEqual(ctx.exception.error_code, 1006)

    @patch('api.providers.weatherapi.requests.get')
    def test_invalid_api_key_raises_service_error(self, mock_get):
        mock_get.return_value = _mock_response({'error': {'code': 2006}}, status_code=403)
        with self.assertRaises(WeatherServiceError) as ctx:
            WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')
        self.assertEqual(ctx.exception.error_code, 2006)


# 2025-06-01 00:00 UTC; Paris is UTC+2 in June
_UTC_MIDNIGHT_2025_06_01 = 1748736000


class WeatherAPIProviderV2FieldsTests(TestCase):

    def _get(self, mock_get, data=None):
        mock_get.return_value = _mock_response(data or _load_fixture('weatherapi_response.json'))
        return WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='en')

    @patch('api.providers.weatherapi.requests.get')
    def test_requests_alerts(self, mock_get):
        self._get(mock_get)
        self.assertEqual(mock_get.call_args[1]['params']['alerts'], 'yes')

    @patch('api.providers.weatherapi.requests.get')
    def test_forecast_days_follows_env(self, mock_get):
        with patch.dict('os.environ', {'WEATHER_FORECAST_DAYS': '7'}):
            self._get(mock_get)
        self.assertEqual(mock_get.call_args[1]['params']['days'], 7)

    @patch('api.providers.weatherapi.requests.get')
    def test_current_v2_fields(self, mock_get):
        current = self._get(mock_get).current
        self.assertEqual(current.humidity, 62)
        self.assertEqual(current.wind_kph, 14.4)
        self.assertEqual(current.wind_degree, 250)
        self.assertEqual(current.gust_kph, 22.3)
        self.assertEqual(current.uv, 6.0)
        self.assertEqual(current.precip_mm, 0.0)

    @patch('api.providers.weatherapi.requests.get')
    @patch('api.providers.weatherapi.get_time_for_timezone')
    def test_hourly_v2_fields(self, mock_now, mock_get):
        import pytz
        from datetime import datetime
        mock_now.return_value = pytz.timezone('Europe/Paris').localize(datetime(2025, 6, 1, 0, 0))
        hours = self._get(mock_get).next_24h
        self.assertEqual(hours[1].chance_of_rain, 20)
        self.assertEqual(hours[1].chance_of_snow, 0)
        self.assertEqual(hours[1].precip_mm, 0.1)
        self.assertEqual(hours[1].feels_like, 17.5)
        self.assertEqual(hours[1].wind_kph, 13.0)
        self.assertEqual(hours[1].uv, 6.0)

    @patch('api.providers.weatherapi.requests.get')
    def test_daily_v2_fields(self, mock_get):
        day = self._get(mock_get).next_days[2]
        self.assertEqual(day.chance_of_rain, 80)
        self.assertEqual(day.chance_of_snow, 10)
        self.assertEqual(day.total_precip_mm, 6.5)
        self.assertEqual(day.max_wind_kph, 30.0)
        self.assertEqual(day.uv, 3.0)

    @patch('api.providers.weatherapi.requests.get')
    def test_sunrise_sunset_converted_with_location_timezone(self, mock_get):
        day = self._get(mock_get).next_days[0]
        # 05:47 AM / 09:50 PM CEST — same instants Open-Meteo yields for its fixture
        self.assertEqual(day.sunrise, _UTC_MIDNIGHT_2025_06_01 + 3 * 3600 + 47 * 60)
        self.assertEqual(day.sunset, _UTC_MIDNIGHT_2025_06_01 + 19 * 3600 + 50 * 60)

    @patch('api.providers.weatherapi.requests.get')
    def test_polar_no_sunrise_gives_null(self, mock_get):
        day = self._get(mock_get).next_days[2]
        self.assertIsNone(day.sunrise)
        self.assertIsNone(day.sunset)

    @patch('api.providers.weatherapi.requests.get')
    def test_alerts_are_mapped(self, mock_get):
        alerts = self._get(mock_get).alerts
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].event, 'Thunderstorm warning')
        self.assertEqual(alerts[0].headline, 'Orages violents')
        self.assertEqual(alerts[0].severity, 'Moderate')
        self.assertEqual(alerts[0].effective, _UTC_MIDNIGHT_2025_06_01 + 12 * 3600)
        self.assertEqual(alerts[0].expires, _UTC_MIDNIGHT_2025_06_01 + 20 * 3600)

    @patch('api.providers.weatherapi.requests.get')
    def test_no_alert_gives_empty_list(self, mock_get):
        data = _load_fixture('weatherapi_response.json')
        data['alerts'] = {'alert': []}
        self.assertEqual(self._get(mock_get, data).alerts, [])

    @patch('api.providers.weatherapi.requests.get')
    def test_missing_alerts_block_gives_null(self, mock_get):
        data = _load_fixture('weatherapi_response.json')
        del data['alerts']
        self.assertIsNone(self._get(mock_get, data).alerts)

    @patch('api.providers.weatherapi.requests.get')
    def test_next_minutes_is_null(self, mock_get):
        self.assertIsNone(self._get(mock_get).next_minutes)

    @patch('api.providers.weatherapi.requests.get')
    def test_missing_v2_fields_do_not_crash(self, mock_get):
        data = _load_fixture('weatherapi_response.json')
        del data['current']['uv']
        del data['forecast']['forecastday'][0]['astro']
        result = self._get(mock_get, data)
        self.assertIsNone(result.current.uv)
        self.assertIsNone(result.next_days[0].sunrise)


class WeatherAPIProviderUnknownConditionTests(TestCase):

    @patch('api.providers.weatherapi.requests.get')
    def test_unknown_condition_code_falls_back_to_provider_text(self, mock_get):
        data = _load_fixture('weatherapi_response.json')
        data['current']['condition'] = {
            'text': 'Smoky haze', 'icon': '//cdn.weatherapi.com/weather/64x64/night/143.png', 'code': 1036,
        }
        mock_get.return_value = _mock_response(data)
        result = WeatherAPIProvider().get_weather(position='48.8566,2.3522', city=None, country_code=None, ip_address=None, lang_iso='fr')
        self.assertEqual(result.current.condition.code, 1036)
        self.assertEqual(result.current.condition.text, 'Smoky haze')
        self.assertEqual(result.current.condition.icon, 143)
