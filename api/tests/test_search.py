from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework_api_key.models import APIKey

_PARIS = {
    'id': 2988507, 'name': 'Paris', 'latitude': 48.85341, 'longitude': 2.3488, 'country_code': 'FR',
    'country': 'France', 'admin1': 'Île-de-France', 'population': 2138551, 'timezone': 'Europe/Paris',
}
_PARIS_TX = {
    'id': 4717560, 'name': 'Paris', 'latitude': 33.66094, 'longitude': -95.55551, 'country_code': 'US',
    'country': 'United States', 'admin1': 'Texas', 'population': 24782, 'timezone': 'America/Chicago',
}
_NO_ADMIN = {  # some places have no admin1 / population
    'id': 1, 'name': 'Somewhere', 'latitude': 1.0, 'longitude': 2.0, 'country_code': 'xx',
    'country': 'Nowhere', 'timezone': 'UTC',
}


def _response(results, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = {'results': results, 'generationtime_ms': 0.5} if results is not None else {'generationtime_ms': 0.5}
    return mock


@patch('api.utils.geocoding.requests.get')
class CitySearchViewTests(TestCase):

    def setUp(self):
        cache.clear()
        _, key = APIKey.objects.create_key(name='test-key')
        self.auth = {'HTTP_AUTHORIZATION': f'Api-Key {key}'}
        self.url = reverse('api:search')

    def _get(self, params, auth=True):
        return self.client.get(self.url, params, **(self.auth if auth else {}))

    def test_requires_api_key(self, mock_get):
        self.assertEqual(self._get({'q': 'Paris'}, auth=False).status_code, 403)
        mock_get.assert_not_called()

    def test_returns_cities_in_open_meteo_order(self, mock_get):
        mock_get.return_value = _response([_PARIS, _PARIS_TX])
        data = self._get({'q': 'Paris', 'lang_iso': 'fr'}).json()
        self.assertEqual([c['id'] for c in data], [2988507, 4717560])
        self.assertEqual(data[0], {
            'id': 2988507, 'name': 'Paris', 'region': 'Île-de-France', 'country': 'France',
            'country_code': 'FR', 'lat': 48.85341, 'lon': 2.3488, 'population': 2138551,
            'timezone': 'Europe/Paris',
        })

    def test_missing_optional_fields(self, mock_get):
        mock_get.return_value = _response([_NO_ADMIN])
        city = self._get({'q': 'Somewhere'}).json()[0]
        self.assertEqual(city['region'], '')
        self.assertIsNone(city['population'])
        self.assertEqual(city['country_code'], 'XX')

    def test_sends_language_and_max_count(self, mock_get):
        mock_get.return_value = _response([])
        self._get({'q': 'London', 'lang_iso': 'fr'})
        params = mock_get.call_args[1]['params']
        self.assertEqual(params['name'], 'London')
        self.assertEqual(params['language'], 'fr')
        self.assertEqual(params['count'], 20)
        self.assertNotIn('countryCode', params)

    def test_language_is_reduced_to_bare_code(self, mock_get):
        mock_get.return_value = _response([])
        self._get({'q': 'Paris', 'lang_iso': 'zh_tw'})
        self.assertEqual(mock_get.call_args[1]['params']['language'], 'zh')

    def test_default_language_is_english(self, mock_get):
        mock_get.return_value = _response([])
        self._get({'q': 'Paris'})
        self.assertEqual(mock_get.call_args[1]['params']['language'], 'en')

    def test_country_code_filters_server_side(self, mock_get):
        mock_get.return_value = _response([_PARIS_TX])
        data = self._get({'q': 'Paris', 'country_code': 'us'}).json()
        self.assertEqual(mock_get.call_args[1]['params']['countryCode'], 'US')
        self.assertEqual([c['country_code'] for c in data], ['US'])

    def test_country_code_guard_if_ignored_upstream(self, mock_get):
        mock_get.return_value = _response([_PARIS, _PARIS_TX])
        data = self._get({'q': 'Paris', 'country_code': 'US'}).json()
        self.assertEqual([c['id'] for c in data], [4717560])

    def test_invalid_country_code_is_400(self, mock_get):
        self.assertEqual(self._get({'q': 'Paris', 'country_code': 'FRA'}).status_code, 400)
        mock_get.assert_not_called()

    def test_limit_default_and_clamp(self, mock_get):
        many = [dict(_PARIS, id=i) for i in range(20)]
        mock_get.return_value = _response(many)
        self.assertEqual(len(self._get({'q': 'Paris'}).json()), 10)
        self.assertEqual(len(self._get({'q': 'Paris', 'limit': 3}).json()), 3)
        self.assertEqual(len(self._get({'q': 'Paris', 'limit': 50}).json()), 20)
        self.assertEqual(len(self._get({'q': 'Paris', 'limit': 0}).json()), 1)

    def test_invalid_limit_is_400(self, mock_get):
        self.assertEqual(self._get({'q': 'Paris', 'limit': 'abc'}).status_code, 400)

    def test_short_query_returns_empty_without_calling_upstream(self, mock_get):
        for q in ('', ' ', 'P', ' P '):
            response = self._get({'q': q})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), [])
        mock_get.assert_not_called()

    def test_two_characters_are_searched(self, mock_get):
        mock_get.return_value = _response([])
        self._get({'q': 'Pa'})
        mock_get.assert_called_once()

    def test_too_long_query_is_400(self, mock_get):
        self.assertEqual(self._get({'q': 'a' * 101}).status_code, 400)

    def test_no_match_returns_empty_list(self, mock_get):
        mock_get.return_value = _response(None)  # Open-Meteo omits "results"
        self.assertEqual(self._get({'q': 'zzzzqx'}).json(), [])

    def test_cache_shared_across_limits_case_and_spaces(self, mock_get):
        mock_get.return_value = _response([_PARIS, _PARIS_TX])
        self._get({'q': 'saint etienne', 'limit': 1})
        self._get({'q': '  Saint   Etienne ', 'limit': 5})
        mock_get.assert_called_once()

    def test_cache_separated_by_language_and_country(self, mock_get):
        mock_get.return_value = _response([_PARIS])
        self._get({'q': 'Paris', 'lang_iso': 'fr'})
        self._get({'q': 'Paris', 'lang_iso': 'en'})
        self._get({'q': 'Paris', 'lang_iso': 'fr', 'country_code': 'FR'})
        self.assertEqual(mock_get.call_count, 3)

    def test_empty_results_are_cached(self, mock_get):
        mock_get.return_value = _response(None)
        self._get({'q': 'zzzzqx'})
        self._get({'q': 'zzzzqx'})
        mock_get.assert_called_once()

    def test_upstream_http_error_is_503_and_not_cached(self, mock_get):
        mock_get.return_value = _response(None, status_code=500)
        self.assertEqual(self._get({'q': 'Paris'}).status_code, 503)
        self._get({'q': 'Paris'})
        self.assertEqual(mock_get.call_count, 2)

    def test_upstream_unreachable_is_503(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError
        self.assertEqual(self._get({'q': 'Paris'}).status_code, 503)
