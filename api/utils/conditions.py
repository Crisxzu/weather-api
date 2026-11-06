import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WMOCondition:
    code: int
    icon: int

_root = Path(__file__).resolve().parent.parent.parent

CONDITIONS_PATH = _root / 'conditions.json'

# conditions.json can be refreshed on disk by `manage.py update_conditions`;
# running workers pick the new version up within this many seconds.
_RELOAD_CHECK_SECONDS = 60

# WeatherAPI renamed some language codes in conditions.json. Accept both
# spellings so clients sending the old (or new) code keep getting translations.
_LANG_ALIASES = {
    'zh': 'zh_cn',
    'zh_hsn': 'hsn',
    'zh_wuu': 'wuu',
    'zh_yue': 'yue',
}
_LANG_ALIASES.update({new: old for old, new in list(_LANG_ALIASES.items())})

with open(_root / 'wmo_conditions.json') as f:
    _wmo_conditions = json.load(f)


class _ConditionsStore:
    """conditions.json indexed by code, reloaded when the file's mtime changes."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._by_code: dict[int, dict] = {}
        self._mtime: float | None = None
        self._last_check = 0.0
        self._load()

    def _load(self):
        mtime = os.stat(self._path).st_mtime
        with open(self._path, encoding='utf-8') as f:
            data = json.load(f)
        self._by_code = {c['code']: c for c in data}
        self._mtime = mtime

    def get(self, code: int) -> dict | None:
        now = time.monotonic()
        if now - self._last_check >= _RELOAD_CHECK_SECONDS:
            with self._lock:
                self._last_check = now
                try:
                    if os.stat(self._path).st_mtime != self._mtime:
                        self._load()
                        logger.info('Reloaded %s (%d conditions)', self._path.name, len(self._by_code))
                except (OSError, ValueError, KeyError, TypeError):
                    # Keep serving the previous version rather than failing requests.
                    logger.exception('Could not reload %s, keeping the previous version', self._path.name)
        return self._by_code.get(code)


_store = _ConditionsStore(CONDITIONS_PATH)


def _normalize_lang(lang_iso: str) -> str:
    return lang_iso.strip().lower().replace('-', '_')


def get_condition_by_code(code: int, is_day: bool, lang_iso: str = None) -> str | None:
    condition = _store.get(code)
    if condition is None:
        return None
    default = condition['day'] if is_day else condition['night']
    if not lang_iso:
        return default
    lang = _normalize_lang(lang_iso)
    candidates = (lang, _LANG_ALIASES.get(lang))
    for language in condition['languages']:
        if language['lang_iso'] in candidates:
            return language['day_text'] if is_day else language['night_text']
    return default


def get_condition_by_wmo_code(wmo_code: int) -> WMOCondition:
    entry = _wmo_conditions.get(str(wmo_code))
    if entry is None:
        logger.warning('Unknown WMO code %s, falling back to Clear', wmo_code)
        return WMOCondition(code=1000, icon=113)
    return WMOCondition(code=entry['code'], icon=entry['icon'])
