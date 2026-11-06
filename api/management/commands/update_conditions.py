"""
Refresh conditions.json from WeatherAPI's published list.

    python manage.py update_conditions            # download, validate, write
    python manage.py update_conditions --dry-run  # show what would change

Safe to run from cron: the new file is validated before being written
atomically, and running workers reload it on their own (see api.utils.conditions).
Exits non-zero on any failure so cron/monitoring can report it.
"""
import json
import os
import tempfile
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError

from api.utils.conditions import CONDITIONS_PATH

DEFAULT_URL = 'https://www.weatherapi.com/docs/conditions.json'
_TIMEOUT_SECONDS = 30
_MIN_CONDITIONS = 40  # the list has ~60 entries; far fewer means a broken download


def _validate(data) -> list[dict]:
    if not isinstance(data, list) or len(data) < _MIN_CONDITIONS:
        raise CommandError(f'Expected a list of at least {_MIN_CONDITIONS} conditions')
    seen = set()
    for c in data:
        if not isinstance(c, dict):
            raise CommandError('Every condition must be an object')
        code = c.get('code')
        if not isinstance(code, int) or code in seen:
            raise CommandError(f'Invalid or duplicate condition code: {code!r}')
        seen.add(code)
        if not isinstance(c.get('day'), str) or not isinstance(c.get('night'), str) or not isinstance(c.get('icon'), int):
            raise CommandError(f'Condition {code}: day/night must be strings and icon an integer')
        languages = c.get('languages')
        if not isinstance(languages, list):
            raise CommandError(f'Condition {code}: languages must be a list')
        for lang in languages:
            if not all(isinstance(lang.get(k), str) for k in ('lang_iso', 'day_text', 'night_text')):
                raise CommandError(f'Condition {code}: malformed language entry {lang!r}')
    return sorted(data, key=lambda c: c['code'])


def _langs(data) -> set[str]:
    return {lang['lang_iso'] for c in data for lang in c['languages']}


def _write_atomically(path: Path, content: str):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Command(BaseCommand):
    help = "Download WeatherAPI's conditions list and update conditions.json if it changed."
    # Only touches a JSON file: skip system checks so cron output stays clean.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--url', default=DEFAULT_URL, help='Source URL (default: %(default)s)')
        parser.add_argument('--output', default=str(CONDITIONS_PATH), help='File to update (default: %(default)s)')
        parser.add_argument('--dry-run', action='store_true', help='Report changes without writing')
        parser.add_argument(
            '--allow-removals', action='store_true',
            help='Accept a list that drops condition codes we currently have (refused by default)',
        )

    def handle(self, *args, url, output, dry_run, allow_removals, **options):
        path = Path(output)

        try:
            resp = requests.get(url, timeout=_TIMEOUT_SECONDS, headers={'User-Agent': 'WeatherAppApi/1.0'})
            resp.raise_for_status()
            new = _validate(resp.json())
        except requests.exceptions.RequestException as e:
            raise CommandError(f'Download failed: {e}') from e
        except ValueError as e:
            raise CommandError(f'Response is not valid JSON: {e}') from e

        try:
            with open(path, encoding='utf-8') as f:
                current = json.load(f)
        except (OSError, ValueError):
            current = []

        old_codes = {c['code'] for c in current}
        new_codes = {c['code'] for c in new}
        added, removed = sorted(new_codes - old_codes), sorted(old_codes - new_codes)
        langs_added, langs_removed = sorted(_langs(new) - _langs(current)), sorted(_langs(current) - _langs(new))

        if removed and not allow_removals:
            raise CommandError(f'New list drops condition codes {removed}; rerun with --allow-removals to accept')

        if sorted(current, key=lambda c: c['code']) == new:
            self.stdout.write('conditions.json is already up to date')
            return

        self.stdout.write(f'Conditions: {len(current)} -> {len(new)}')
        if added:
            self.stdout.write(f'  added codes: {added}')
        if removed:
            self.stdout.write(f'  removed codes: {removed}')
        if langs_added:
            self.stdout.write(f'  added languages: {langs_added}')
        if langs_removed:
            self.stdout.write(self.style.WARNING(
                f'  removed languages: {langs_removed} (add an alias in api/utils/conditions.py '
                'if clients still send these codes)'
            ))
        if not (added or removed or langs_added or langs_removed):
            self.stdout.write('  translations changed')

        if dry_run:
            self.stdout.write('Dry run: nothing written')
            return

        _write_atomically(path, json.dumps(new, ensure_ascii=False, indent=2) + '\n')
        self.stdout.write(self.style.SUCCESS(f'Updated {path}'))
