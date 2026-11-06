import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

_REPO_CONDITIONS = Path(__file__).resolve().parents[2] / 'conditions.json'


def _response(data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = data
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.exceptions.HTTPError(f'{status_code} Error')
    return mock


def _conditions(codes, lang='fr'):
    return [
        {'code': c, 'day': f'day {c}', 'night': f'night {c}', 'icon': 113,
         'languages': [{'lang_name': 'X', 'lang_iso': lang, 'day_text': 'j', 'night_text': 'n'}]}
        for c in codes
    ]


_BASE = list(range(2000, 2050))  # 50 codes, above the sanity minimum
_NEW = 3000


@patch('api.management.commands.update_conditions.requests.get')
class UpdateConditionsCommandTests(TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / 'conditions.json'
        self.path.write_text(json.dumps(_conditions(_BASE)))

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        out = StringIO()
        call_command('update_conditions', '--output', str(self.path), *args, stdout=out)
        return out.getvalue()

    def test_writes_new_codes(self, mock_get):
        mock_get.return_value = _response(_conditions(_BASE + [_NEW]))
        out = self._run()
        self.assertIn(f'added codes: [{_NEW}]', out)
        self.assertIn(_NEW, [c['code'] for c in json.loads(self.path.read_text())])

    def test_output_is_sorted_and_readable(self, mock_get):
        mock_get.return_value = _response(list(reversed(_conditions(_BASE + [_NEW]))))
        self._run()
        text = self.path.read_text()
        self.assertEqual([c['code'] for c in json.loads(text)], sorted(_BASE + [_NEW]))
        self.assertIn('\n  {', text)  # indented, one entry per block

    def test_up_to_date_does_not_rewrite(self, mock_get):
        mock_get.return_value = _response(list(reversed(_conditions(_BASE))))
        before = self.path.stat().st_mtime_ns
        self.assertIn('already up to date', self._run())
        self.assertEqual(self.path.stat().st_mtime_ns, before)

    def test_dry_run_does_not_write(self, mock_get):
        mock_get.return_value = _response(_conditions(_BASE + [_NEW]))
        before = self.path.read_text()
        self.assertIn('Dry run', self._run('--dry-run'))
        self.assertEqual(self.path.read_text(), before)

    def test_removed_codes_are_refused_by_default(self, mock_get):
        mock_get.return_value = _response(_conditions(_BASE[1:]))
        with self.assertRaises(CommandError):
            self._run()
        self.assertEqual(len(json.loads(self.path.read_text())), len(_BASE))

    def test_removed_codes_accepted_with_flag(self, mock_get):
        mock_get.return_value = _response(_conditions(_BASE[1:]))
        self._run('--allow-removals')
        self.assertEqual(len(json.loads(self.path.read_text())), len(_BASE) - 1)

    def test_removed_languages_are_reported(self, mock_get):
        mock_get.return_value = _response(_conditions(_BASE, lang='zh_cn'))
        out = self._run()
        self.assertIn("removed languages: ['fr']", out)

    def test_too_short_list_is_rejected(self, mock_get):
        mock_get.return_value = _response(_conditions([1000, 1003]))
        with self.assertRaises(CommandError):
            self._run()

    def test_malformed_entry_is_rejected(self, mock_get):
        data = _conditions(_BASE + [_NEW])
        data[-1]['icon'] = 'not-an-int'
        mock_get.return_value = _response(data)
        with self.assertRaises(CommandError):
            self._run()

    def test_duplicate_codes_are_rejected(self, mock_get):
        mock_get.return_value = _response(_conditions(_BASE + [_BASE[0]]))
        with self.assertRaises(CommandError):
            self._run()

    def test_http_error_raises(self, mock_get):
        mock_get.return_value = _response(None, status_code=503)
        with self.assertRaises(CommandError):
            self._run()

    def test_network_error_raises(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError
        with self.assertRaises(CommandError):
            self._run()

    def test_invalid_json_raises(self, mock_get):
        resp = _response(None)
        resp.json.side_effect = ValueError('bad json')
        mock_get.return_value = resp
        with self.assertRaises(CommandError):
            self._run()

    def test_repo_conditions_file_passes_validation(self, mock_get):
        from api.management.commands.update_conditions import _validate
        _validate(json.loads(_REPO_CONDITIONS.read_text(encoding='utf-8')))
