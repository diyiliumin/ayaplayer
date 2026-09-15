#!/usr/bin/env python3
# receive.py
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

FIFO = "/tmp/tcp_stream_player_2.fifo"

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/stream":
            self.send_error(404)
            return

        # 打开 FIFO 写端
        with open(FIFO, "wb") as f:
            while True:
                chunk = self.rfile.read(32 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                f.flush()

        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    print(f"📥 接收服务: http://0.0.0.0:{port}/stream", file=sys.stderr)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
