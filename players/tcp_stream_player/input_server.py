#!/usr/bin/env python3
import sys
import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ★★★ 输出目录（和 bash 版一致）★★★
OUT_DIR = os.environ.get("OUT_DIR", "/tmp/ts_stream")
os.makedirs(OUT_DIR, exist_ok=True)

# 启动时清理旧文件（和 bash 版一致）
for f in os.listdir(OUT_DIR):
    if f.endswith(".ts"):
        try:
            os.remove(os.path.join(OUT_DIR, f))
        except OSError:
            pass

# 时间戳前缀（和 bash 版一致）
PREFIX = int(time.time())

# 计数器（防止同秒覆盖）
_counter = 0
_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        global _counter

        if self.path not in ("/stream", "/segment"):
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        te = self.headers.get("Transfer-Encoding", "").lower()

        # ★★★ 文件名：前缀_序号.ts（和 bash 版一致）★★★
        with _lock:
            idx = _counter
            _counter += 1

        out_file = os.path.join(OUT_DIR, f"{PREFIX}_{idx:05d}.ts")

        print(f"\n=== POST {self.path} CL={content_length} TE={te} ===", file=sys.stderr)
        print(f"   → {out_file}", file=sys.stderr)

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

        print(f"=== 结束: {total} bytes ===\n", file=sys.stderr)

        try:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
        except BrokenPipeError:
            pass

    def _read_chunked(self, f):
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
            self.rfile.read(2)

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
    print(f"   前缀: {PREFIX}", file=sys.stderr)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
