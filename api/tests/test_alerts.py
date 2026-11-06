import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase

from api.providers.alerts import get_alerts

_FIXTURES = Path(__file__).parent / 'fixtures'

_ENV = {
    'WEATHER_API_KEY': 'test-key',
    'WEATHER_API_BASE_URL': 'http://api.weatherapi.com/v1',
    'WEATHER_ALERTS_PROVIDER': 'weatherapi',
}


def _alerts_response(alerts, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = {'location': {}, 'alerts': {'alert': alerts}}
    return mock


def _fixture_alerts():
    with open(_FIXTURES / 'weatherapi_response.json') as f:
        return json.load(f)['alerts']['alert']


@patch.dict('os.environ', _ENV)
@patch('api.providers.alerts.requests.get')
class GetAlertsTests(TestCase):

    def setUp(self):
        cache.clear()

    def test_calls_alerts_endpoint_with_rounded_position(self, mock_get):
        mock_get.return_value = _alerts_response([])
        get_alerts(48.8566, 2.3522)
        url = mock_get.call_args[0][0]
        params = mock_get.call_args[1]['params']
        self.assertTrue(url.endswith('/alerts.json'))
        self.assertEqual(params['q'], '48.86,2.35')

    def test_maps_alerts(self, mock_get):
        mock_get.return_value = _alerts_response(_fixture_alerts())
        alerts = get_alerts(48.86, 2.35)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].event, 'Thunderstorm warning')
        self.assertEqual(alerts[0].effective, 1748736000 + 12 * 3600)

    def test_no_alert_gives_empty_list(self, mock_get):
        mock_get.return_value = _alerts_response([])
        self.assertEqual(get_alerts(48.86, 2.35), [])

    def test_results_are_cached_including_empty_list(self, mock_get):
        mock_get.return_value = _alerts_response([])
        get_alerts(48.86, 2.35)
        get_alerts(48.8601, 2.3499)  # same ~1 km cell
        mock_get.assert_called_once()

    def test_cached_alerts_are_returned_as_dataclasses(self, mock_get):
        mock_get.return_value = _alerts_response(_fixture_alerts())
        get_alerts(48.86, 2.35)
        alerts = get_alerts(48.86, 2.35)
        self.assertEqual(alerts[0].headline, 'Orages violents')

    def test_http_error_gives_null_and_is_not_cached(self, mock_get):
        mock_get.return_value = _alerts_response([], status_code=403)
        self.assertIsNone(get_alerts(48.86, 2.35))
        get_alerts(48.86, 2.35)
        self.assertEqual(mock_get.call_count, 2)

    def test_network_error_gives_null(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout
        self.assertIsNone(get_alerts(48.86, 2.35))

    def test_disabled_when_env_is_empty(self, mock_get):
        with patch.dict('os.environ', {'WEATHER_ALERTS_PROVIDER': ''}):
            self.assertIsNone(get_alerts(48.86, 2.35))
        mock_get.assert_not_called()

    def test_disabled_without_api_key(self, mock_get):
        with patch.dict('os.environ', {'WEATHER_API_KEY': ''}):
            self.assertIsNone(get_alerts(48.86, 2.35))
        mock_get.assert_not_called()

    def test_unknown_provider_disables_alerts(self, mock_get):
        with patch.dict('os.environ', {'WEATHER_ALERTS_PROVIDER': 'meteofrance'}):
            self.assertIsNone(get_alerts(48.86, 2.35))
        mock_get.assert_not_called()
