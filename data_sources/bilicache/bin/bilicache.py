#!/usr/bin/env python3
"""
播放器插件: bilicache
支持 scheme: bilicache
"""

import json
import pathlib
import subprocess
import sys
import os
import time
from pathlib import Path

# ============================================
# 读取配置
# ============================================
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "../config/config.json"

def get_root():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"root": ""}, f)
    with open(CONFIG_FILE) as f:
        return Path(json.load(f)['root'])

ROOT = get_root()

# ============================================
# 查找音频文件
# ============================================
def find_audio_file(cid: str, root: Path) -> Path:
    """在 root/cid/ 目录下查找音频文件，找不到直接退出"""
    cid_dir = root / cid

    if not cid_dir.exists():
        print(f"错误: 目录不存在: {cid_dir}", file=sys.stderr)
        sys.exit(1)

    # 遍历所有 .m4s 文件
    for f in cid_dir.glob("*.m4s"):
        try:
            cmd = ['sh', '-c', 'tail -c +10 "$0" | ffplay -nodisp -autoexit - 2>&1 | grep -m1 Stream', str(f)]
            out = subprocess.check_output(cmd, text=True)
            if ('mp4a' in out or 'eac3' in out):
                return f
        except Exception:
            continue

    print(f"错误: 找不到音频文件 (cid: {cid})", file=sys.stderr)
    sys.exit(1)

# ============================================
# 查找封面
# ============================================
def get_image(cid: str) -> Path | None:
    cid_dir = ROOT / cid
    if not cid_dir.exists():
        return None

    # 优先 image.jpg
    img = cid_dir / "image.jpg"
    if img.exists():
        return img

    # 其次 group.jpg
    img = cid_dir / "group.jpg"
    if img.exists():
        return img

    # 任意 jpg/png
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        for f in cid_dir.glob(ext):
            return f

    return None

def generate_display_name(title, group, category):
    """根据 title, group, category 生成显示名称，自动去重"""
    parts = []

    if category and category not in parts:
        parts.append(category)
    if group and group not in parts:
        parts.append(group)
    if title and title not in parts:
        parts.append(title)

    if not parts:
        return "未知曲目"

    return " - ".join(parts)

# ============================================
# --canwork：检查插件能否处理这个 JSON
# ============================================
def cmd_canwork(data):
    """检查插件能否处理这个 JSON（环境 + 这首歌）"""
    ok = True

    # 1. 检查 config.json
    if not CONFIG_FILE.exists():
        print(f"❌ config.json 不存在: {CONFIG_FILE}", file=sys.stderr)
        ok = False
    elif not ROOT or not str(ROOT).strip():
        print(f"❌ config.json 里 root 为空", file=sys.stderr)
        ok = False
    elif not ROOT.exists():
        print(f"❌ root 路径不存在: {ROOT}", file=sys.stderr)
        ok = False
    elif not ROOT.is_dir():
        print(f"❌ root 不是目录: {ROOT}", file=sys.stderr)
        ok = False
    else:
        print(f"✅ root: {ROOT}", file=sys.stderr)

    # 2. 检查 ffplay
    try:
        subprocess.run(['ffplay', '-version'], capture_output=True, timeout=5, check=True)
        print(f"✅ ffplay 可用", file=sys.stderr)
    except Exception:
        print(f"❌ ffplay 不可用", file=sys.stderr)
        ok = False

    # 3. 检查 tail
    try:
        subprocess.run(['tail', '--version'], capture_output=True, timeout=5, check=True)
        print(f"✅ tail 可用", file=sys.stderr)
    except Exception:
        print(f"❌ tail 不可用", file=sys.stderr)
        ok = False

    # 4. 检查这首歌的音频文件是否存在
    cid = data.get('cid')
    if not cid:
        print(f"❌ JSON 里没有 cid", file=sys.stderr)
        ok = False
    else:
        cid_dir = ROOT / str(cid)
        if not cid_dir.exists():
            print(f"❌ cid 目录不存在: {cid_dir}", file=sys.stderr)
            ok = False
        else:
            found = False
            for f in cid_dir.glob("*.m4s"):
                try:
                    cmd = ['sh', '-c', 'tail -c +10 "$0" | ffplay -nodisp -autoexit - 2>&1 | grep -m1 Stream', str(f)]
                    out = subprocess.check_output(cmd, text=True, timeout=10)
                    if ('mp4a' in out or 'eac3' in out):
                        found = True
                        print(f"✅ 找到音频: {f.name}", file=sys.stderr)
                        break
                except Exception:
                    continue
            if not found:
                print(f"❌ 找不到音频文件 (cid: {cid})", file=sys.stderr)
                ok = False

    if ok:
        print("canwork")
        return 0
    else:
        print("cannotwork")
        return 1

# ============================================
# 主逻辑
# ============================================
def main():
    if len(sys.argv) < 2:
        print("用法: ./bilicache [--support|--canwork JSON|--getrawdata JSON|--cover JSON|--title JSON]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--support":
        print("bilicache")
        return

    if cmd == "--canwork":
        if len(sys.argv) < 3:
            print("错误: --canwork 需要 JSON 参数", file=sys.stderr)
            sys.exit(1)
        data = json.loads(sys.argv[2])
        sys.exit(cmd_canwork(data))

    if len(sys.argv) < 3:
        print("错误: 需要 JSON 参数", file=sys.stderr)
        sys.exit(1)

    data = json.loads(sys.argv[2])
    cid = data.get('cid')
    title = data.get('title', '未知标题')

    if cmd == "--getrawdata":
        audio_file = find_audio_file(str(cid), ROOT)  # 找不到就退出

        # 流式输出
        yt = subprocess.Popen(
            ['tail', '-c', '+10', audio_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        while True:
            b = yt.stdout.read(65536)
            if not b:
                break
            sys.stdout.buffer.write(b)
            sys.stdout.buffer.flush()
        yt.wait()

    elif cmd == "--cover":
        image = get_image(str(cid))
        if image:
            print(image)
        else:
            print("")

    elif cmd == "--title":
        title = data.get('title', '')
        group = data.get('group', '')
        category = data.get('category', '')
        display_name = generate_display_name(title, group, category)
        print(display_name)

if __name__ == "__main__":
    main()
