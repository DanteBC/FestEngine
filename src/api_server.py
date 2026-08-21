import http.server
import socketserver
import json
import threading
import logging

# Configure basic logging to suppress the request logs unless requested
class SilentHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.main_window = kwargs.pop('main_window')
        self.extra_columns = kwargs.pop('extra_columns')
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/current_show':
            row = self.main_window.grid.GetGridCursorRow()
            num_rows = self.main_window.grid.GetNumberRows()
            
            def get_prog_data(r):
                if 0 <= r < num_rows:
                    num = self.main_window.get_num(r)
                    data = {"num": num}
                    # Add extra columns if data exists for this num
                    if num in self.main_window.data:
                        row_data = self.main_window.data[num]
                        for col in self.extra_columns:
                            data[col] = row_data.get(col)
                    return data
                return None

            data = {
                "previous": get_prog_data(row - 1),
                "current": get_prog_data(row),
                "next": get_prog_data(row + 1)
            }
            
            # Send response with explicit UTF-8 encoding for JSON content
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            # Ensure_ascii=False ensures non-ASCII characters (like Cyrillic) are preserved
            response_body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.wfile.write(response_body)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Override to suppress logging if configured
        if self.server.log_enabled:
            super().log_message(format, *args)

class APIServer(threading.Thread):
    def __init__(self, main_window, port=8000, log_enabled=False, extra_columns=None):
        super().__init__()
        self.main_window = main_window
        self.port = port
        self.log_enabled = log_enabled
        self.extra_columns = extra_columns or []
        self.daemon = True
        self.httpd = None
        self._shutdown_event = threading.Event()

    def run(self):
        class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            allow_reuse_address = True  # Allow immediate port reuse
            
            def __init__(self, server_address, RequestHandlerClass, log_enabled):
                super().__init__(server_address, RequestHandlerClass)
                self.log_enabled = log_enabled
                # Set socket timeout to allow checking shutdown event
                self.socket.settimeout(0.5)

        server_address = ('127.0.0.1', self.port)
        self.httpd = ThreadedHTTPServer(server_address, 
                                        lambda *args: SilentHTTPRequestHandler(*args, main_window=self.main_window, extra_columns=self.extra_columns),
                                        self.log_enabled)
        
        while not self._shutdown_event.is_set():
            try:
                self.httpd.handle_request()
            except socketserver.socket.timeout:
                continue

    def stop(self):
        self._shutdown_event.set()
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
