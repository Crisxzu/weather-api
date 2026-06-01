import logging
import re

import requests

logger = logging.getLogger(__name__)

_IP_API_URL = 'http://ip-api.com/json/{ip}'
_FIELDS = 'status,lat,lon,city,regionName,country,timezone'

_private_ip_regex = re.compile(
    r'^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|::1$|fc|fd)'
)


def resolve_ip(ip_address: str) -> dict:
    """
    Resolves an IP address to geographic coordinates and location metadata.

    Returns a dict with keys: lat, lon, city, region, country, timezone.
    Raises ValueError for private/invalid IPs.
    Raises WeatherServiceUnavailableError on network failure.
    """
    from api.providers.base import WeatherServiceUnavailableError

    if _private_ip_regex.match(ip_address):
        raise ValueError(f'IP address {ip_address} is private and cannot be geolocated')

    try:
        response = requests.get(
            _IP_API_URL.format(ip=ip_address),
            params={'fields': _FIELDS},
            timeout=5,
        )
    except requests.exceptions.ConnectionError as e:
        raise WeatherServiceUnavailableError('IP geolocation service unreachable') from e
    except requests.exceptions.Timeout as e:
        raise WeatherServiceUnavailableError('IP geolocation service timed out') from e

    if response.status_code != 200:
        raise WeatherServiceUnavailableError(f'IP geolocation returned HTTP {response.status_code}')

    data = response.json()
    if data.get('status') != 'success':
        raise ValueError(f'Unable to geolocate IP address {ip_address}')

    return {
        'lat': float(data['lat']),
        'lon': float(data['lon']),
        'city': data.get('city', ''),
        'region': data.get('regionName', ''),
        'country': data.get('country', ''),
        'timezone': data.get('timezone', ''),
    }
