# Kernel API 文档

## 概述

Kernel 是播放器控制中枢，通过 **DBus Session Bus** 暴露接口。所有 UI（终端、Web、移动端）通过 DBus 信号与 Kernel 通信。

---

## DBus 接口

| 项目 | 值 |
|------|-----|
| **总线** | Session Bus |
| **接口名** | `com.ayaplayer.Interface` |
| **状态路径** | `/com/ayaplayer/Status` |
| **控制路径** | `/com/ayaplayer/Control` |

---

## 1. 状态信号（Kernel → UI）

### `StatusChanged`

Kernel 广播当前播放状态。UI 监听此信号更新界面。

**信号路径**：`/com/ayaplayer/Status`
**信号名**：`StatusChanged`

**参数（按顺序）**：

| # | 类型 | 名称 | 说明 |
|---|------|------|------|
| 1 | `int32` | `pid` | 播放器进程 PID，0 表示无播放 |
| 2 | `string` | `title` | 歌曲标题 |
| 3 | `string` | `cover` | 封面路径（本地）或 URL |
| 4 | `int32` | `songleft` | 剩余播放次数 |
| 5 | `boolean` | `paused` | 是否暂停 |

**触发时机**：
- 切歌
- 暂停/继续
- 播放次数改变
- UI 启动时（响应 `ui_started`）

**示例**：

```
path=/com/ayaplayer/Status
interface=com.ayaplayer.Interface
member=StatusChanged
   int32 12345
   string "01 - 虚空の夢 - ak+q、Sennzai"
   string "http://i1.hdslb.com/bfs/archive/xxx.png"
   int32 2
   boolean false
```

---

## 2. 控制信号（UI → Kernel）

### `Control`

UI 发送控制命令给 Kernel。

**信号路径**：`/com/ayaplayer/Control`
**信号名**：`Control`

**参数（按顺序）**：

| # | 类型 | 名称 | 说明 |
|---|------|------|------|
| 1 | `string` | `action` | 命令类型（见下表） |
| 2 | `string` | `data` | 命令参数 |

---

### Action 列表

| Action | Data | 说明 |
|--------|------|------|
| `number` | `"0"` ~ `"8"` | 设置播放次数（实际次数 = data + 1） |
| `pause` | `"true"` / `"false"` | 暂停 / 继续 |
| `skip` | `""` | 跳过当前歌曲 |
| `quit` | `""` | 退出播放器 |
| `ui_started` | `"<pid>"` | UI 启动，请求 Kernel 广播当前状态 |
| `status` | JSON 字符串 | （保留）状态同步 |

---

## 3. 使用示例

### 3.1 Bash（dbus-send）

**发送 UI 启动信号**：

```bash
dbus-send --session \
    --type=signal \
    /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control \
    "string:ui_started" \
    "string:$$"
```

**设置播放次数为 3**：

```bash
dbus-send --session \
    --type=signal \
    /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control \
    "string:number" \
    "string:2"
```

**暂停**：

```bash
dbus-send --session \
    --type=signal \
    /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control \
    "string:pause" \
    "string:true"
```

**跳过**：

```bash
dbus-send --session \
    --type=signal \
    /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control \
    "string:skip" \
    "string:"
```

**退出**：

```bash
dbus-send --session \
    --type=signal \
    /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control \
    "string:quit" \
    "string:"
```

**监听状态**：

```bash
dbus-monitor --session "type='signal',interface='com.ayaplayer.Interface',member='StatusChanged'"
```

---

### 3.2 Python（dbus-python）

**发送控制信号**：

```python
import subprocess
import os

def send_control(action, data=""):
    subprocess.run([
        'dbus-send', '--session',
        '--type=signal',
        '/com/ayaplayer/Control',
        'com.ayaplayer.Interface.Control',
        f'string:{action}',
        f'string:{data}'
    ], stderr=subprocess.DEVNULL, check=False)

# 设置次数
send_control('number', '2')

# 暂停
send_control('pause', 'true')

# 跳过
send_control('skip')

# 退出
send_control('quit')

# UI 启动
send_control('ui_started', str(os.getpid()))
```

**监听状态**：

```python
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

def on_status_changed(pid, title, cover, songleft, paused):
    print(f"PID: {pid}")
    print(f"标题: {title}")
    print(f"封面: {cover}")
    print(f"剩余: {songleft}")
    print(f"暂停: {paused}")

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()

bus.add_signal_receiver(
    on_status_changed,
    dbus_interface='com.ayaplayer.Interface',
    signal_name='StatusChanged',
    path='/com/ayaplayer/Status'
)

loop = GLib.MainLoop()
loop.run()
```

---

### 3.3 Go（godbus/v5）

**发送控制信号**：

```go
import "github.com/godbus/dbus/v5"

conn, _ := dbus.SessionBus()

func sendControl(action, data string) error {
    return conn.Emit(
        "/com/ayaplayer/Control",
        "com.ayaplayer.Interface.Control",
        action,
        data,
    )
}

// 使用
sendControl("number", "2")
sendControl("pause", "true")
sendControl("skip", "")
sendControl("quit", "")
```

**监听状态**：

```go
import (
    "github.com/godbus/dbus/v5"
    "log"
)

conn, _ := dbus.SessionBus()

conn.AddMatchSignal(
    dbus.WithMatchInterface("com.ayaplayer.Interface"),
    dbus.WithMatchMember("StatusChanged"),
    dbus.WithMatchObjectPath("/com/ayaplayer/Status"),
)

c := make(chan *dbus.Signal, 10)
conn.Signal(c)

for sig := range c {
    if sig.Name != "com.ayaplayer.Interface.StatusChanged" {
        continue
    }
    body := sig.Body
    pid := body[0].(int32)
    title := body[1].(string)
    cover := body[2].(string)
    songleft := body[3].(int32)
    paused := body[4].(bool)
    
    log.Printf("🎵 %s  [%d次]  暂停=%v", title, songleft, paused)
}
```

---

### 3.4 JavaScript（Web UI）

Web UI 不能直接访问 DBus，需要通过后端代理。参考 `webui_by_ds` 的实现：

**后端（Go + WebSocket）**：

```go
// 监听 DBus → 通过 WebSocket 推送
// WebSocket → 接收前端命令 → 发送 DBus 信号
```

**前端（JS）**：

```javascript
const ws = new WebSocket('wss://music.ymodatabase.top/ws');

// 接收状态
ws.onmessage = (e) => {
    const state = JSON.parse(e.data);
    console.log(state.title, state.paused);
};

// 发送控制
ws.send(JSON.stringify({ action: 'pause', data: 'true' }));
ws.send(JSON.stringify({ action: 'skip', data: '' }));
ws.send(JSON.stringify({ action: 'number', data: '2' }));
```

---

## 4. 完整工作流

```
┌─────────────┐                    ┌─────────────┐
│   Kernel    │                    │     UI      │
│ (Bash)      │                    │ (Python/Go/Web) │
└──────┬──────┘                    └──────┬──────┘
       │                                  │
       │  ◄──── Control (ui_started) ─────┤
       │                                  │
       │  ───── StatusChanged ────────►  │
       │                                  │
       │  ◄──── Control (number) ─────────┤
       │                                  │
       │  ───── StatusChanged ────────►  │
       │                                  │
       │  ◄──── Control (pause) ──────────┤
       │                                  │
       │  ───── StatusChanged ────────►  │
       │                                  │
       │  ◄──── Control (skip) ───────────┤
       │                                  │
       │  ───── StatusChanged ────────►  │
       │                                  │
       │  ◄──── Control (quit) ───────────┤
       │                                  │
```

---

## 5. 状态字段详解

### `pid` (int32)

- **0**：没有正在播放的歌曲
- **> 0**：播放器进程 PID

### `title` (string)

- 歌曲标题
- 可能为空字符串

### `cover` (string)

- **HTTP URL**：`http://i1.hdslb.com/...`
- **本地路径**：`/mnt/windows/.../image.jpg`
- **空字符串**：无封面

### `songleft` (int32)

- 剩余播放次数（不含当前正在播的）
- **0**：播完这首歌就切下一首
- **N**：还会再播 N 次

### `paused` (boolean)

- **true**：已暂停（SIGSTOP）
- **false**：播放中

---

## 6. 错误处理

| 情况 | 表现 |
|------|------|
| Kernel 未启动 | DBus 信号没人发送，UI 一直显示"等待播放..." |
| UI 未发 `ui_started` | 收不到初始状态，需要等下次 `StatusChanged` |
| DBus 连接失败 | `dbus.SessionBus()` 报错 |
| 发送信号失败 | `dbus-send` 返回非 0（通常忽略） |

**建议**：
- UI 启动时立即发 `ui_started`
- UI 监听 `StatusChanged` 更新界面
- UI 退出时不需要通知 Kernel（Kernel 会自己清理）

---

## 7. 版本兼容

| 版本 | 变化 |
|------|------|
| v1 | 基础信号：`StatusChanged`、`Control` |
| v2（未来） | 可能增加 `Progress`、`Volume`、`Playlist` 等信号 |

---

## 8. 快速测试

**终端 1：监听状态**

```bash
dbus-monitor --session "type='signal',interface='com.ayaplayer.Interface'"
```

**终端 2：发送命令**

```bash
# UI 启动
dbus-send --session --type=signal /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control string:ui_started string:$$

# 设置播放 3 次
dbus-send --session --type=signal /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control string:number string:2

# 暂停
dbus-send --session --type=signal /com/ayaplayer/Control \
    com.ayaplayer.Interface.Control string:pause string:true
```

**终端 1 应该能看到 `StatusChanged` 信号。**

---

## 9. 接口汇总

```
接口: com.ayaplayer.Interface

状态路径: /com/ayaplayer/Status
  └── 信号: StatusChanged(int32 pid, string title, string cover, int32 songleft, boolean paused)

控制路径: /com/ayaplayer/Control
  └── 信号: Control(string action, string data)
      ├── action="number"     data="0"~"8"
      ├── action="pause"      data="true"/"false"
      ├── action="skip"       data=""
      ├── action="quit"       data=""
      └── action="ui_started" data="<pid>"
```

---

**这就是你的 Kernel API 完整文档。任何 UI 只要实现这两个信号，就能和 Kernel 通信。**
