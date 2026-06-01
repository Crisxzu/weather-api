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
