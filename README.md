# ayaplayer

> 一个自由的播放器。
> 试着用简单的方式实现简单的功能。

---

## 对于用户

### 第一步：搞懂这个项目是干什么的

先**浏览一下项目目录**，搞清楚每个文件夹是做什么的。这个过程可能有点复杂，建议结合 `kernel/head` 里的代码理解。

**项目结构速查：**

```
biliCLI/
├── data_sources/          # 播放源插件
├── players/               # 播放器插件
├── kernel/                # 调度核心
├── gateway/               # 数据网关
├── song_adders/           # 选歌器
├── user_interfaces/       # UI
├── distros/               # 发行版
├── to_be_played/          # 播放列表
├── choose_song            # 数据源选择器
├── healthcheck-all        # 健康检查
└── launch                 # 启动脚本
```

**文件夹功能速查：**

| 文件夹 | 作用 |
|--------|------|
| `data_sources/` | 播放源插件（B站缓存、B站在线、本地文件、Steam音乐库） |
| `players/` | 播放器插件（ffplay 本地播放、tcp_stream_player 流式推流） |
| `kernel/` | 调度核心（Shell 写的播放器内核） |
| `gateway/` | 数据网关（本地文件 / HTTP 远端 / 多级级联） |
| `song_adders/` | 选歌器（TUI 界面，生成播放列表） |
| `user_interfaces/` | 可视化 UI（终端ASCII、curses面板、GTK4桌面App、浏览器） |
| `distros/` | 发行版（不同组件组合的启动方式） |
| `to_be_played/` | 播放列表存放（`playlist.json` 一次性列表，`loop_list/` 循环列表） |

### 第二步：删除你不需要的插件

**以文件夹为单位**，删掉你不需要的插件。

- 不用 B 站？删 `data_sources/bilicache` 和 `data_sources/biliweb`
- 不用 Steam？删 `data_sources/steam`
- 不用流式推流？删 `players/tcp_stream_player`
- 不用桌面 App？删 `user_interfaces/wayland_app`

**删完之后，剩下的就是你自己的播放器。**

### 第三步：健康检查

```bash
./healthcheck-all
```

它会扫描所有 `healthcheck` 文件，逐个执行，生成报告。

根据报告提示，完成剩余插件的**配置与编译**。

### 已提供的插件列表

**数据源：**
- `bilicache` — B站缓存
- `biliweb` — B站在线
- `local` — 本地文件
- `steam` — Steam音乐库
- `zz_bilicache_fallback` — B站缓存兜底

**播放器：**
- `ffplay` — 本地播放
- `tcp_stream_player` — 流式推流

**UI：**
- `fakehexwithascii` — 终端 ASCII 可视化
- `dashboard.py` — curses 监控面板
- `wayland_app` — GTK4 桌面 App
- `webui_by_ds` — 浏览器 UI
- `tui_use_tcp` — TCP 流 TUI

### 你应该的工作流

```bash
# 1. 选择数据源
./choose_song

# 2. 启动播放系统
./launch

# 3. 控制播放
# 在 fakehex 界面里按 1-9 设置重复次数，p 暂停，x 跳过，q 退出
```

---

## 加歌器使用指南

加歌器负责往播放列表里加歌。它和播放源一一对应——每个播放源都有一个加歌器。

### 已提供的加歌器

| 加歌器 | 对应播放源 | 作用 |
|--------|-----------|------|
| `bili_cache_select_song` | `bilicache` | 从 B 站缓存里选歌 |
| `bili_web_select_song` | `biliweb` | 从 B 站网页链接里选歌 |
| `local_select_song` | `local` | 从本地文件里选歌 |
| `steam_select_song` | `steam` | 从 Steam 音乐库里选歌 |

### 统一入口：`choose_song`

```bash
./choose_song
```

它会自动扫描 `song_adders/` 下的所有加歌器，显示一个列表，让你选一个运行。

```
🎵 歌曲添加器
   选择一个数据源
   ──────────────────────────────────────
  ▶ 📦  B站缓存    bili_cache_select_song
    🌐  B站网页    bili_web_select_song
    📁  本地文件    local_select_song
    🎮  Steam音乐  steam_select_song
   ──────────────────────────────────────
  h/k ↑ 上 · j/l ↓ 下 · Enter 运行 · q 退出
```

### 加歌器的工作流

```bash
# 1. 选择加歌器
./choose_song

# 2. 在 TUI 里浏览、搜索、选择
#    j/k      上下移动
#    h/l      收起/展开
#    /        搜索
#    Enter/a  添加到播放列表
#    d        清空播放列表
#    r        打乱播放列表
#    v        编辑播放列表（用 nvim 编辑 playlist.json）
#    s        编辑扫描源（用 nvim 编辑 urls.txt / config.json）
#    b        重新构建 tree.json
#    q        退出

# 3. 加完之后，回到主流程
./launch
```

**注意 `v` 和 `s` 的区别：**

- `v` 编辑的是**播放列表**（`playlist.json`）
- `s` 编辑的是**扫描源**（`urls.txt` / `config.json`）

一个是"我要听什么"，一个是"我从哪里找歌"。

### 加歌器与播放源的关系

**加歌器写 JSON，播放源读 JSON。**

加歌器写进去的 JSON，播放源必须能读懂。
播放源能读懂的 JSON，加歌器必须能写出来。

**JSON 字段：**

```json
{
  "scheme": "bilicache",     // 必须，声明属于哪个播放源
  "title": "七里香",          // 建议，用于显示
  "category": "叶惠美",       // 建议，用于显示
  "cid": 123456,             // 播放源自定义
  "bvid": "BV1xx411c7mD",    // 播放源自定义
  "p": 1                     // 播放源自定义
}
```

### 自己写一个加歌器

如果你想加一个新的播放源，你需要**同时写一个加歌器**。

**要求：**

1. 在 `song_adders/` 下创建一个目录，例如 `my_select_song/`
2. 写一个 `run` 脚本作为入口
3. 生成的 JSON 必须带 `scheme` 字段，且该 `scheme` 必须和你的播放源对应
4. 可以直接复用 `bili_select_song_tui`，也可以自己写一个新的 TUI

**复用现成 TUI 的方式：**

```bash
# 在 song_adders/my_select_song/ 下
ln -sf ../bili_select_song_tui ./bili_select_song_tui
cat > run << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
ln -sf ./tree.json ./bili_select_song_tui/tree.json
./bili_select_song_tui/tui
EOF
chmod +x run
```

然后你只需要准备一个 `tree.json`，格式和其他加歌器一致。

### 加歌器的本质

> **加歌器就是"把外部内容变成播放列表条目"的工具。**

它做三件事：
1. 从某个来源获取内容（B站缓存、网页、本地文件、Steam）
2. 让用户选择
3. 写入 `playlist.json`

**就这么简单。**

---

## 对于插件开发者

本项目有**初等插件系统**。

### UI 开发者

你需要实现：

- 订阅 DBus 的 `StatusChanged` 信号（接收状态）
- 发送 DBus 的 `Control` 信号（发送控制）

**接口：**

```
Status: com.ayaplayer.Interface /com/ayaplayer/Status StatusChanged
  参数: int32 pid, string title, string cover, int32 songleft, boolean paused

Control: com.ayaplayer.Interface /com/ayaplayer/Control Control
  参数: string action, string data
  action: number | pause | skip | quit | ui_started
```

**要求：**
- 无状态，从 DBus 读
- 启动时发送 `ui_started`
- 可以随时关掉，内核不受影响

### 播放源开发者

你需要实现**三个必须接口**和**两个可选接口**：

**必须：**

```bash
# 1. 声明支持的 scheme
plugin --support
# 输出：bilicache

# 2. 检查能否处理这个 JSON（环境 + 这首歌）
plugin --canwork '{"cid":123,"scheme":"bilicache"}'
# stdout: canwork 或 cannotwork
# 退出码: 0（可以）或 1（不可以）

# 3. 输出音频流到 stdout
plugin --getrawdata '{"cid":123,"scheme":"bilicache"}'
# 输出：原始音频流
```

**可选：**

```bash
# 4. 输出封面路径
plugin --cover '{"cid":123,"scheme":"bilicache"}'
# 输出：/path/to/cover.jpg 或 URL

# 5. 输出显示名称
plugin --title '{"cid":123,"scheme":"bilicache"}'
# 输出：周杰伦 - 七里香
```

**要求：**

- 需要一个**独特的 scheme**（不能和其他插件冲突）
- 需要实现对应的**加歌器**（可以复用现成 TUI，也可以自己起一个新的）
- `run` 作为入口

**加歌器与播放源的对应关系：**

加歌器负责写 JSON 到播放列表，播放源负责读 JSON 并播放。
两者必须能**互相解析**。

**JSON 字段：**

| 字段 | 必填 | 用途 |
|------|------|------|
| `scheme` | ✅ 必须 | 内核靠它找到播放源 |
| `title` | 建议 | UI 显示用 |
| `category` | 建议 | UI 显示用 |
| 其他 | 自定义 | 加歌器和播放源自行约定 |

**内核只关心 `scheme`。其他字段全部由你的加歌器和播放源自行约定。**

### 播放器开发者

**无所谓是否 fork**，但要注意：

- player **只能以单首歌为单位**
- kernel **每播一首歌都会启动一次**
- **播完一首歌之后必须主动退出**

**如需常驻服务**，可以用 tmp 文件系统或 FIFO 桥接，或者你有自己的 hack。

**接口：**

```bash
# 从 stdin 读音频流，播放
exec ffplay -v 0 -nostats -nodisp -autoexit -i pipe:0 "$@"
```

**就这一件事。其他什么都不用管。**

---

## gateway：数据网关

gateway 是整个系统的**数据访问层**。它把"播放列表在哪"这个问题，从内核里剥离出来，变成了一个可配置的"跳转规则"。

### 能力

- **切换歌单源**：本地文件 / HTTP 远端 / 多级级联
- **简单数据库操作**：读、写、追加、弹出、清空、打乱
- **远程操作**：通过 HTTP 访问远端的 gateway

### 切换歌单源

`gateway/source_list.txt` 里每行是一个数据源：

```txt
# 第1个有效行 = 主数据源
http://your-server.com:8787
file:///home/user/playlist.json
```

- `file://` — 本地文件
- `http://` — 转发到远端 gateway

**内核不关心数据在哪。它只跟 gateway 说话。**

### 简单数据库操作

```bash
# 读取
gateway read              # 读全部
gateway first             # 读第一行
gateway count             # 统计行数

# 写入
gateway append '{"..."}'  # 追加到末尾
gateway push '{"..."}'    # 插到顶部
gateway pop               # 弹出第一行
gateway finish '{"..."}'  # 匹配顶部则删除（幂等）
gateway clear             # 清空
gateway shuffle           # 打乱

# 编辑
gateway checkout          # 下载到本地
gateway commit            # 上传回远端
gateway diff              # 显示差异
gateway status            # 查看状态
```

**所有的操作对本地和远端是透明的。**

### 远程操作

启动 HTTP 服务：

```bash
gateway --daemon start
# 访问 http://localhost:8787/dashboard
```

它会：
- 把本地操作暴露成 HTTP API
- 提供 Dashboard 查看请求历史
- 支持被另一个 gateway 转发

### 多级级联

```
本地内核 → 本地 gateway
              ↓ 转发
        远端 gateway A
              ↓ 转发
        远端 gateway B
              ↓
        最终数据源
```

**每一级只知道"下一个是谁"，不需要知道全局拓扑。**

---

## 分布式实现情况

目前支持：

- **内核可以向公网请求歌单**：通过 `gateway` 的 HTTP 远端模式
- **内核可以向公网推送音频流**：通过 `tcp_stream_player` 的分片推流

**其他还不行。**

### 可以这样配置

**场景1：纯本地**

```bash
# distros/active -> distro_simple
./launch
```

**场景2：从公网拉歌单**

```bash
# gateway/source_list.txt
http://your-server.com:8787
file:///home/user/playlist.json

./launch
```

**场景3：向公网推音频流**

```bash
# players/tcp_stream_player/source_list.txt
http://your-server.com:10722

# 内核把音频分片推送到公网服务器
# 然后在任意地方用浏览器访问 http://your-server.com:10723
./launch
```

**场景4：本地拉 + 公网推**

```bash
# gateway/source_list.txt
http://your-server.com:8787

# players/tcp_stream_player/source_list.txt
http://your-server.com:10722

# 歌单从公网拉，音频往公网推
./launch
```

---

## License

GPL-2.0

