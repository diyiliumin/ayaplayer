#!/usr/bin/env python3
"""
播放器插件: local
支持 scheme: local
播放本地音乐库
自动从音频文件提取内嵌封面
"""

import json
import subprocess
import sys
import os
import hashlib
from pathlib import Path

TMP_DIR = "/tmp/steam_covers"


def generate_display_name(title, group, category):
    parts = []
    if title and title not in parts:
        parts.append(title)
    if category and category not in parts:
        parts.append(category)
    if group and group not in parts:
        parts.append(group)
    return " - ".join(parts) if parts else "未知曲目"


def get_cover_cache_path(audio_file):
    """根据音频文件路径生成缓存路径"""
    os.makedirs(TMP_DIR, exist_ok=True)
    h = hashlib.md5(audio_file.encode('utf-8')).hexdigest()
    return os.path.join(TMP_DIR, f"{h}.jpg")


def extract_cover(audio_file):
    """从音频文件提取内嵌封面到 /tmp"""
    cache_path = get_cover_cache_path(audio_file)

    # 已有缓存
    if os.path.exists(cache_path):
        return cache_path

    # 用 ffmpeg 提取封面
    try:
        result = subprocess.run(
            [
                'ffmpeg', '-y', '-v', '0',
                '-i', audio_file,
                '-an', '-vcodec', 'copy',
                '-f', 'image2',
                cache_path,
            ],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0 and os.path.exists(cache_path):
            if os.path.getsize(cache_path) > 0:
                return cache_path
            else:
                os.remove(cache_path)
    except Exception as e:
        print(f"⚠️ 提取封面失败: {e}", file=sys.stderr)

    # 回退：ffmpeg 输出到 stdout
    try:
        result = subprocess.run(
            [
                'ffmpeg', '-v', '0',
                '-i', audio_file,
                '-an', '-vcodec', 'copy',
                '-f', 'image2', '-',
            ],
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout:
            with open(cache_path, 'wb') as f:
                f.write(result.stdout)
            return cache_path
    except Exception:
        pass

    return None


# ============================================
# --canwork：检查插件能否处理这个 JSON
# ============================================
def cmd_canwork(data):
    """检查插件能否处理这个 JSON"""
    ok = True

    # 1. 检查 ffmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5, check=True)
        print(f"✅ ffmpeg 可用", file=sys.stderr)
    except Exception:
        print(f"❌ ffmpeg 不可用", file=sys.stderr)
        ok = False

    # 2. 检查 JSON 里的 bvid（文件路径）
    file_path = data.get('bvid', '')
    if not file_path:
        print(f"❌ JSON 里没有 bvid（文件路径）", file=sys.stderr)
        ok = False
    elif not os.path.isfile(file_path):
        print(f"❌ 文件不存在: {file_path}", file=sys.stderr)
        ok = False
    else:
        size = os.path.getsize(file_path)
        print(f"✅ 文件存在: {file_path} ({size} bytes)", file=sys.stderr)

    if ok:
        print("canwork")
        return 0
    else:
        print("cannotwork")
        return 1


def main():
    if len(sys.argv) < 2:
        print("用法: ./steam [--support|--canwork JSON|--getrawdata JSON|--cover JSON|--title JSON]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--support":
        print("local")
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
    file_path = data.get('bvid', '')
    title = data.get('title', '未知标题')

    if not file_path:
        print("错误: JSON 中没有 bvid 字段（文件路径）", file=sys.stderr)
        sys.exit(1)

    if cmd == "--getrawdata":
        if not os.path.isfile(file_path):
            print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
            sys.exit(1)

        # 流式输出
        ff = subprocess.Popen(
            [
                'ffmpeg', '-v', '0',
                '-vn',
                '-i', file_path,
                '-f', 'mp3', '-',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        while True:
            b = ff.stdout.read(65536)
            if not b:
                break
            sys.stdout.buffer.write(b)
            sys.stdout.buffer.flush()
        ff.wait()

    elif cmd == "--cover":
        cover_path = extract_cover(file_path)
        print(cover_path if cover_path else "")

    elif cmd == "--title":
        title = data.get('title', '')
        group = data.get('group', '')
        category = data.get('category', '')
        print(generate_display_name(title, group, category))


if __name__ == "__main__":
    main()
