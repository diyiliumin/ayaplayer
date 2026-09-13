#!/usr/bin/env python3
"""
播放状态仪表盘 - 通过 DBus 监听并显示
"""

import os
import sys
import time
import json
import signal
import curses
import threading
import subprocess
from datetime import datetime

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

# ============================================
# 颜色定义（用于 curses）
# ============================================
class Colors:
    HEADER = 1
    GREEN = 2
    YELLOW = 3
    RED = 4
    CYAN = 5
    MAGENTA = 6
    BLUE = 7
    WHITE = 8

# ============================================
# DBus 监听器
# ============================================
class PlayerStatusListener:
    def __init__(self):
        self.pid = 0
        self.title = "等待播放..."
        self.cover = ""
        self.songleft = 0
        self.paused = False
        self.status_updated = False
        self.last_update = "从未"
        self.running = True
        
        # 连接 DBus
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        
        # 监听状态信号
        self.bus.add_signal_receiver(
            self.on_status_changed,
            dbus_interface='com.ayaplayer.Interface',
            signal_name='StatusChanged',
            path='/com/ayaplayer/Status'
        )
        
        # 监听控制信号（按键）
        self.bus.add_signal_receiver(
            self.on_control,
            dbus_interface='com.ayaplayer.Interface',
            signal_name='Control',
            path='/com/ayaplayer/Control'
        )
        
        print(f"📡 监听 DBus 信号...", file=sys.stderr)
        print(f"PID: {os.getpid()}", file=sys.stderr)
        
        # GLib 主循环（在独立线程）
        self.loop = GLib.MainLoop()
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
    
    def _run_loop(self):
        self.loop.run()
    
    def on_status_changed(self, pid, title, cover, songleft=0, paused=False):
        self.pid = int(pid)
        self.title = str(title) if title else "未知曲目"
        self.cover = str(cover) if cover else ""
        self.songleft = int(songleft)
        self.paused = bool(paused)
        self.status_updated = True
        self.last_update = datetime.now().strftime("%H:%M:%S")
    
    def on_control(self, action, data):
        # 按键信号，可选显示
        pass
    
    def get_status(self):
        return {
            'pid': self.pid,
            'title': self.title,
            'cover': self.cover,
            'songleft': self.songleft,
            'paused': self.paused,
            'last_update': self.last_update,
            'status_updated': self.status_updated
        }
    
    def stop(self):
        self.loop.quit()
        self.running = False

# ============================================
# Dashboard 主界面
# ============================================
class Dashboard:
    def __init__(self, listener):
        self.listener = listener
        self.stdscr = None
        self.running = True
        
        # 终端大小
        self.rows = 0
        self.cols = 0
    
    def draw_box(self, y, x, height, width, title=""):
        """画一个带标题的框"""
        if height < 2 or width < 2:
            return
        
        # 上边框
        self.stdscr.addch(y, x, curses.ACS_ULCORNER)
        for i in range(width - 2):
            self.stdscr.addch(y, x + 1 + i, curses.ACS_HLINE)
        self.stdscr.addch(y, x + width - 1, curses.ACS_URCORNER)
        
        # 标题
        if title:
            self.stdscr.addstr(y, x + 2, f" {title} ")
        
        # 中间（空行）
        for i in range(height - 2):
            self.stdscr.addch(y + 1 + i, x, curses.ACS_VLINE)
            self.stdscr.addch(y + 1 + i, x + width - 1, curses.ACS_VLINE)
        
        # 下边框
        self.stdscr.addch(y + height - 1, x, curses.ACS_LLCORNER)
        for i in range(width - 2):
            self.stdscr.addch(y + height - 1, x + 1 + i, curses.ACS_HLINE)
        self.stdscr.addch(y + height - 1, x + width - 1, curses.ACS_LRCORNER)
    
    def draw_status(self, status):
        """绘制状态信息"""
        rows, cols = self.stdscr.getmaxyx()
        
        # 标题栏
        self.stdscr.attron(curses.A_BOLD | curses.color_pair(Colors.HEADER))
        title = " 🎵 播放状态仪表盘 "
        self.stdscr.addstr(0, (cols - len(title)) // 2, title)
        self.stdscr.attroff(curses.A_BOLD | curses.color_pair(Colors.HEADER))
        
        # 分隔线
        self.stdscr.hline(1, 0, curses.ACS_HLINE, cols)
        
        # 状态框
        box_y = 2
        box_height = 6
        box_width = min(cols - 4, 60)
        box_x = 2
        self.draw_box(box_y, box_x, box_height, box_width, "📊 播放状态")
        
        # 状态内容
        line = 0
        if status['paused']:
            pause_status = "⏸ 暂停"
        else:
            pause_status = "▶ 播放中"
        self.stdscr.addstr(box_y + 1 + line, box_x + 2, f"状态: {pause_status}")
        line += 1
        
        # 标题（截断过长）
        title = status['title']
        if len(title) > box_width - 10:
            title = title[:box_width - 13] + "..."
        self.stdscr.addstr(box_y + 1 + line, box_x + 2, f"歌曲: {title}")
        line += 1
        
        self.stdscr.addstr(box_y + 1 + line, box_x + 2, f"剩余: {status['songleft']} 次")
        line += 1
        
        self.stdscr.addstr(box_y + 1 + line, box_x + 2, f"PID:  {status['pid']}")
        line += 1
        
        self.stdscr.addstr(box_y + 1 + line, box_x + 2, f"更新: {status['last_update']}")
        
        # 信息框
        info_y = box_y + box_height + 1
        info_height = 4
        info_width = min(cols - 4, 60)
        self.draw_box(info_y, box_x, info_height, info_width, "  操作提示")
        
        self.stdscr.addstr(info_y + 1, box_x + 2, "q 退出仪表盘")
        self.stdscr.addstr(info_y + 2, box_x + 2, "r 刷新状态")
        self.stdscr.addstr(info_y + 3, box_x + 2, f"(curses: {rows}x{cols})")
        
        # 封面路径（如果有）
        if status['cover']:
            cover_y = box_y + box_height + info_height + 2
            cover = status['cover']
            if len(cover) > cols - 4:
                cover = cover[:cols - 7] + "..."
            self.stdscr.attron(curses.color_pair(Colors.BLUE))
            self.stdscr.addstr(cover_y, 2, f"🖼️ 封面: {cover}")
            self.stdscr.attroff(curses.color_pair(Colors.BLUE))
        
        # 底部时间
        bottom_y = rows - 1
        self.stdscr.attron(curses.color_pair(Colors.CYAN))
        self.stdscr.addstr(bottom_y, 2, f"📡 监听中...  按 q 退出   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdscr.attroff(curses.color_pair(Colors.CYAN))
    
    def main_loop(self, stdscr):
        """主循环"""
        self.stdscr = stdscr
        
        # 初始化颜色
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(Colors.HEADER, curses.COLOR_CYAN, -1)
        curses.init_pair(Colors.GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(Colors.YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(Colors.RED, curses.COLOR_RED, -1)
        curses.init_pair(Colors.CYAN, curses.COLOR_CYAN, -1)
        curses.init_pair(Colors.BLUE, curses.COLOR_BLUE, -1)
        curses.init_pair(Colors.MAGENTA, curses.COLOR_MAGENTA, -1)
        curses.init_pair(Colors.WHITE, curses.COLOR_WHITE, -1)
        
        # 隐藏光标
        curses.curs_set(0)
        self.stdscr.nodelay(1)  # 非阻塞输入
        
        while self.running:
            # 获取状态
            status = self.listener.get_status()
            
            # 清屏
            self.stdscr.clear()
            
            # 绘制
            self.draw_status(status)
            
            # 刷新
            self.stdscr.refresh()
            
            # 检查按键
            try:
                key = self.stdscr.getch()
                if key == ord('q') or key == ord('Q'):
                    self.running = False
                    break
                elif key == ord('r') or key == ord('R'):
                    send_ui_started()
            except:
                pass
            
            time.sleep(0.2)
    
    def run(self):
        """启动仪表盘"""
        try:
            curses.wrapper(self.main_loop)
        except KeyboardInterrupt:
            pass
        
        print(f"\n👋 仪表盘已退出")

def send_control(action, data=""):
    """发送控制信号（统一入口）"""
    subprocess.run([
        'dbus-send', '--session',
        '--type=signal',
        '/com/ayaplayer/Control',
        'com.ayaplayer.Interface.Control',
        f'string:{action}',
        f'string:{data}'
    ], stderr=subprocess.DEVNULL, check=False)
def send_ui_started():
    """发送 UI 启动"""
    send_control('ui_started', str(os.getpid()))


# ============================================
# 主函数
# ============================================
def main():
    # 初始化 DBus 监听器
    print("🎵 启动播放状态仪表盘...", file=sys.stderr)
    listener = PlayerStatusListener()
    send_ui_started()
    
    # 给 DBus 一点时间连接
    time.sleep(0.3)
    
    # 启动仪表盘
    dashboard = Dashboard(listener)
    
    try:
        dashboard.run()
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        print("\n👋 退出", file=sys.stderr)

if __name__ == '__main__':
    main()
