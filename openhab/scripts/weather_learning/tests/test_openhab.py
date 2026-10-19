"""Provider retirement must not strand Google entrypoints or reuse a site fallback."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import importlib, json, secrets, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_archive import snapshot


class OpenHABEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.requests = []
        self.regional = {'location': '38.3739919,-105.7744609', 'timezone': 'America/Denver'}
        self.status = 200
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                owner.requests.append((self.command, self.path, self.headers.get('Authorization'), b''))
                self.send_response(owner.status)
                self.end_headers()
                self.wfile.write(json.dumps(owner.regional).encode())
            def do_PUT(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                owner.requests.append((self.command, self.path, self.headers.get('Authorization'), body))
                self.send_response(202)
                self.end_headers()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)
        self.token = secrets.token_hex(16)
        self.env = self.root / 'openhab.env'
        self.env.write_text('export OPENHAB_TOKEN="' + self.token + '"\n')
        self.client = importlib.import_module('weather_learning.openhab')
        self.enterContext(patch.object(self.client, 'BASE', 'http://127.0.0.1:' + str(self.server.server_port) + '/rest'))
        self.enterContext(patch.object(self.client, 'ENV_FILE', str(self.env)))
        self.enterContext(patch.object(self.client, '_TOKEN', None))

    def test_regional_read_and_state_update_reuse_existing_private_identity(self):
        value = self.client.oh_get(self.client.I18N_CONFIG_PATH)
        self.assertEqual(value, self.regional)
        self.client.oh_put_state('Forecast_Provider_Status_JSON', 'UNDEF')
        self.assertEqual([(method, path, body) for method, path, _, body in self.requests], [
            ('GET', '/rest/services/org.openhab.i18n/config', b''),
            ('PUT', '/rest/items/Forecast_Provider_Status_JSON/state', b'UNDEF')])
        self.assertEqual([auth for _, _, auth, _ in self.requests], ['Bearer ' + self.token] * 2)

    def test_missing_token_and_http_failure_do_not_substitute_a_site(self):
        self.env.write_text('# no configured identity\n')
        with self.assertRaises(RuntimeError):
            self.client.oh_get(self.client.I18N_CONFIG_PATH)
        self.assertEqual(self.requests, [])
        self.env.write_text('OPENHAB_TOKEN=' + self.token + '\n')
        self.status = 503
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError):
            self.client.oh_get(self.client.I18N_CONFIG_PATH)
        self.assertEqual(len(self.requests), 1)

    def test_collector_runs_with_legacy_worker_unimportable(self):
        import weathernext_ingest
        reader = Mock()
        reader.discover_run.return_value = {'start_time': '2026-10-18T00:00:00Z'}
        reader.fetch_points.return_value = snapshot()
        reader.transport.bytes_received = 32
        reader.transport.requests = 1
        reader.transport.noncommercial_verified = True
        output = StringIO()
        with patch.dict(sys.modules, {'forecast_intel': None}), patch.object(weathernext_ingest, 'EarthEngineReader', return_value=reader), redirect_stdout(output):
            result = weathernext_ingest.main(['--probe', '--archive', str(self.root / 'archive')])
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'], 'PROBE_PASSED')
        self.assertEqual([path for _, path, _, _ in self.requests], ['/rest/services/org.openhab.i18n/config'])
        self.assertEqual(list((self.root / 'archive' / 'objects').glob('*.json')), [])

    def test_new_cli_cohort_does_not_load_previous_candidate(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from weather_learning.cli import _context
        from weather_learning.shadow import ShadowStore
        from weather_learning.training import fit_bias
        policy = self.root / 'policy.json'
        policy.write_text(json.dumps({'version': 2, 'streams': {'outdoor': dict(
            model='Fineoffset-WH65B', sensor_id=206, minimum_f=-60, maximum_f=140,
            validity_seconds=120, sensor_epoch='00000000-0000-4000-8000-000000000001')}}))
        policy.chmod(0o600)
        from weather_learning.archive import Archive
        Archive(self.root / 'archive')  # Existing collector-owned source.
        previous = ShadowStore(self.root / 'state')
        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        previous.install_model(fit_bias([], cutoff=cutoff, code_revision='a' * 40), fitted_at=cutoff)
        with patch.dict(sys.modules, {'forecast_intel': None}):
            _, state, _, _, _ = _context(SimpleNamespace(
                archive=str(self.root / 'archive'), state=str(self.root / 'state'), temperature_policy=str(policy)))
        self.assertIsNone(state.current_model())
        self.assertIsNotNone(previous.current_model())

    def test_shadow_publication_works_without_legacy_worker_or_fallback(self):
        from weather_learning.cli import main_shadow
        policy = self.root / 'policy.json'
        policy.write_text(json.dumps({'version': 2, 'streams': {'outdoor': dict(
            model='Fineoffset-WH65B', sensor_id=206, minimum_f=-60, maximum_f=140,
            validity_seconds=120, sensor_epoch='00000000-0000-4000-8000-000000000001')}}))
        policy.chmod(0o600)
        from weather_learning.archive import Archive
        Archive(self.root / 'archive')  # Collector owns initialization.
        output = StringIO()
        args = ['--archive', str(self.root / 'archive'), '--state', str(self.root / 'state'),
                '--temperature-policy', str(policy), '--code-revision', 'a' * 40, '--publish']
        with patch.dict(sys.modules, {'forecast_intel': None}), redirect_stdout(output):
            result = main_shadow(args)
        self.assertEqual(result, 0, output.getvalue())
        states = [json.loads(body) for method, _, _, body in self.requests if method == 'PUT']
        self.assertEqual(len(states), 3)
        self.assertTrue(all(value == states[0] for value in states))
        self.assertEqual(states[0]['status'], 'UNAVAILABLE')
        self.assertEqual(states[0]['reason'], 'NO_ELIGIBLE_SOURCE')
        self.assertFalse(states[0]['automaticActuation'])
        self.assertNotIn(self.token, output.getvalue())


    def test_failed_collection_reports_numeric_budget_use_without_upstream_text(self):
        import requests
        import weathernext_ingest
        reader = Mock()
        reader.discover_run.side_effect = requests.ReadTimeout('upstream diagnostic text must stay private')
        reader.transport.bytes_received = 123
        reader.transport.requests = 4
        output = StringIO()
        with patch.object(weathernext_ingest, 'EarthEngineReader', return_value=reader), patch.object(weathernext_ingest, 'monotonic', side_effect=[10., 30.], create=True), redirect_stdout(output):
            result = weathernext_ingest.main(['--collect', '--archive', str(self.root / 'failed-archive')])
        self.assertEqual(result, 1)
        value = json.loads(output.getvalue())
        self.assertEqual(value['status'], 'UNAVAILABLE')
        self.assertEqual(value['reason'], 'ReadTimeout')
        self.assertEqual(value['requests'], 4)
        self.assertEqual(value['bytes_received'], 123)
        self.assertEqual(value['elapsed_seconds'], 20.)
        self.assertNotIn('upstream diagnostic text must stay private', output.getvalue())
        self.assertNotIn(self.token, output.getvalue())


    def test_shadow_context_cannot_mutate_the_collectors_existing_index(self):
        import sqlite3
        from hashlib import sha256
        from types import SimpleNamespace
        from weather_learning.archive import Archive
        from weather_learning.cli import _context
        policy = self.root / 'readonly-policy.json'
        policy.write_text(json.dumps({'version': 2, 'streams': {'outdoor': dict(
            model='Fineoffset-WH65B', sensor_id=206, minimum_f=-60, maximum_f=140,
            validity_seconds=120, sensor_epoch='00000000-0000-4000-8000-000000000001')}}))
        policy.chmod(0o600)
        source = Archive(self.root / 'readonly-archive')
        before = (sha256(source.db.read_bytes()).hexdigest(), source.db.stat().st_mtime_ns, source.db.stat().st_ctime_ns)
        archive, _, _, _, _ = _context(SimpleNamespace(archive=str(source.root), state=str(self.root / 'readonly-state'), temperature_policy=str(policy)))
        with self.assertRaises(sqlite3.OperationalError):
            with archive._connect() as connection:connection.execute('DELETE FROM snapshots')
        self.assertEqual(before, (sha256(source.db.read_bytes()).hexdigest(), source.db.stat().st_mtime_ns, source.db.stat().st_ctime_ns))

    def test_missing_shadow_source_is_unavailable_without_initializing_history(self):
        from weather_learning.cli import main_shadow
        policy = self.root / 'missing-policy.json'
        policy.write_text(json.dumps({'version': 2, 'streams': {'outdoor': dict(
            model='Fineoffset-WH65B', sensor_id=206, minimum_f=-60, maximum_f=140,
            validity_seconds=120, sensor_epoch='00000000-0000-4000-8000-000000000001')}}))
        policy.chmod(0o600)
        missing = self.root / 'missing-source'
        output = StringIO()
        with redirect_stdout(output):
            result = main_shadow(['--archive', str(missing), '--state', str(self.root / 'missing-state'),
                '--temperature-policy', str(policy), '--code-revision', 'a' * 40, '--publish'])
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'], 'UNAVAILABLE')
        self.assertFalse(missing.exists(), 'observer initialized collector-owned history')
        states = [json.loads(body) for method, _, _, body in self.requests if method == 'PUT']
        self.assertEqual(len(states), 3)
        self.assertTrue(all(value == states[0] for value in states))
        self.assertEqual(states[0]['reason'], 'NO_ELIGIBLE_SOURCE')
        self.assertFalse(states[0]['automaticActuation'])
