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
