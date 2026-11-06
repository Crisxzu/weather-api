from unittest.mock import MagicMock, patch

from django.test import TestCase

from api.providers.base import WeatherServiceUnavailableError
from api.utils.conditions import get_condition_by_code, get_condition_by_wmo_code
from api.utils.ip_geolocation import resolve_ip


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
        self.assertEqual(result.code, 1000)
        self.assertEqual(result.icon, 113)

    def test_unknown_wmo_code_returns_clear_fallback(self):
        result = get_condition_by_wmo_code(42)
        self.assertEqual(result.code, 1000)
        self.assertEqual(result.icon, 113)


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
        self.assertEqual(result.lat, 48.8566)
        self.assertEqual(result.lon, 2.3522)
        self.assertEqual(result.city, 'Paris')
        self.assertEqual(result.country, 'France')
        self.assertEqual(result.timezone, 'Europe/Paris')

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


class ConditionLanguageAliasTests(TestCase):

    def test_new_condition_codes_are_known(self):
        self.assertEqual(get_condition_by_code(1036, is_day=True, lang_iso='fr'), 'Brume de fumée')

    def test_legacy_chinese_code_still_translated(self):
        # conditions.json renamed zh -> zh_cn; clients may still send zh
        self.assertEqual(
            get_condition_by_code(1000, is_day=True, lang_iso='zh'),
            get_condition_by_code(1000, is_day=True, lang_iso='zh_cn'),
        )
        self.assertNotEqual(get_condition_by_code(1000, is_day=True, lang_iso='zh'), 'Sunny')

    def test_legacy_dialect_codes_still_translated(self):
        for legacy in ('zh_hsn', 'zh_wuu', 'zh_yue'):
            self.assertNotEqual(get_condition_by_code(1000, is_day=True, lang_iso=legacy), 'Sunny', legacy)

    def test_lang_code_is_normalized(self):
        self.assertEqual(
            get_condition_by_code(1000, is_day=True, lang_iso='zh-TW'),
            get_condition_by_code(1000, is_day=True, lang_iso='zh_tw'),
        )


class ConditionsReloadTests(TestCase):

    def _store(self, tmp_path, data):
        import json
        from api.utils.conditions import _ConditionsStore
        path = tmp_path / 'conditions.json'
        path.write_text(json.dumps(data))
        return path, _ConditionsStore(path)

    def setUp(self):
        import tempfile
        from pathlib import Path
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _entry(self, code, day):
        return {'code': code, 'day': day, 'night': day, 'icon': 113, 'languages': []}

    @patch('api.utils.conditions._RELOAD_CHECK_SECONDS', 0)
    def test_reloads_when_file_changes(self):
        import json
        import os
        path, store = self._store(self.tmp_path, [self._entry(1000, 'Sunny')])
        self.assertIsNone(store.get(1036))

        path.write_text(json.dumps([self._entry(1000, 'Sunny'), self._entry(1036, 'Smoky haze')]))
        os.utime(path, (1, 2_000_000_000))  # force a different mtime
        self.assertEqual(store.get(1036)['day'], 'Smoky haze')

    @patch('api.utils.conditions._RELOAD_CHECK_SECONDS', 0)
    def test_keeps_previous_version_if_new_file_is_broken(self):
        import os
        path, store = self._store(self.tmp_path, [self._entry(1000, 'Sunny')])
        path.write_text('{not json')
        os.utime(path, (1, 2_000_000_000))
        with self.assertLogs('api.utils.conditions', level='ERROR'):
            self.assertEqual(store.get(1000)['day'], 'Sunny')

    @patch('api.utils.conditions._RELOAD_CHECK_SECONDS', 3600)
    def test_does_not_stat_on_every_call(self):
        path, store = self._store(self.tmp_path, [self._entry(1000, 'Sunny')])
        store.get(1000)
        with patch('api.utils.conditions.os.stat') as mock_stat:
            store.get(1000)
        mock_stat.assert_not_called()


class ForecastDaysTests(TestCase):

    def test_defaults_to_seven_days(self):
        import os
        from api.providers.base import get_forecast_days
        with patch.dict('os.environ', {}, clear=False):
            os.environ.pop('WEATHER_FORECAST_DAYS', None)
            self.assertEqual(get_forecast_days(), 7)

    def test_env_overrides_default(self):
        from api.providers.base import get_forecast_days
        with patch.dict('os.environ', {'WEATHER_FORECAST_DAYS': '3'}):
            self.assertEqual(get_forecast_days(), 3)

    def test_invalid_value_falls_back_to_default(self):
        from api.providers.base import get_forecast_days
        with patch.dict('os.environ', {'WEATHER_FORECAST_DAYS': 'abc'}):
            self.assertEqual(get_forecast_days(), 7)

    def test_clamped_to_provider_limits(self):
        from api.providers.base import get_forecast_days
        with patch.dict('os.environ', {'WEATHER_FORECAST_DAYS': '30'}):
            self.assertEqual(get_forecast_days(), 16)
        with patch.dict('os.environ', {'WEATHER_FORECAST_DAYS': '0'}):
            self.assertEqual(get_forecast_days(), 1)
