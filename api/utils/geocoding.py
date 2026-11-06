"""
Open-Meteo geocoding (place name → places), shared by the city search endpoint
and the weather `city=` query. Data comes from GeoNames (CC BY 4.0).
"""
import requests

from api.providers.base import WeatherServiceUnavailableError

GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search'
MAX_RESULTS = 20
_TIMEOUT_SECONDS = 5


def search_places(name: str, *, language: str = 'en', count: int = 10, country_code: str | None = None) -> list[dict]:
    """
    Raw Open-Meteo results, in Open-Meteo's order (relevance, then population).
    Returns [] when nothing matches. Note that Open-Meteo only does fuzzy
    matching from 3 characters (2 = exact match only).

    Raises WeatherServiceUnavailableError on network or HTTP errors.
    """
    params = {'name': name, 'count': count, 'language': language, 'format': 'json'}
    cc = country_code.strip().upper() if country_code and country_code.strip() else None
    if cc:
        params['countryCode'] = cc
    try:
        resp = requests.get(GEOCODING_URL, params=params, timeout=_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        raise WeatherServiceUnavailableError(f'Open-Meteo geocoding unreachable: {e}') from e
    if resp.status_code != 200:
        raise WeatherServiceUnavailableError(f'Open-Meteo geocoding returned HTTP {resp.status_code}')

    results = resp.json().get('results') or []
    if cc:  # countryCode already filters server-side; keep a guard in case it is ignored
        results = [r for r in results if (r.get('country_code') or '').upper() == cc]
    return results
