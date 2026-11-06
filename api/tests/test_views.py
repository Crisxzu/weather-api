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


class PositionRoundingTests(TestCase):

    def test_rounds_to_two_decimals(self):
        from api.views import round_position
        self.assertEqual(round_position('48.856613,2.352222'), '48.86,2.35')
        self.assertEqual(round_position(' 48.8566 , 2.3522 '), '48.86,2.35')
        self.assertEqual(round_position('-33.8688,151.2093'), '-33.87,151.21')

    def test_negative_zero_is_normalized(self):
        from api.views import round_position
        self.assertEqual(round_position('-0.001,0.001'), '0.00,0.00')

    def test_invalid_or_missing_position_is_left_untouched(self):
        from api.views import round_position
        self.assertEqual(round_position('not-valid'), 'not-valid')
        self.assertIsNone(round_position(None))


class WeatherViewV2Tests(TestCase):

    def setUp(self):
        cache.clear()
        _, self.api_key = APIKey.objects.create_key(name='test-key')
        self.url = reverse('api:weather')
        self.auth = {'HTTP_AUTHORIZATION': f'Api-Key {self.api_key}'}

    @patch('api.views.get_primary_provider')
    def test_nearby_positions_share_cache_and_provider_gets_rounded_position(self, mock_registry):
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data()
        mock_registry.return_value = provider

        self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.client.get(self.url, {'position': '48.8571,2.3519'}, **self.auth)

        provider.get_weather.assert_called_once()
        self.assertEqual(provider.get_weather.call_args[1]['position'], '48.86,2.35')

    @patch('api.views.get_primary_provider')
    def test_v2_blocks_are_null_when_unsupported(self, mock_registry):
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data()
        mock_registry.return_value = provider

        data = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth).json()
        self.assertIsNone(data['next_minutes'])
        self.assertIsNone(data['alerts'])
        self.assertIn('chance_of_rain', data['next_24h'][0])
        self.assertIsNone(data['next_24h'][0]['chance_of_rain'])

    @patch('api.views.get_primary_provider')
    def test_v2_fields_are_serialized(self, mock_registry):
        from api.providers.schemas import MinutelyPrecipitation, WeatherAlert
        provider = MagicMock()
        weather = _make_weather_data(
            next_minutes=[MinutelyPrecipitation(timestamp=1748772000, precip_mm=0.4)],
            alerts=[WeatherAlert(event='Storm', headline='Orages', severity='Moderate', effective=1, expires=None)],
        )
        weather.next_24h[0].chance_of_rain = 80
        weather.next_days[0].sunrise = 1748749620
        provider.get_weather.return_value = weather
        mock_registry.return_value = provider

        data = self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth).json()
        self.assertEqual(data['next_minutes'], [{'timestamp': 1748772000, 'precip_mm': 0.4}])
        self.assertEqual(data['alerts'][0]['event'], 'Storm')
        self.assertIsNone(data['alerts'][0]['expires'])
        self.assertEqual(data['next_24h'][0]['chance_of_rain'], 80)
        self.assertEqual(data['next_days'][0]['sunrise'], 1748749620)

    @patch('api.views.cache.set')
    @patch('api.views.get_primary_provider')
    def test_short_ttl_when_next_minutes_present(self, mock_registry, mock_cache_set):
        from api.providers.schemas import MinutelyPrecipitation
        from api.views import NOWCAST_CACHE_TTL
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data(
            next_minutes=[MinutelyPrecipitation(timestamp=1748772000, precip_mm=0.0)],
        )
        mock_registry.return_value = provider

        self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.assertEqual(mock_cache_set.call_args[0][2], NOWCAST_CACHE_TTL)

    @patch('api.views.cache.set')
    @patch('api.views.get_primary_provider')
    def test_default_ttl_without_next_minutes(self, mock_registry, mock_cache_set):
        from api.views import CACHE_TTL
        provider = MagicMock()
        provider.get_weather.return_value = _make_weather_data()
        mock_registry.return_value = provider

        self.client.get(self.url, {'position': '48.8566,2.3522'}, **self.auth)
        self.assertEqual(mock_cache_set.call_args[0][2], CACHE_TTL)

