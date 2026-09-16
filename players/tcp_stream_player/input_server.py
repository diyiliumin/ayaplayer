#!/usr/bin/env python3
import sys
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

# 输出目录
OUT_DIR = os.environ.get("OUT_DIR", "/tmp/ts_stream_recv")

# 确保目录存在
os.makedirs(OUT_DIR, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        if self.path != "/stream":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        te = self.headers.get("Transfer-Encoding", "").lower()

        print(f"\n=== POST CL={content_length} TE={te} ===", file=sys.stderr)

        # ★★★ 按时间戳命名 ★★★
        timestamp = int(time.time())
        out_file = os.path.join(OUT_DIR, f"{timestamp}.ts")

        total = 0
        try:
            with open(out_file, "wb") as f:
                if te == "chunked":
                    total = self._read_chunked(f)
                elif content_length > 0:
                    total = self._read_fixed(f, content_length)
                else:
                    total = self._read_until_eof(f)
        except Exception as e:
            print(f"❌ {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

        print(f"=== 结束: {total} bytes → {out_file} ===\n", file=sys.stderr)

        try:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
        except BrokenPipeError:
            pass

    def _read_chunked(self, f):
        """严格按 chunked 规范读"""
        total = 0
        while True:
            line = self.rfile.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                size = int(line.split(b';')[0], 16)
            except ValueError:
                print(f"⚠️ 无效 chunk size: {line!r}", file=sys.stderr)
                break

            if size == 0:
                while True:
                    t = self.rfile.readline()
                    if t in (b'\r\n', b'\n', b''):
                        break
                break

            remaining = size
            while remaining > 0:
                data = self.rfile.read(remaining)
                if not data:
                    return total
                f.write(data)
                f.flush()
                total += len(data)
                remaining -= len(data)

            crlf = self.rfile.read(2)
            if crlf != b'\r\n':
                print(f"⚠️ 期望 CRLF，得到: {crlf!r}", file=sys.stderr)

            print(f"  📦 chunk {size} bytes (total: {total})", file=sys.stderr)

        return total

    def _read_fixed(self, f, length):
        total = 0
        while total < length:
            data = self.rfile.read(min(length - total, 32 * 1024))
            if not data:
                break
            f.write(data)
            f.flush()
            total += len(data)
        return total

    def _read_until_eof(self, f):
        total = 0
        while True:
            data = self.rfile.read(32 * 1024)
            if not data:
                break
            f.write(data)
            f.flush()
            total += len(data)
        return total

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 10722
    print(f"📥 服务: http://127.0.0.1:{port}/stream", file=sys.stderr)
    print(f"   输出目录: {OUT_DIR}", file=sys.stderr)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
