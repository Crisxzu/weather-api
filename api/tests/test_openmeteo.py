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
        result = provider.get_weather(position='48.8566,2.3522', city=None, ip_address=None, lang_iso='en')

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
        result = OpenMeteoProvider().get_weather(position=None, city='Paris', ip_address=None, lang_iso='en')
        self.assertIsInstance(result, WeatherData)

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_ip_query_resolves_coordinates_then_fetches(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        mock_ipget.return_value = _mock_response(_load_fixture('ipapi_response.json'))
        result = OpenMeteoProvider().get_weather(position=None, city=None, ip_address='81.2.69.142', lang_iso='en')
        self.assertIsInstance(result, WeatherData)
        # Location metadata comes from ip-api, not Nominatim
        self.assertEqual(result.location.name, 'Paris')
        self.assertEqual(result.location.country, 'France')

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_condition_text_is_localized(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, ip_address=None, lang_iso='fr')
        self.assertIsNotNone(result.current.condition.text)

    @patch('api.providers.openmeteo.requests.get')
    @patch('api.utils.ip_geolocation.requests.get')
    def test_next_days_has_three_entries(self, mock_ipget, mock_get):
        forecast = _load_fixture('openmeteo_response.json')
        mock_get.side_effect = _make_requests_get_side_effect(forecast)
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, ip_address=None, lang_iso='en')
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
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, ip_address=None, lang_iso='en')
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
        result = OpenMeteoProvider().get_weather(position='48.8566,2.3522', city=None, ip_address=None, lang_iso='en')
        self.assertIsInstance(result, WeatherData)
        self.assertIn('48.8566', result.location.name)


class OpenMeteoProviderErrorTests(TestCase):

    def test_no_query_raises_value_error(self):
        with self.assertRaises(ValueError):
            OpenMeteoProvider().get_weather(position=None, city=None, ip_address=None, lang_iso='en')

    def test_invalid_position_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            OpenMeteoProvider().get_weather(position='not-valid', city=None, ip_address=None, lang_iso='en')

    @patch('api.providers.openmeteo.requests.get')
    def test_geocoding_failure_raises_unavailable_error(self, mock_get):
        mock_get.return_value = _mock_response({'results': []})
        with self.assertRaises(WeatherServiceUnavailableError):
            OpenMeteoProvider().get_weather(position=None, city='UnknownCity', ip_address=None, lang_iso='en')

    @patch('api.providers.openmeteo.requests.get')
    def test_geocoding_connection_error_raises_unavailable_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError
        with self.assertRaises(WeatherServiceUnavailableError):
            OpenMeteoProvider().get_weather(position=None, city='Paris', ip_address=None, lang_iso='en')

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
            OpenMeteoProvider().get_weather(position=None, city='Paris', ip_address=None, lang_iso='en')
