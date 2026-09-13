"""Minimal dependency-free WebSocket client (stdlib only)."""

import base64
import os
import socket
import ssl
import struct
from urllib.parse import urlparse


class WebSocket:
    def __init__(self, url):
        u = urlparse(url)
        if u.scheme not in ("ws", "wss"):
            raise ValueError("只支持 ws:// 或 wss://")
        self.host = u.hostname
        self.port = u.port or (443 if u.scheme == "wss" else 80)
        self.path = u.path or "/"
        if u.query:
            self.path += "?" + u.query
        self.scheme = u.scheme
        self.sock = None

    def connect(self, timeout=10):
        s = socket.create_connection((self.host, self.port), timeout=timeout)
        if self.scheme == "wss":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        self.sock = s

        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET {} HTTP/1.1\r\n"
            "Host: {}:{}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).format(self.path, self.host, self.port, key)
        self.sock.sendall(req.encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("握手期间连接关闭")
            resp += chunk
        head = resp.split(b"\r\n\r\n", 1)[0]
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise ConnectionError("握手失败: " + status.decode(errors="replace"))

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        self._send_frame(0x1, data)

    def recv(self):
        """返回文本/二进制帧的 payload；收到 close 时返回 None。"""
        while True:
            header = self._read_exact(2)
            b1, b2 = header[0], header[1]
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            length = b2 & 0x7F

            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]

            mask = self._read_exact(4) if masked else None
            payload = self._read_exact(length)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

            if opcode == 0x8:
                return None
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            return payload

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    def _send_frame(self, opcode, payload):
        mask = os.urandom(4)
        header = bytes([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", length)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + masked)

    def _read_exact(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("连接关闭")
            data += chunk
        return data
