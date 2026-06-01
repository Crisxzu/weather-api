from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework_api_key.models import APIKey

from api.providers.base import WeatherServiceError, WeatherServiceUnavailableError
from api.providers.schemas import (
    Condition, CurrentWeather, DailyForecast, HourlyForecast, Location, WeatherData,
)


def _make_weather_data(**overrides):
    defaults = dict(
        last_updated=1748772000,
        source='Weather API',
        source_link='https://www.weatherapi.com/',
        location=Location(
            name='Paris',
            region='Ile-de-France',
            country='France',
            lat=48.8566,
            lon=2.3522,
            tz_id='Europe/Paris',
            localtime_epoch=1748772000,
            localtime='2025-06-01 12:00',
        ),
        current=CurrentWeather(
            temp=18.0,
            min_temp=12.1,
            max_temp=23.5,
            is_day=True,
            feels_like=17.2,
            condition=Condition(code=1000, text='Sunny', icon=113),
        ),
        next_24h=[
            HourlyForecast(
                temp=18.0, humidity=62, timestamp=1748772000,
                is_day=True, condition=Condition(code=1000, text='Sunny', icon=113),
            )
        ],
        next_days=[
            DailyForecast(
                min_temp=12.1, max_temp=23.5, humidity=58, timestamp=1748736000,
                is_day=True, condition=Condition(code=1000, text='Sunny', icon=113),
            )
        ],
    )
    defaults.update(overrides)
    return WeatherData(**defaults)


class WeatherViewAuthTests(TestCase):

    def setUp(self):
        cache.clear()
        _, self.api_key = APIKey.objects.create_key(name='test-key')
        self.url = reverse('api:weather')

    def test_request_without_api_key_returns_403(self):
        response = self.client.get(self.url, {'position': '48.8566,2.3522'})
        self.assertEqual(response.status_code, 403)

    def test_request_with_invalid_api_key_returns_403(self):
        response = self.client.get(
            self.url,
            {'position': '48.8566,2.3522'},
            HTTP_AUTHORIZATION='Api-Key invalid-key-value',
        )
        self.assertEqual(response.status_code, 403)


class WeatherViewCacheTests(TestCase):

    def setUp(self):
        cache.clear()
        _, self.api_key = APIKey.objects.create_key(name='test-key')
        self.url = reverse('api:weather')
        self.auth = {'HTTP_AUTHORIZATION': f'Api-Key {self.api_key}'}

    @patch('api.views.get_primary_provider')
    def test_cache_miss_calls_provider(self, mock_registry):
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data()
        mock_registry.return_value = provider

        response = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.assertEqual(response.status_code, 200)
        provider.get_weather.assert_called_once()

    @patch('api.views.get_primary_provider')
    def test_cache_hit_does_not_call_provider(self, mock_registry):
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data()
        mock_registry.return_value = provider

        # First request — populates cache
        self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        # Second request — should hit cache
        self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)

        provider.get_weather.assert_called_once()

    @patch('api.views.get_primary_provider')
    def test_different_lang_iso_uses_different_cache_key(self, mock_registry):
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data()
        mock_registry.return_value = provider

        self.client.get(self.url, {'position': '48.8566,2.3522', 'lang_iso': 'en'}, **self.auth)
        self.client.get(self.url, {'position': '48.8566,2.3522', 'lang_iso': 'fr'}, **self.auth)

        self.assertEqual(provider.get_weather.call_count, 2)


class WeatherViewResponseTests(TestCase):

    def setUp(self):
        cache.clear()
        _, self.api_key = APIKey.objects.create_key(name='test-key')
        self.url = reverse('api:weather')
        self.auth = {'HTTP_AUTHORIZATION': f'Api-Key {self.api_key}'}

    @patch('api.views.get_primary_provider')
    def test_successful_response_shape(self, mock_registry):
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data()
        mock_registry.return_value = provider

        response = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('location', data)
        self.assertIn('current', data)
        self.assertIn('next_24h', data)
        self.assertIn('next_days', data)
        self.assertIn('source', data)

    @patch('api.views.get_primary_provider')
    def test_no_query_params_returns_400(self, mock_registry):
        provider = MagicMock()
        provider.get_weather.side_effect = ValueError('No valid position, city or IP address provided')
        mock_registry.return_value = provider

        response = self.client.get(self.url, **self.auth)
        self.assertEqual(response.status_code, 400)


class WeatherViewFallbackTests(TestCase):

    def setUp(self):
        cache.clear()
        _, self.api_key = APIKey.objects.create_key(name='test-key')
        self.url = reverse('api:weather')
        self.auth = {'HTTP_AUTHORIZATION': f'Api-Key {self.api_key}'}

    @patch('api.views.get_fallback_provider')
    @patch('api.views.get_primary_provider')
    def test_fallback_triggered_on_unavailable_error(self, mock_primary_reg, mock_fallback_reg):
        primary = MagicMock()
        primary.get_weather.side_effect = WeatherServiceUnavailableError('Primary down')
        mock_primary_reg.return_value = primary

        fallback = MagicMock()
        fallback.get_weather.return_value = _make_weather_data(source='Open-Meteo', source_link='https://open-meteo.com/')
        mock_fallback_reg.return_value = fallback

        response = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['source'], 'Open-Meteo')
        fallback.get_weather.assert_called_once()

    @patch('api.views.get_fallback_provider')
    @patch('api.views.get_primary_provider')
    def test_no_fallback_on_service_error(self, mock_primary_reg, mock_fallback_reg):
        primary = MagicMock()
        primary.get_weather.side_effect = WeatherServiceError(http_status=403, error_code=2007)
        mock_primary_reg.return_value = primary

        fallback = MagicMock()
        mock_fallback_reg.return_value = fallback

        response = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        # Deterministic error — no fallback, returns the error directly
        self.assertEqual(response.status_code, 403)
        fallback.get_weather.assert_not_called()

    @patch('api.views.get_fallback_provider')
    @patch('api.views.get_primary_provider')
    def test_503_when_no_fallback_configured(self, mock_primary_reg, mock_fallback_reg):
        primary = MagicMock()
        primary.get_weather.side_effect = WeatherServiceUnavailableError('Primary down')
        mock_primary_reg.return_value = primary

        mock_fallback_reg.return_value = None

        response = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.assertEqual(response.status_code, 503)

    @patch('api.views.get_fallback_provider')
    @patch('api.views.get_primary_provider')
    def test_503_when_both_providers_fail(self, mock_primary_reg, mock_fallback_reg):
        primary = MagicMock()
        primary.get_weather.side_effect = WeatherServiceUnavailableError('Primary down')
        mock_primary_reg.return_value = primary

        fallback = MagicMock()
        fallback.get_weather.side_effect = WeatherServiceUnavailableError('Fallback also down')
        mock_fallback_reg.return_value = fallback

        response = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.assertEqual(response.status_code, 503)
