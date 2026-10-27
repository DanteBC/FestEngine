import base64
import hashlib
import hmac
import json
import queue
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src import webhook_sender
from src.constants import is_skipped_note
from src.webhook_sender import (
    WebhookSender,
    event_expired,
    parse_custom_headers,
    retry_delay,
    sign_payload,
    validate_secret,
)


class WebhookSenderTests(unittest.TestCase):
    def test_signature_matches_standard_webhooks_format(self):
        secret = 'whsec_' + base64.b64encode(b'webhook secret').decode('ascii')
        body = b'{"type":"hook.test"}'
        msg_id = 'msg_fixed'
        attempt_ts = 1700000000
        expected_digest = hmac.new(
            b'webhook secret',
            b'msg_fixed.1700000000.' + body,
            hashlib.sha256,
        ).digest()
        expected = 'v1,' + base64.b64encode(expected_digest).decode('ascii')
        self.assertEqual(sign_payload(secret, msg_id, attempt_ts, body), expected)

    def test_header_parsing_validation_and_colons(self):
        self.assertEqual(parse_custom_headers('Authorization: Bearer abc\nX-Note: a:b:c'),
                         {'Authorization': 'Bearer abc', 'X-Note': 'a:b:c'})
        with self.assertRaises(ValueError):
            parse_custom_headers('Content-Type: text/plain')
        with self.assertRaises(ValueError):
            parse_custom_headers('Bad Header: value')
        with self.assertRaises(ValueError):
            parse_custom_headers('X-Token: first\nsecond')
        with self.assertRaises(ValueError):
            validate_secret('whsec_not-base64!')

    def test_retry_policy_and_expiration(self):
        self.assertEqual(retry_delay(0, random_value=1), 1)
        self.assertEqual(retry_delay(5, random_value=1), 30)
        self.assertEqual(retry_delay(20, random_value=1), 30)
        self.assertEqual(retry_delay(0, retry_after=4, random_value=0.8), 4)
        self.assertAlmostEqual(retry_delay(1, random_value=1.2), 2.4)
        self.assertTrue(event_expired('row.play', 0, now=121))
        self.assertFalse(event_expired('row.play', 1, now=120))
        self.assertTrue(event_expired('row.updated', 0, now=601))
        self.assertFalse(event_expired('row.updated', 1, now=600))

    def test_skip_words_are_matched_as_whole_words(self):
        self.assertTrue(is_skipped_note('ПРОПУСК номера'))
        self.assertTrue(is_skipped_note('номер skipped'))
        self.assertTrue(is_skipped_note('номер пропущена'))
        self.assertFalse(is_skipped_note('skipping intro'))
        self.assertFalse(is_skipped_note('skip_intro'))


class WebhookHTTPTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            'responses': queue.Queue(),
            'requests': [],
            'lock': threading.Lock(),
            'request_seen': threading.Event(),
            'response_gate': None,
            'response_body': b'',
        }
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', '0'))
                body = self.rfile.read(length)
                with state['lock']:
                    state['requests'].append({
                        'body': body,
                        'headers': dict(self.headers.items()),
                    })
                state['request_seen'].set()
                if state['response_gate'] is not None:
                    state['response_gate'].wait(timeout=2)
                try:
                    code = state['responses'].get_nowait()
                except queue.Empty:
                    code = 200
                self.send_response(code)
                if code == 429 or code >= 500:
                    self.send_header('Retry-After', '0')
                if code == 302:
                    self.send_header('Location', '/redirected')
                if state['response_body']:
                    self.send_header('Content-Length', str(len(state['response_body'])))
                self.end_headers()
                if state['response_body']:
                    self.wfile.write(state['response_body'])

            def log_message(self, format, *args):
                return

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.url = 'http://127.0.0.1:%d/hook' % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)

    def make_sender(self, **callbacks):
        secret = callbacks.pop('secret', '')
        headers = callbacks.pop('headers', {})
        sender = WebhookSender(**callbacks)
        sender.configure(self.url, secret, headers)
        self.addCleanup(sender.close)
        return sender

    def test_send_now_includes_standard_headers_custom_headers_and_signature(self):
        secret = 'whsec_' + base64.b64encode(b'local test key').decode('ascii')
        sender = WebhookSender()
        sender.configure(self.url, secret, {'X-Api-Key': 'abc:123'})
        self.addCleanup(sender.close)

        self.assertEqual(sender.send_now('hook.test', {}), '200')
        request = self.state['requests'][0]
        headers = {name.lower(): value for name, value in request['headers'].items()}
        self.assertEqual(headers['user-agent'], 'FestEngine')
        self.assertEqual(headers['x-api-key'], 'abc:123')
        self.assertTrue(headers['webhook-id'].startswith('msg_'))
        expected = sign_payload(secret, headers['webhook-id'],
                                int(headers['webhook-timestamp']), request['body'])
        self.assertEqual(headers['webhook-signature'], expected)
        self.assertEqual(json.loads(request['body']), {
            'type': 'hook.test',
            'timestamp': json.loads(request['body'])['timestamp'],
            'data': {},
        })

    def test_signature_is_omitted_when_no_secret_is_configured(self):
        sender = WebhookSender()
        sender.configure(self.url)
        self.addCleanup(sender.close)

        self.assertEqual(sender.send_now('hook.test', {}), '200')
        headers = {name.lower(): value for name, value in self.state['requests'][0]['headers'].items()}
        self.assertNotIn('webhook-signature', headers)
        self.assertIn('webhook-id', headers)
        self.assertIn('webhook-timestamp', headers)

    def test_503_retries_same_event_and_preserves_fifo_order(self):
        self.state['responses'].put(503)
        original_delay = webhook_sender.retry_delay
        webhook_sender.retry_delay = lambda *args: 0
        self.addCleanup(setattr, webhook_sender, 'retry_delay', original_delay)
        sender = self.make_sender()

        sender.send('row.play', {'row': None})
        sender.send('row.stop', {'row': None})
        sender._queue.join()

        requests = self.state['requests']
        self.assertEqual([json.loads(r['body'])['type'] for r in requests],
                         ['row.play', 'row.play', 'row.stop'])
        ids = [{name.lower(): value for name, value in r['headers'].items()}['webhook-id']
               for r in requests]
        self.assertEqual(ids[0], ids[1])
        self.assertNotEqual(ids[1], ids[2])
        self.assertEqual(requests[0]['body'], requests[1]['body'])

    def test_404_is_dropped_and_410_disables_queue(self):
        statuses = []
        logs = []
        gone = []
        sender = self.make_sender(on_status=statuses.append, on_log=logs.append,
                                  on_gone=lambda: gone.append(True))
        self.state['responses'].put(404)
        self.assertTrue(sender.send_now('hook.test', {}).startswith('404 —'))

        self.state['responses'].put(410)
        response_gate = threading.Event()
        self.state['response_gate'] = response_gate
        self.state['request_seen'].clear()
        sender.send('row.updated', {'row': None})
        self.assertTrue(self.state['request_seen'].wait(timeout=2))
        sender.send('row.updated', {'row': None})
        response_gate.set()
        sender._queue.join()
        self.assertEqual(gone, [True])
        self.assertIn('410 — disabled', statuses)
        self.assertTrue(any('410' in message for message in logs))
        self.assertEqual(len(self.state['requests']), 2)

    def test_redirect_is_not_followed(self):
        self.state['responses'].put(302)
        sender = WebhookSender()
        sender.configure(self.url)
        self.addCleanup(sender.close)

        result = sender.send_now('hook.test', {})
        self.assertTrue(result.startswith('302 —'))
        self.assertEqual(len(self.state['requests']), 1)

    def test_clear_cancels_pending_retry_and_response_body_redacts_header_values(self):
        logs = []
        sender = self.make_sender(headers={'X-Api-Key': 'private-token'}, on_log=logs.append)
        self.state['responses'].put(404)
        self.state['response_body'] = b'request used private-token'
        result = sender.send_now('hook.test', {})
        self.assertTrue(result.startswith('404 —'))
        self.assertTrue(any('[REDACTED]' in message for message in logs))
        self.assertFalse(any('private-token' in message for message in logs))

        self.state['response_body'] = b''
        self.state['request_seen'].clear()
        self.state['responses'].put(503)
        original_delay = webhook_sender.retry_delay
        webhook_sender.retry_delay = lambda *args: 5
        self.addCleanup(setattr, webhook_sender, 'retry_delay', original_delay)
        sender.send('row.play', {'row': None})
        self.assertTrue(self.state['request_seen'].wait(timeout=2))
        sender.clear()
        sender._queue.join()
        self.assertEqual(len(self.state['requests']), 2)

    def test_optional_standardwebhooks_verifier(self):
        try:
            from standardwebhooks import Webhook
        except ImportError:
            self.skipTest("standardwebhooks is not installed")
        secret = 'whsec_' + base64.b64encode(b'local test key').decode('ascii')
        body = b'{"type":"hook.test"}'
        msg_id = 'msg_optional'
        timestamp = str(int(time.time()))
        signature = sign_payload(secret, msg_id, int(timestamp), body)
        verifier = Webhook(secret)
        verifier.verify(body, {
            'webhook-id': msg_id,
            'webhook-timestamp': timestamp,
            'webhook-signature': signature,
        })


if __name__ == '__main__':
    unittest.main()
