from unittest.mock import MagicMock, patch

from django.test import TestCase

from api.utils.conditions import get_condition_by_code, get_condition_by_wmo_code
from api.utils.ip_geolocation import resolve_ip
from api.providers.base import WeatherServiceUnavailableError


class GetConditionByCodeTests(TestCase):

    def test_returns_english_day_text_by_default(self):
        result = get_condition_by_code(1000, is_day=True)
        self.assertEqual(result, 'Sunny')

    def test_returns_english_night_text_by_default(self):
        result = get_condition_by_code(1000, is_day=False)
        self.assertEqual(result, 'Clear')

    def test_returns_translated_text_for_known_lang(self):
        result = get_condition_by_code(1000, is_day=True, lang_iso='fr')
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, '')

    def test_falls_back_to_english_for_unknown_lang(self):
        result = get_condition_by_code(1000, is_day=True, lang_iso='xx')
        self.assertEqual(result, 'Sunny')

    def test_returns_none_for_unknown_code(self):
        result = get_condition_by_code(9999, is_day=True)
        self.assertIsNone(result)


class GetConditionByWmoCodeTests(TestCase):

    def test_known_wmo_code_returns_mapped_entry(self):
        result = get_condition_by_wmo_code(0)
        self.assertIn('code', result)
        self.assertIn('icon', result)
        self.assertEqual(result['code'], 1000)
        self.assertEqual(result['icon'], 113)

    def test_rain_code_maps_correctly(self):
        result = get_condition_by_wmo_code(61)
        self.assertEqual(result['code'], 1183)

    def test_unknown_wmo_code_returns_clear_fallback(self):
        result = get_condition_by_wmo_code(42)
        self.assertEqual(result['code'], 1000)
        self.assertEqual(result['icon'], 113)


class ResolveIpTests(TestCase):

    def _mock_response(self, data, status_code=200):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = data
        return mock

    def test_private_ip_raises_value_error(self):
        with self.assertRaises(ValueError):
            resolve_ip('192.168.1.1')

    def test_loopback_ip_raises_value_error(self):
        with self.assertRaises(ValueError):
            resolve_ip('127.0.0.1')

    @patch('api.utils.ip_geolocation.requests.get')
    def test_valid_ip_returns_location_data(self, mock_get):
        mock_get.return_value = self._mock_response({
            'status': 'success',
            'lat': 48.8566,
            'lon': 2.3522,
            'city': 'Paris',
            'regionName': 'Ile-de-France',
            'country': 'France',
            'timezone': 'Europe/Paris',
        })
        result = resolve_ip('81.2.69.142')
        self.assertEqual(result['lat'], 48.8566)
        self.assertEqual(result['lon'], 2.3522)
        self.assertEqual(result['city'], 'Paris')
        self.assertEqual(result['country'], 'France')
        self.assertEqual(result['timezone'], 'Europe/Paris')

    @patch('api.utils.ip_geolocation.requests.get')
    def test_failed_api_status_raises_value_error(self, mock_get):
        mock_get.return_value = self._mock_response({'status': 'fail'})
        with self.assertRaises(ValueError):
            resolve_ip('81.2.69.142')

    @patch('api.utils.ip_geolocation.requests.get')
    def test_connection_error_raises_unavailable(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError
        with self.assertRaises(WeatherServiceUnavailableError):
            resolve_ip('81.2.69.142')

    @patch('api.utils.ip_geolocation.requests.get')
    def test_timeout_raises_unavailable(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout
        with self.assertRaises(WeatherServiceUnavailableError):
            resolve_ip('81.2.69.142')
