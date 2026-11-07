"""Exercise the repository's error handler in an isolated loopback nginx process."""
import http.server
import json
import pathlib
import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request


def verify(source: pathlib.Path) -> None:
    text = source.read_text()
    handler = re.search(r"    location @accounting_unavailable \{\n.*?^    \}", text, re.M | re.S)
    assert handler

    class Auth(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(int(self.headers['X-Test-Status']))
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Auth)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    try:
        with tempfile.TemporaryDirectory(prefix='kisco-gateway-test-') as folder:
            path = pathlib.Path(folder)
            config = f'''pid {path}/nginx.pid; error_log {path}/error.log;
events {{ worker_connections 32; }}
http {{ access_log off; server {{ listen 127.0.0.1:{port};
location /bill {{ error_page 500 502 503 504 = @accounting_unavailable;
auth_request /auth; auth_request_set $gateway_auth_status $upstream_status;
proxy_pass http://127.0.0.1:{server.server_port};
}}
location = /auth {{ internal; proxy_pass http://127.0.0.1:{server.server_port};
proxy_set_header X-Test-Status $http_x_test_status; }}
{handler.group()}
}} }}'''
            (path/'nginx.conf').write_text(config)
            process = subprocess.Popen(['nginx', '-p', folder, '-c', str(path/'nginx.conf'), '-g', 'daemon off;'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                time.sleep(0.3)
                assert process.poll() is None, (path/'error.log').read_text()
                for status, expected, code in [(429, 429, 'rate_limited'), (503, 503, 'dependency_unavailable')]:
                    request = urllib.request.Request(f'http://127.0.0.1:{port}/bill', headers={'X-Test-Status': str(status)})
                    try:
                        urllib.request.urlopen(request)
                        raise AssertionError('Authorization failure reached bill endpoint')
                    except urllib.error.HTTPError as response:
                        assert response.code == expected, (status, response.code)
                        assert json.load(response)['error']['code'] == code
                        assert response.headers['Cache-Control'] == 'no-store'
                        if status == 429:
                            assert response.headers['Retry-After'] == '60'
            finally:
                process.terminate()
                process.wait(timeout=5)
    finally:
        server.shutdown()
        server.server_close()
    print('Gateway authentication throttle: 2 cases passed')


if __name__ == '__main__':
    import sys
    verify(pathlib.Path(sys.argv[1]))
