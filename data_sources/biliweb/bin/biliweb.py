#!/usr/bin/env python3
"""
播放器插件: biliweb
支持 scheme: biliweb
使用 yt-dlp 流式播放 B站视频音频
"""

import json
import subprocess
import sys
import os
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def generate_display_name(title, group, category):
    parts = []
    if title and title not in parts:
        parts.append(title)
    if category and category not in parts:
        parts.append(category)
    if group and group not in parts:
        parts.append(group)
    if not parts:
        return "未知曲目"
    return " - ".join(parts)


def build_bilibili_url(bvid, p=None):
    url = f"https://www.bilibili.com/video/{bvid}/"
    if p and p > 1:
        url += f"?p={p}"
    return url


# ============================================
# --canwork：检查插件能否处理这个 JSON
# ============================================
def cmd_canwork(data):
    """检查插件能否处理这个 JSON"""
    ok = True

    # 1. 检查 yt-dlp
    try:
        subprocess.run(['yt-dlp', '--version'], capture_output=True, timeout=5, check=True)
        print(f"✅ yt-dlp 可用", file=sys.stderr)
    except Exception:
        print(f"❌ yt-dlp 不可用", file=sys.stderr)
        ok = False

    # 2. 检查 ffplay
    try:
        subprocess.run(['ffplay', '-version'], capture_output=True, timeout=5, check=True)
        print(f"✅ ffplay 可用", file=sys.stderr)
    except Exception:
        print(f"❌ ffplay 不可用", file=sys.stderr)
        ok = False

    # 3. 检查 JSON 里有没有 bvid
    bvid = data.get('bvid', '')
    if not bvid:
        print(f"❌ JSON 里没有 bvid", file=sys.stderr)
        ok = False
    else:
        print(f"✅ bvid: {bvid}", file=sys.stderr)

    # 4. 检查网络（可选，探测 B站）
    if bvid:
        url = build_bilibili_url(bvid, data.get('p', 1))
        try:
            # 只探测，不下载
            result = subprocess.run(
                ['yt-dlp', '--simulate', '--no-warnings', '--no-playlist', url],
                capture_output=True, timeout=15, text=True
            )
            if result.returncode == 0:
                print(f"✅ 视频可访问: {bvid}", file=sys.stderr)
            else:
                print(f"⚠️ 视频可能不可访问: {bvid}", file=sys.stderr)
                # 不强制失败，可能网络问题
        except subprocess.TimeoutExpired:
            print(f"⚠️ 探测超时: {bvid}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ 探测失败: {e}", file=sys.stderr)

    if ok:
        print("canwork")
        return 0
    else:
        print("cannotwork")
        return 1


def main():
    if len(sys.argv) < 2:
        print("用法: ./biliweb [--support|--canwork JSON|--getrawdata JSON|--cover JSON|--title JSON]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--support":
        print("biliweb")
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
    bvid = data.get('bvid', '')
    p = data.get('p', 1)
    title = data.get('title', '未知标题')
    cover = data.get('pic', '')

    if not bvid:
        print("错误: JSON 中没有 bvid 字段", file=sys.stderr)
        sys.exit(1)

    if cmd == "--getrawdata":
        url = build_bilibili_url(bvid, p)

        # 流式输出
        yt = subprocess.Popen(
            ['yt-dlp', '-f', 'bestaudio', '-o', '-', '--no-playlist', url],
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
        if cover:
            print(cover)
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
