from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase

from api.providers.air_quality import get_air_quality

_VARS = ['european_aqi', 'us_aqi', 'pm2_5', 'pm10', 'ozone', 'nitrogen_dioxide',
         'alder_pollen', 'birch_pollen', 'grass_pollen', 'mugwort_pollen', 'olive_pollen', 'ragweed_pollen']
_UTC_MIDNIGHT_2025_06_01 = 1748736000


def _raw(pollen=True):
    """72 hourly values from 2025-06-01 00:00 local; value = hour index for every variable."""
    times = [f'2025-06-{1 + i // 24:02d}T{i % 24:02d}:00' for i in range(72)]
    hourly = {'time': times}
    for var in _VARS:
        hourly[var] = [float(i) if (pollen or 'pollen' not in var) else None for i in range(72)]
    hourly['european_aqi'][5] = None  # gaps must be ignored
    current = {'time': '2025-06-01T12:00', 'interval': 3600}
    current.update({var: (7.0 if (pollen or 'pollen' not in var) else None) for var in _VARS})
    return {'timezone': 'Europe/Paris', 'current': current, 'hourly': hourly}


def _response(data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    return mock


@patch.dict('os.environ', {'WEATHER_AIR_QUALITY_PROVIDER': 'openmeteo', 'WEATHER_FORECAST_DAYS': '3'})
@patch('api.providers.air_quality.requests.get')
class GetAirQualityTests(TestCase):

    def setUp(self):
        cache.clear()

    def test_requests_rounded_position_and_variables(self, mock_get):
        mock_get.return_value = _response(_raw())
        get_air_quality(48.8566, 2.3522)
        params = mock_get.call_args[1]['params']
        self.assertTrue(mock_get.call_args[0][0].startswith('https://air-quality-api.open-meteo.com'))
        self.assertEqual((params['latitude'], params['longitude']), ('48.86', '2.35'))
        self.assertIn('birch_pollen', params['hourly'])
        self.assertEqual(params['forecast_days'], 3)

    def test_current_values(self, mock_get):
        mock_get.return_value = _response(_raw())
        current = get_air_quality(48.86, 2.35).current
        self.assertEqual(current.european_aqi, 7.0)
        self.assertEqual(current.pm2_5, 7.0)
        self.assertEqual(current.pollen.birch, 7.0)

    def test_days_are_daily_maxima_from_today(self, mock_get):
        mock_get.return_value = _response(_raw())
        days = get_air_quality(48.86, 2.35).days
        self.assertEqual(len(days), 3)
        self.assertEqual(days[0].timestamp, _UTC_MIDNIGHT_2025_06_01)
        self.assertEqual(days[1].timestamp, _UTC_MIDNIGHT_2025_06_01 + 86400)
        self.assertEqual(days[0].european_aqi, 23.0)  # max of hours 0..23
        self.assertEqual(days[1].pollen.grass, 47.0)

    def test_days_capped_by_forecast_days(self, mock_get):
        mock_get.return_value = _response(_raw())
        with patch.dict('os.environ', {'WEATHER_FORECAST_DAYS': '2'}):
            self.assertEqual(len(get_air_quality(48.86, 2.35).days), 2)

    def test_pollen_null_outside_coverage(self, mock_get):
        mock_get.return_value = _response(_raw(pollen=False))
        result = get_air_quality(40.71, -74.0)
        self.assertIsNone(result.current.pollen)
        self.assertIsNone(result.days[0].pollen)
        self.assertEqual(result.current.us_aqi, 7.0)

    def test_zero_pollen_is_kept(self, mock_get):
        raw = _raw()
        for var in _VARS:
            if 'pollen' in var:
                raw['current'][var] = 0.0
        mock_get.return_value = _response(raw)
        self.assertEqual(get_air_quality(48.86, 2.35).current.pollen.birch, 0.0)

    def test_cached_per_cell_and_rebuilt_as_dataclasses(self, mock_get):
        mock_get.return_value = _response(_raw())
        get_air_quality(48.86, 2.35)
        result = get_air_quality(48.8601, 2.3499)
        mock_get.assert_called_once()
        self.assertEqual(result.current.pollen.birch, 7.0)
        self.assertEqual(result.days[1].pollen.grass, 47.0)

    def test_cached_null_pollen(self, mock_get):
        mock_get.return_value = _response(_raw(pollen=False))
        get_air_quality(40.71, -74.0)
        self.assertIsNone(get_air_quality(40.71, -74.0).current.pollen)

    def test_http_error_gives_null_and_is_not_cached(self, mock_get):
        mock_get.return_value = _response({}, status_code=429)
        self.assertIsNone(get_air_quality(48.86, 2.35))
        get_air_quality(48.86, 2.35)
        self.assertEqual(mock_get.call_count, 2)

    def test_network_error_gives_null(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout
        self.assertIsNone(get_air_quality(48.86, 2.35))

    def test_malformed_response_gives_null(self, mock_get):
        mock_get.return_value = _response({'unexpected': True})
        with self.assertLogs('api.providers.air_quality', level='WARNING'):
            self.assertIsNone(get_air_quality(48.86, 2.35))

    def test_disabled_when_env_is_empty(self, mock_get):
        with patch.dict('os.environ', {'WEATHER_AIR_QUALITY_PROVIDER': ''}):
            self.assertIsNone(get_air_quality(48.86, 2.35))
        mock_get.assert_not_called()

    def test_unknown_provider_disables(self, mock_get):
        with patch.dict('os.environ', {'WEATHER_AIR_QUALITY_PROVIDER': 'weatherapi'}):
            self.assertIsNone(get_air_quality(48.86, 2.35))
        mock_get.assert_not_called()
