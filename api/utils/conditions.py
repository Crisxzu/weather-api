import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_root = Path(__file__).resolve().parent.parent.parent

with open(_root / 'conditions.json') as f:
    _conditions = json.load(f)

with open(_root / 'wmo_conditions.json') as f:
    _wmo_conditions = json.load(f)


def get_condition_by_code(code: int, is_day: bool, lang_iso: str = None) -> str | None:
    for condition in _conditions:
        if condition['code'] == code:
            default = condition['day'] if is_day else condition['night']
            if lang_iso:
                result = [l for l in condition['languages'] if l['lang_iso'] == lang_iso]
                if not result:
                    return default
                language = result[0]
                return language['day_text'] if is_day else language['night_text']
            return default
    return None


def get_condition_by_wmo_code(wmo_code: int) -> dict:
    entry = _wmo_conditions.get(str(wmo_code))
    if entry is None:
        logger.warning('Unknown WMO code %s, falling back to Clear', wmo_code)
        return {'code': 1000, 'icon': 113}
    return {'code': entry['code'], 'icon': entry['icon']}
