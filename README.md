# biliCLI - B站视频本地管理工具

## 项目简介

biliCLI 是一个基于终端的B站视频本地内容管理工具，可以将下载的B站视频文件组织成结构化目录树，提供美观的TUI界面进行浏览和播放。

测试环境是win11下的wsl，用win11客户端缓存，用wsl运行。其他不知道

## 快速开始

### 环境要求
```bash
# 必需
- Rust (用于编译 buildtree)
- Go 1.20+ (用于编译 TUI)
- Python 3.8+ (用于辅助脚本)
- ffplay (来自 ffmpeg，用于视频播放)
- xxd (用于 fake_hex 显示)

# 可选但推荐
- pkg-config, build-essential
```

### 安装步骤

你应该会收到一个编译好的安装包，如果我居然搞定了一大堆事情上GitHub开源了那你可能需要用下面的命令编译

1. **克隆项目**
```bash
git clone <repository-url>
cd biliCLI
```

2. **编译所有组件**
```bash
# 编译 Rust 扫描器
cd buildtree
cargo build --release

# 编译 Go TUI
cd ../cmd/tui
go build -o mytui

# 编译 C 辅助工具
cd ../..
gcc fake_hex.c -o fake_hex
gcc launcher.c -o launch
```

3. **配置**
编辑 `config.json`，设置视频文件根目录：
```json
{
  "root": "/path/to/your/bilibili/downloads"
}
```

## 使用方法

### 基本流程

1. **首次使用 - 构建索引**

如果你的缓存地址改动过，请先去根目录的config.json修改

```bash
# 方法一：直接运行扫描器
cd buildtree
cargo run --release

# 方法二：通过TUI界面按 'b' 键构建
```

2. **启动TUI界面**
```bash
# 使用启动器（推荐）
./launch

# 或直接运行TUI
./cmd/tui/mytui
```

### TUI快捷键

| 快捷键 | 功能 |
|--------|------|
| **j/k** | 上下移动光标 |
| **h/l** | 折叠/展开节点 |
| **Enter** | 播放选中项 |
| **m** | 切换播放模式（顺序/随机） |
| **/** | 搜索视频 |
| **n** | 跳转到下一个搜索结果 |
| **b** | 重新构建视频索引 |
| **q** | 退出程序 |

### 播放模式
- **顺序播放**：按目录顺序播放
- **随机播放**：打乱顺序播放

### 目录结构说明
```
视频分组 (Group)
├── 视频系列 (Title)
│   ├── 分集1 (Item)
│   └── 分集2 (Item)
└── 另一个系列
```

## 注意事项

### 1. 文件路径
- 确保 `config.json` 中的 `root` 路径正确指向B站客户端的下载目录
- 典型路径示例：
  - Windows: `C:/Users/用户名/Videos/Bilibili`
  - Linux: `~/Videos/Bilibili`
  - macOS: `~/Movies/Bilibili`

### 2. 依赖组件
- **ffplay** 必须正确安装并可在终端调用
- **xxd** 通常随 vim 或 hexdump 安装
- 如果遇到播放问题，先测试：`ffplay -version`

### 3. 数据更新
- 添加新视频后，需要按 **b** 重建索引
- 重建过程可能较慢，取决于视频数量

### 4. 播放控制
- 播放过程中按 **q** 退出当前视频
- 播放列表会连续播放，直到列表结束或手动退出
- 程序退出时会自动清理所有播放进程

### 5. 常见问题

**Q: 启动时报 "未检测到 buildtree/tree.json"**
A: 按 'b' 键构建索引，或直接运行 `buildtree/target/release/buildtree`

**Q: 播放没有画面只有声音**
A: 因为这是个音乐播放器

**Q: TUI界面显示异常**
A: 确保终端支持UTF-8，建议使用较新版本的终端模拟器

**Q: 视频文件找不到**
A: 确认 `config.json` 中的路径正确，且视频文件的 `videoInfo.json` 存在

### 6. 清理与重置
```bash
# 删除索引文件
rm buildtree/tree.json

# 清理构建缓存
cd buildtree && cargo clean

# 清理Go编译文件
rm -rf cmd/tui/mytui

# 清理所有播放进程（异常退出时使用）
pkill -f ffplay
pkill -f play
```

## 项目结构说明

```
biliCLI/
├── buildtree/          # Rust扫描器：分析视频文件生成索引
├── cmd/tui/            # Go TUI：用户界面
├── internal/           # Go内部库
├── *.py                # Python辅助脚本
├── *.c                 # C辅助工具
└── config.json         # 配置文件
```

## 贡献与开发

shitted by ayazumi 2026-Jan-05

1. **报告问题**：我累了，有问题请改好发给我
2. **功能建议**：描述使用场景和预期行为
3. **代码提交**：保持代码风格一致，添加适当注释

## 许可证

本项目为个人开源项目，仅供学习和交流使用。使用B站视频内容请遵守相关版权规定。

## 更新日志

### v1.0
- 初始版本发布
- 支持基本视频索引和播放
- 提供TUI浏览界面
- 支持顺序/随机播放模式

---

**提示**：本工具仅为本地视频文件管理器，不提供视频下载功能。视频需通过B站客户端或其他方式下载。
