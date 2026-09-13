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
    if category and category not in parts:
        parts.append(category)
    if group and group not in parts:
        parts.append(group)
    if title and title not in parts:
        parts.append(title)
    if not parts:
        return "未知曲目"
    return " - ".join(parts)

def build_bilibili_url(bvid, p=None):
    url = f"https://www.bilibili.com/video/{bvid}/"
    if p and p > 1:
        url += f"?p={p}"
    return url

def main():
    if len(sys.argv) < 2:
        print("用法: ./biliweb [--support|--getrawdata JSON|--cover JSON|--title JSON]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "--support":
        print("bilicache")
        return
    
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
        # print(f"播放: {title}", file=sys.stderr)
        # print(f"URL: {url}", file=sys.stderr)
        
        # # ★★★ 用 yt-dlp 流式播放 ★★★
        # cmd_str = f'yt-dlp -f bestaudio -o - --no-playlist "{url}" 2>/dev/null | ffplay -v 0 -nostats -nodisp -autoexit - 2>/dev/null &'
        # 
        # proc = subprocess.Popen(
        #     ['bash', '-c', cmd_str],
        #     stdout=subprocess.DEVNULL,
        #     stderr=subprocess.DEVNULL,
        #     start_new_session=True
        # )
        # 等待 ffplay 启动
        # time.sleep(0.3)
        # 
        # # ★★★ 用 pgrep 获取 ffplay PID ★★★
        # result = subprocess.run(
        #     ['pgrep', '-n', 'ffplay'],
        #     capture_output=True,
        #     text=True
        # )
        
        # if result.stdout:
        #     ffplay_pid = int(result.stdout.strip())
        #     print(ffplay_pid)
        # else:
        #     # 备用：返回 shell 进程 PID
        #     print(proc.pid)
        
        yt = subprocess.Popen(
            ['yt-dlp', '-f', 'bestaudio', '-o', '-', '--no-playlist', url],
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
        # ff = subprocess.Popen(
        #     ['ffplay', '-v', '0', '-nostats', '-nodisp', '-autoexit', '-'],
        #     stdin=yt.stdout,
        #     stdout=subprocess.DEVNULL,
        #     stderr=subprocess.DEVNULL,
        #     start_new_session=True
        # )
        
        # yt.stdout.close()          # ← 父进程关掉读端，不然管道不 EOF
        
        # print(ff.pid)              # ← ffplay 的 PID，确权
        
        
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
