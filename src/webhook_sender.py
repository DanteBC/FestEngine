import base64
import binascii
import datetime
import email.utils
import hashlib
import hmac
import json
import queue
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


MAX_QUEUE_SIZE = 200
REQUEST_TIMEOUT = 10
SCENE_EVENT_LIFETIME = 120
STATE_EVENT_LIFETIME = 600
SCENE_EVENTS = {
    'row.show',
    'row.play',
    'row.stop',
    'row.finished',
    'row.end',
    'projector.clear',
    'system.emergency_stop',
    'countdown.start',
    'background.play',
    'background.pause',
}
RESERVED_HEADERS = {
    'content-type',
    'content-length',
    'host',
    'user-agent',
    'webhook-id',
    'webhook-timestamp',
    'webhook-signature',
}
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
RETRY_DELAYS = (1, 2, 4, 8, 16, 30)


def parse_custom_headers(value):
    if isinstance(value, str):
        headers = {}
        for line_number, line in enumerate(value.splitlines(), 1):
            if not line.strip():
                continue
            if ':' not in line:
                raise ValueError("Header line %d must be in 'Name: value' format" % line_number)
            name, header_value = line.split(':', 1)
            name = name.strip()
            header_value = header_value.strip()
            if name in headers:
                raise ValueError("Duplicate header name: %s" % name)
            headers[name] = header_value
    elif isinstance(value, dict):
        headers = dict(value)
    else:
        raise ValueError("Custom headers must be a mapping or text")

    normalized_names = set()
    for name, header_value in headers.items():
        if not isinstance(name, str) or not HEADER_NAME_RE.fullmatch(name):
            raise ValueError("Invalid HTTP header name: %r" % name)
        if name.lower() in RESERVED_HEADERS:
            raise ValueError("Header %s is managed by FestEngine" % name)
        if name.lower() in normalized_names:
            raise ValueError("Duplicate header name: %s" % name)
        normalized_names.add(name.lower())
        if not isinstance(header_value, str) or '\r' in header_value or '\n' in header_value:
            raise ValueError("Header values must be text without CR or LF")
        try:
            header_value.encode('latin-1')
        except UnicodeEncodeError:
            raise ValueError("Header values must be representable as HTTP header bytes")
    return headers


def validate_secret(secret):
    if secret is None or secret == '':
        return
    if not isinstance(secret, str):
        raise ValueError("Webhook secret must be text")
    encoded = secret[len('whsec_'):] if secret.startswith('whsec_') else secret
    try:
        decoded = base64.b64decode(encoded.encode('ascii'), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ValueError("Webhook secret must contain valid base64 data")
    if not decoded:
        raise ValueError("Webhook secret must not be empty")


def validate_webhook_url(url):
    if url is None:
        return ''
    if not isinstance(url, str):
        raise ValueError("Webhook URL must be text")
    url = url.strip()
    if not url or url.lower() == 'debug':
        return url
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as error:
        raise ValueError("Invalid webhook URL: %s" % error)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
        raise ValueError("Webhook URL must be an absolute HTTP or HTTPS URL")
    return url


def sign_payload(secret, msg_id, attempt_ts, body):
    validate_secret(secret)
    encoded = secret[len('whsec_'):] if secret.startswith('whsec_') else secret
    key = base64.b64decode(encoded.encode('ascii'), validate=True)
    to_sign = ("%s.%d." % (msg_id, attempt_ts)).encode('utf-8') + body
    digest = hmac.new(key, to_sign, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode('ascii')


def event_expired(event_type, created_at, now=None):
    if now is None:
        now = time.time()
    lifetime = SCENE_EVENT_LIFETIME if event_type in SCENE_EVENTS else STATE_EVENT_LIFETIME
    return now - created_at > lifetime


def retry_delay(retry_number, retry_after=None, random_value=None):
    base_delay = RETRY_DELAYS[min(retry_number, len(RETRY_DELAYS) - 1)]
    if random_value is None:
        random_value = random.uniform(0.8, 1.2)
    delay = base_delay * random_value
    if retry_after is not None:
        delay = max(delay, retry_after)
    return delay


def _retry_after_seconds(value, now=None):
    if not value:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            retry_time = email.utils.parsedate_to_datetime(value)
            if retry_time.tzinfo is None:
                retry_time = retry_time.replace(tzinfo=datetime.timezone.utc)
            if now is None:
                now = datetime.datetime.now(datetime.timezone.utc)
            return max(0, (retry_time - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new_url):
        return None


class WebhookSender:
    def __init__(self, on_status=None, on_log=None, on_gone=None):
        self.on_status = on_status or (lambda status: None)
        self.on_log = on_log or (lambda message: None)
        self.on_gone = on_gone or (lambda: None)
        self._queue = queue.Queue(MAX_QUEUE_SIZE)
        self._config_lock = threading.Lock()
        self._config = ('', '', {})
        self._closed = threading.Event()
        self._disabled_by_receiver = threading.Event()
        self._active_lock = threading.Lock()
        self._active_item = None
        self._worker = threading.Thread(target=self._run, name='WebhookSender', daemon=True)
        self._worker.start()

    def configure(self, url, secret='', headers=None):
        url = validate_webhook_url(url)
        if secret is None:
            secret = ''
        validate_secret(secret)
        headers = parse_custom_headers({} if headers is None else headers)
        with self._config_lock:
            self._config = (url or '', secret or '', headers)
        self._disabled_by_receiver.clear()

    def send(self, event_type, data):
        if self._closed.is_set() or self._disabled_by_receiver.is_set():
            self.on_log("Event %s not queued; receiver is disabled" % event_type)
            return False
        try:
            item = self._make_item(event_type, data)
        except (TypeError, ValueError, UnicodeError) as error:
            self.on_status('serialization error')
            self.on_log("Failed to serialize %s: %s" % (event_type, error))
            return False
        self.on_status('queued')
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                dropped = self._queue.get_nowait()
                self._queue.task_done()
                self.on_log("Queue full; dropped oldest event %s" % dropped['event_type'])
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                self.on_log("Queue full; dropped event %s" % event_type)
                return False
        return True

    def send_now(self, event_type, data):
        item = self._make_item(event_type, data)
        result = self._send_attempt(item)
        if result['code'] is not None and 200 <= result['code'] < 300:
            self.on_status(str(result['code']))
            self.on_log("Delivered %s (%d)" % (event_type, result['code']))
            return str(result['code'])
        if result['code'] == 410:
            self._disabled_by_receiver.set()
            self.on_status('410 — disabled')
            self.on_log("Receiver returned 410; disabling webhooks")
            self.clear()
            self.on_gone()
            return '410 — disabled'
        if result['code'] is not None:
            code = result['code']
            retryable = code == 429 or code >= 500
            status = "%d — %s" % (code, 'retryable' if retryable else 'dropped')
            self.on_status(status)
            self.on_log("%s %s (%d): %s" %
                        ('Retryable' if retryable else 'Dropped', event_type, code, result['detail'][:200]))
            return status
        self.on_status('connection failed')
        self.on_log("Failed to send %s: %s" % (event_type, result['detail']))
        return result['detail'] or 'connection failed'

    def clear(self):
        with self._active_lock:
            if self._active_item is not None:
                self._active_item['cancel'].set()
        cleared = 0
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                cleared += 1
            except queue.Empty:
                break
        if cleared:
            self.on_log("Cleared %d queued event(s)" % cleared)
        return cleared

    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        self.clear()
        self.on_log("Webhook sender closed; pending events discarded")

    @staticmethod
    def _make_event(event_type, data):
        now = datetime.datetime.now(datetime.timezone.utc)
        timestamp = now.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        return {
            'type': event_type,
            'timestamp': timestamp,
            'data': data,
        }, now.timestamp()

    def _make_item(self, event_type, data):
        envelope, queued_at = self._make_event(event_type, data)
        body = json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return {
            'event_type': event_type,
            'envelope': envelope,
            'body': body,
            'msg_id': 'msg_' + uuid.uuid4().hex,
            'queued_at': queued_at,
            'config': self._settings(),
            'cancel': threading.Event(),
        }

    def _settings(self):
        with self._config_lock:
            return self._config

    def _send_attempt(self, item):
        url, secret, custom_headers = item['config']
        attempt_ts = int(time.time())
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'FestEngine',
            'webhook-id': item['msg_id'],
            'webhook-timestamp': str(attempt_ts),
        }
        if secret:
            headers['webhook-signature'] = sign_payload(secret, item['msg_id'], attempt_ts, item['body'])
        headers.update(custom_headers)
        redactions = [url, secret] + list(custom_headers.values())
        if secret.startswith('whsec_'):
            redactions.append(secret[len('whsec_'):])
        redactions.extend([headers.get('webhook-signature', '')])

        def redact(value):
            for sensitive in redactions:
                if sensitive:
                    value = value.replace(sensitive, '[REDACTED]')
            return value

        try:
            request = urllib.request.Request(url, data=item['body'], headers=headers, method='POST')
            opener = urllib.request.build_opener(_NoRedirectHandler())
            with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
                code = response.getcode()
                return {'code': code, 'detail': '', 'retry_after': None}
        except urllib.error.HTTPError as error:
            try:
                detail = error.read(200).decode('utf-8', errors='replace') if error.code not in (429,) and error.code < 500 else ''
            finally:
                error.close()
            return {
                'code': error.code,
                'detail': redact(detail),
                'retry_after': _retry_after_seconds(error.headers.get('Retry-After')),
            }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeEncodeError) as error:
            return {'code': None, 'detail': redact(str(error)), 'retry_after': None}

    def _run(self):
        retry_number = 0
        while not self._closed.is_set():
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            with self._active_lock:
                self._active_item = item
            try:
                while not self._closed.is_set():
                    if item['cancel'].is_set():
                        self.on_log("Discarded queued retry for %s" % item['event_type'])
                        retry_number = 0
                        break
                    if event_expired(item['event_type'], item['queued_at']):
                        self.on_log("Discarded expired event %s" % item['event_type'])
                        self.on_status('expired')
                        retry_number = 0
                        break
                    result = self._send_attempt(item)
                    code = result['code']
                    if code is not None and 200 <= code < 300:
                        self.on_status(str(code))
                        self.on_log("Delivered %s (%d)" % (item['event_type'], code))
                        retry_number = 0
                        break
                    if code == 410:
                        self._disabled_by_receiver.set()
                        self.on_status('410 — disabled')
                        self.on_log("Receiver returned 410; disabling webhooks")
                        self.clear()
                        self.on_gone()
                        retry_number = 0
                        break
                    if code == 429 or code is not None and code >= 500 or code is None:
                        retry_number += 1
                        delay = retry_delay(retry_number - 1, result['retry_after'])
                        self.on_status("retrying (%d)" % retry_number)
                        self.on_log("Retrying %s after %.1f s (%s)" %
                                    (item['event_type'], delay, code if code is not None else result['detail']))
                        if item['cancel'].wait(delay):
                            self.on_log("Discarded queued retry for %s" % item['event_type'])
                            retry_number = 0
                            break
                        if self._closed.is_set():
                            break
                        continue
                    response_detail = result['detail'][:200]
                    self.on_log("Dropped %s (%d): %s" %
                                (item['event_type'], code, response_detail))
                    self.on_status("%d — dropped" % code)
                    retry_number = 0
                    break
            finally:
                with self._active_lock:
                    if self._active_item is item:
                        self._active_item = None
                self._queue.task_done()
