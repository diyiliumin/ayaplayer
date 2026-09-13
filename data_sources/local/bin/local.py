#!/usr/bin/env python3
"""
播放器插件: steam
支持 scheme: steam
播放本地 Steam 音乐库
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
    
    # ★★★ 已经有缓存，直接返回 ★★★
    if os.path.exists(cache_path):
        return cache_path
    
    # ★★★ 用 ffmpeg 提取封面 ★★★
    try:
        result = subprocess.run(
            [
                'ffmpeg',
                '-y',                   # 覆盖输出
                '-v', '0',              # 静默
                '-i', audio_file,       # 输入
                '-an',                  # 不要音频
                '-vcodec', 'copy',      # 复制视频流（封面图）
                '-f', 'image2',         # 图片格式
                cache_path,             # 输出
            ],
            capture_output=True,
            timeout=10
        )
        
        if result.returncode == 0 and os.path.exists(cache_path):
            # 检查文件大小（有效的封面）
            if os.path.getsize(cache_path) > 0:
                return cache_path
            else:
                os.remove(cache_path)
    except Exception as e:
        print(f"⚠️ 提取封面失败: {e}", file=sys.stderr)
    
    # ★★★ 回退：用 ffmpeg 输出到 stdout，手动保存 ★★★
    try:
        result = subprocess.run(
            [
                'ffmpeg',
                '-v', '0',
                '-i', audio_file,
                '-an',
                '-vcodec', 'copy',
                '-f', 'image2',
                '-',
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


def main():
    if len(sys.argv) < 2:
        print("用法: ./steam [--support|--getrawdata JSON|--cover JSON|--title JSON]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "--support":
        print("local")
        return
    
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
        
        # print(f"播放: {title}", file=sys.stderr)
        # print(f"文件: {file_path}", file=sys.stderr)
        
        # ★★★ 流式输出 ★★★
        ff = subprocess.Popen(
            [
                'ffmpeg',
                '-v', '0',
                '-vn',
                '-i', file_path,
                '-f', 'mp3',
                '-',
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
        # ★★★ 自动提取封面到 /tmp ★★★
        cover_path = extract_cover(file_path)
        if cover_path:
            print(cover_path)
        else:
            print("")
    
    elif cmd == "--title":
        title = data.get('title', '')
        group = data.get('group', '')
        category = data.get('category', '')
        print(generate_display_name(title, group, category))


if __name__ == "__main__":
    main()
