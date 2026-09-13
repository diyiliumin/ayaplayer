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
# 查找音频文件（失败直接退出）
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
            cmd = ['sh','-c','tail -c +10 "$0" | ffplay -nodisp -autoexit - 2>&1 | grep -m1 Stream', str(f)]
            out = subprocess.check_output(cmd, text=True)
            if ('mp4a' in out or 'eac3' in out):
                return f
        except Exception:
            continue
    
    # ★★★ 找不到音频，直接退出 ★★★
    print(f"错误: 找不到音频文件 (cid: {cid})", file=sys.stderr)
    sys.exit(1)

# ============================================
# 查找封面（找不到返回空）
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
# 主逻辑
# ============================================
def main():
    if len(sys.argv) < 2:
        print("用法: ./bilicache [--support|--getrawdata JSON|--cover JSON|--title JSON]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "--support":
        print("bilicache")
        return
    
    if len(sys.argv) < 3:
        print("错误: 需要 JSON 参数", file=sys.stderr)
        sys.exit(1)
    
    data = json.loads(sys.argv[2])
    cid = data.get('cid')
    title = data.get('title', '未知标题')
    
    if cmd == "--getrawdata":
        audio_file = find_audio_file(str(cid), ROOT)  # 找不到就退出
        
        # print(f"播放: {title}", file=sys.stderr)
        # print(f"文件: {audio_file}", file=sys.stderr)
        
        # cmd_str = f"tail -c +10 '{audio_file}' | ffplay -v 0 -nostats -nodisp -autoexit - 2>/dev/null &"
        # 
        # proc = subprocess.Popen(
        #     ['bash', '-c', cmd_str],
        #     stdout=subprocess.DEVNULL,
        #     stderr=subprocess.DEVNULL,
        #     start_new_session=True
        # )
        # time.sleep(0.2)
        
        # result = subprocess.run(
        #     ['pgrep', '-n', 'ffplay'],
        #     capture_output=True,
        #     text=True
        # )
        # 
        # if result.stdout:
        #     ffplay_pid = int(result.stdout.strip())
        #     print(ffplay_pid)
        # else:
        #     print(proc.pid)
        
        yt = subprocess.Popen(
            ['tail', '-c', '+10',  audio_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        # 把 tail 的输出逐块拷到自己的 stdout
        while True:
            b = yt.stdout.read(65536)
            if not b:
                break
            sys.stdout.buffer.write(b)
            sys.stdout.buffer.flush()
        yt.wait()

        # 
        # ff = subprocess.Popen(
        #     ['ffplay', '-v', '0', '-nostats', '-nodisp', '-autoexit', '-'],
        #     stdin=yt.stdout,
        #     stdout=subprocess.DEVNULL,
        #     stderr=subprocess.DEVNULL,
        #     start_new_session=True
        # )
        # 
        # yt.stdout.close()          # ← 父进程关掉读端，不然管道不 EOF
        # 
        # print(ff.pid)              # ← ffplay 的 PID，确权
        
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
