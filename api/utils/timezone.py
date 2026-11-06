import logging
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)


def get_time_for_timezone(tz_id: str) -> datetime | None:
    try:
        timezone = pytz.timezone(tz_id)
        return datetime.now(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error('Unknown timezone: %s', tz_id)
        return None


def local_to_epoch(value: str, fmt: str | None, tz_id: str) -> int | None:
    """
    Convert a wall-clock time expressed in `tz_id` to an epoch timestamp.

    `fmt` is a strptime format, or None for ISO 8601 (e.g. "2025-06-01T14:00").
    Returns None when the value cannot be parsed (e.g. WeatherAPI's "No sunrise").
    """
    if not value:
        return None
    try:
        naive = datetime.fromisoformat(value) if fmt is None else datetime.strptime(value, fmt)
        return int(pytz.timezone(tz_id).localize(naive).timestamp())
    except (ValueError, pytz.exceptions.UnknownTimeZoneError):
        return None
