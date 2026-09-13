#!/usr/bin/env python3
"""
gateway_daemon.py - HTTP 转发层 + 请求历史记录
"""

import os
import sys
import json
import time
import subprocess
import threading
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GATEWAY = os.path.join(SCRIPT_DIR, "gateway.sh")
HISTORY_FILE = "/tmp/gateway_history.jsonl"
MAX_HISTORY = 1000

# ============================================
# 请求历史（内存 + 文件）
# ============================================
history_lock = threading.Lock()
history = deque(maxlen=MAX_HISTORY)

def load_history():
    """启动时加载历史"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        history.append(json.loads(line))
        except:
            pass

def save_history(entry):
    """追加到文件"""
    try:
        with open(HISTORY_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except:
        pass

def record_request(method, path, args, output, code, duration_ms):
    """记录一次请求"""
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
        "method": method,
        "path": path,
        "args": args,
        "output": output[:500],  # 截断
        "code": code,
        "duration_ms": round(duration_ms, 2),
        "source_ip": None,  # 填充
    }
    with history_lock:
        history.append(entry)
    save_history(entry)
    return entry


class GatewayHandler(BaseHTTPRequestHandler):
    def _call_gateway(self, *args):
        result = subprocess.run(
            [GATEWAY] + list(args),
            capture_output=True,
            text=True
        )
        return result.stdout, result.returncode
    
    def _send(self, code, body, content_type="text/plain; charset=utf-8"):
        if not (100 <= code <= 599):
            code = 500
        
        body_bytes = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body_bytes)
    
    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length).decode()
        return ""
    
    def _handle(self, method):
        parsed = urlparse(self.path)
        path = parsed.path.strip("/")
        query = parsed.query
        
        # ★★★ Dashboard 特殊路径 ★★★
        if path == "dashboard" or path == "":
            self._send(200, self._dashboard_html(), "text/html; charset=utf-8")
            return
        
        if path == "history":
            self._send(200, self._history_json(), "application/json; charset=utf-8")
            return
        
        if path == "stats":
            self._send(200, self._stats_json(), "application/json; charset=utf-8")
            return
        
        if path == "clear_history":
            with history_lock:
                history.clear()
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            self._send(200, '{"status":"ok"}', "application/json")
            return

        # ★★★ 特殊处理 /write ★★★
        if path == "write" and method == "POST":
            body = self._read_body()
            try:
                args = json.loads(body)
                if isinstance(args, list) and len(args) > 0:
                    content = args[0]
                else:
                    content = body
            except:
                content = body
            
            # 调用 gateway.sh write（从 stdin 读）
            start = time.time()
            result = subprocess.run(
                [GATEWAY, "write"],
                input=content,
                capture_output=True,
                text=True
            )
            duration_ms = (time.time() - start) * 1000
            
            http_code = 200 if result.returncode == 0 else 400
            
            # 记录历史
            entry = record_request("POST", path, [f"<{len(content)} bytes>"], 
                                  result.stdout, http_code, duration_ms)
            entry["source_ip"] = self.client_address[0]
            
            self._send(http_code, result.stdout)
            return
        
        # ★★★ 正常命令转发 ★★★
        args = []
        body = ""
        
        if method == "POST":
            body = self._read_body()
            if body:
                try:
                    args = json.loads(body)
                    if not isinstance(args, list):
                        args = [str(args)]
                    args = [str(a) for a in args]
                except json.JSONDecodeError:
                    args = [body]
        else:
            if query:
                for pair in query.split("&"):
                    if "=" in pair:
                        _, val = pair.split("=", 1)
                        args.append(val)
                    else:
                        args.append(pair)
        
        start = time.time()
        out, code = self._call_gateway(path, *args)
        duration_ms = (time.time() - start) * 1000
        
        http_code = 200 if code == 0 else 400
        
        # ★★★ 记录历史 ★★★
        entry = record_request(method, path, args, out, http_code, duration_ms)
        entry["source_ip"] = self.client_address[0]
        
        self._send(http_code, out)
    
    def do_GET(self):
        self._handle("GET")
    
    def do_POST(self):
        self._handle("POST")
    
    # ============================================
    # Dashboard 页面
    # ============================================
    def _dashboard_html(self):
        return """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>Gateway Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    padding: 20px;
    line-height: 1.5;
}
h1 { color: #58a6ff; margin-bottom: 20px; font-size: 24px; }
h2 { color: #8b949e; margin: 20px 0 10px; font-size: 16px; text-transform: uppercase; letter-spacing: 1px; }
.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 30px;
}
.stat-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
}
.stat-card .label { color: #8b949e; font-size: 12px; text-transform: uppercase; }
.stat-card .value { color: #58a6ff; font-size: 28px; font-weight: 600; margin-top: 4px; }
.stat-card.ok .value { color: #3fb950; }
.stat-card.err .value { color: #f85149; }
table {
    width: 100%;
    border-collapse: collapse;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    overflow: hidden;
}
th, td {
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid #30363d;
    font-size: 13px;
}
th { background: #21262d; color: #8b949e; font-weight: 600; text-transform: uppercase; font-size: 11px; }
tr:last-child td { border-bottom: none; }
tr:hover { background: #1c2128; }
.method { display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 11px; }
.method.GET { background: #1f6feb33; color: #58a6ff; }
.method.POST { background: #3fb95033; color: #3fb950; }
.path { color: #ffa657; font-family: monospace; }
.args { color: #8b949e; font-family: monospace; font-size: 11px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.code { font-weight: 600; }
.code.ok { color: #3fb950; }
.code.err { color: #f85149; }
.duration { color: #8b949e; font-family: monospace; }
.time { color: #6e7681; font-size: 11px; }
.controls { margin-bottom: 20px; display: flex; gap: 10px; align-items: center; }
button {
    background: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
}
button:hover { background: #30363d; }
button.danger { color: #f85149; border-color: #f85149; }
button.danger:hover { background: #f8514922; }
#auto-refresh { color: #3fb950; font-size: 12px; margin-left: auto; }
</style>
</head>
<body>
<h1>🚀 Gateway Dashboard</h1>

<div class="stats" id="stats"></div>

<h2>请求历史</h2>
<div class="controls">
    <button onclick="loadAll()">🔄 刷新</button>
    <button class="danger" onclick="clearHistory()">🗑️ 清空历史</button>
    <span id="auto-refresh">● 每 2 秒自动刷新</span>
</div>

<table>
<thead>
<tr>
    <th>时间</th>
    <th>方法</th>
    <th>命令</th>
    <th>参数</th>
    <th>状态</th>
    <th>耗时</th>
    <th>IP</th>
</tr>
</thead>
<tbody id="history-body"></tbody>
</table>

<script>
async function loadStats() {
    try {
        const r = await fetch('/stats');
        const data = await r.json();
        document.getElementById('stats').innerHTML = `
            <div class="stat-card"><div class="label">总请求</div><div class="value">${data.total}</div></div>
            <div class="stat-card ok"><div class="label">成功</div><div class="value">${data.success}</div></div>
            <div class="stat-card err"><div class="label">失败</div><div class="value">${data.error}</div></div>
            <div class="stat-card"><div class="label">平均耗时</div><div class="value">${data.avg_ms}ms</div></div>
            <div class="stat-card"><div class="label">最常用命令</div><div class="value" style="font-size:18px">${data.top_command || '-'}</div></div>
        `;
    } catch (e) { console.error(e); }
}

async function loadHistory() {
    try {
        const r = await fetch('/history');
        const data = await r.json();
        const tbody = document.getElementById('history-body');
        tbody.innerHTML = data.map(e => `
            <tr>
                <td class="time">${e.time}</td>
                <td><span class="method ${e.method}">${e.method}</span></td>
                <td class="path">${e.path}</td>
                <td class="args" title='${JSON.stringify(e.args)}'>${JSON.stringify(e.args)}</td>
                <td class="code ${e.code === 200 ? 'ok' : 'err'}">${e.code}</td>
                <td class="duration">${e.duration_ms}ms</td>
                <td class="time">${e.source_ip || '-'}</td>
            </tr>
        `).reverse().join('');
    } catch (e) { console.error(e); }
}

async function clearHistory() {
    if (!confirm('确定清空历史？')) return;
    await fetch('/clear_history');
    loadAll();
}

function loadAll() {
    loadStats();
    loadHistory();
}

loadAll();
setInterval(loadAll, 2000);
</script>
</body>
</html>"""
    
    def _history_json(self):
        with history_lock:
            return json.dumps(list(history), ensure_ascii=False)
    
    def _stats_json(self):
        with history_lock:
            entries = list(history)
        
        total = len(entries)
        success = sum(1 for e in entries if e.get('code') == 200)
        error = total - success
        
        durations = [e.get('duration_ms', 0) for e in entries]
        avg_ms = round(sum(durations) / len(durations), 2) if durations else 0
        
        # 最常用命令
        from collections import Counter
        paths = Counter(e.get('path') for e in entries if e.get('path'))
        top_command = paths.most_common(1)[0][0] if paths else None
        
        return json.dumps({
            "total": total,
            "success": success,
            "error": error,
            "avg_ms": avg_ms,
            "top_command": top_command,
        }, ensure_ascii=False)
    
    def log_message(self, format, *args):
        pass


def main():
    load_history()
    
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    server = HTTPServer(("0.0.0.0", port), GatewayHandler)
    print(f"🚀 Gateway daemon 运行在 http://0.0.0.0:{port}", file=sys.stderr)
    print(f"📊 Dashboard: http://localhost:{port}/dashboard", file=sys.stderr)
    print(f"📜 History:   http://localhost:{port}/history", file=sys.stderr)
    print(f"📈 Stats:     http://localhost:{port}/stats", file=sys.stderr)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 关闭", file=sys.stderr)
        server.shutdown()


if __name__ == "__main__":
    main()
