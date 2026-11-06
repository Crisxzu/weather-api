import os
from abc import ABC, abstractmethod

from api.providers.schemas import WeatherData


class WeatherServiceUnavailableError(Exception):
    pass


class WeatherServiceError(Exception):
    MESSAGES = {
        1002: 'API key not provided.',
        1003: "Parameter 'q' not provided.",
        1005: 'API request URL is invalid.',
        1006: 'No location found matching the provided parameter.',
        2006: 'API key is invalid.',
        2007: 'API key has exceeded its monthly call quota.',
        2008: 'API key has been disabled.',
        2009: 'API key does not have access to this resource.',
        9000: 'Invalid JSON body in request.',
        9001: 'Too many locations in bulk request.',
        9999: 'Internal weather service error.',
    }

    def __init__(self, http_status, error_code=None):
        self.http_status = http_status
        self.error_code = error_code
        self.message = self.MESSAGES.get(error_code, 'An unexpected error occurred with the weather service.')
        super().__init__(self.message)


class WeatherProvider(ABC):

    @abstractmethod
    def get_weather(self, *, position: str | None, city: str | None, country_code: str | None, ip_address: str | None, lang_iso: str) -> WeatherData:
        """
        Fetch weather data and return a normalized dict matching WeatherDataSerializer.

        Raises:
            ValueError                     — invalid or missing query parameters
            WeatherServiceError            — provider returned a known error response
            WeatherServiceUnavailableError — network failure, timeout, or quota exceeded
        """
        ...

    @property
    @abstractmethod
    def supports_ip_query(self) -> bool:
        """True if this provider can resolve weather from an IP address alone."""
        ...


_DEFAULT_FORECAST_DAYS = 7
_MAX_FORECAST_DAYS = 16


def get_forecast_days() -> int:
    """Number of forecast days to request (WEATHER_FORECAST_DAYS, default 7, clamped to 1..16).

    Providers may return fewer days than requested (WeatherAPI's plan caps it
    at 3), so clients must accept a variable-length next_days.
    """
    try:
        days = int(os.getenv('WEATHER_FORECAST_DAYS', _DEFAULT_FORECAST_DAYS))
    except ValueError:
        days = _DEFAULT_FORECAST_DAYS
    return max(1, min(days, _MAX_FORECAST_DAYS))
