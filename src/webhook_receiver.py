import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from webhook_sender import sign_payload, validate_secret


class WebhookReceiver(HTTPServer):
    def __init__(self, address, handler, secret, responses):
        super().__init__(address, handler)
        self.secret = secret
        self.responses = list(responses)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length)
        if self.server.secret:
            msg_id = self.headers.get('webhook-id', '')
            timestamp = self.headers.get('webhook-timestamp', '')
            received = self.headers.get('webhook-signature', '')
            try:
                expected = sign_payload(self.server.secret, msg_id, int(timestamp), body)
            except (TypeError, ValueError):
                expected = ''
            if not msg_id or not expected or not hmac.compare_digest(expected, received):
                self.send_response(401)
                self.end_headers()
                return

        try:
            event = json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            self.send_response(400)
            self.end_headers()
            return

        print(json.dumps(event, ensure_ascii=False))
        code = self.server.responses.pop(0) if self.server.responses else 200
        self.send_response(code)
        self.end_headers()

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser(description="Local Standard Webhooks test receiver")
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--responses', default='200',
                        help='Comma-separated response codes, e.g. 503,200 to test retries')
    args = parser.parse_args()

    secret = os.environ.get('FESTENGINE_WEBHOOK_SECRET', '')
    validate_secret(secret)
    responses = [int(code.strip()) for code in args.responses.split(',') if code.strip()]
    server = WebhookReceiver((args.host, args.port), Handler, secret, responses)
    print("Listening on http://%s:%d/" % (args.host, args.port))
    if secret:
        print("Signature verification enabled")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
