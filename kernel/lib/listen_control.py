#!/usr/bin/env python3
"""
listen_control.py - 监听 DBus 控制信号，打印 action|data 到 stdout
支持 Ctrl+C 和 pkill 干净退出
"""

import sys
import os
import signal
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

# 全局主循环引用
main_loop = None


def cleanup(signum=None, frame=None):
    """清理函数"""
    if signum:
        sig_name = signal.Signals(signum).name
        print(f"\n🧹 收到 {sig_name}，退出", file=sys.stderr)
    else:
        print(f"\n🧹 退出", file=sys.stderr)
    
    if main_loop:
        main_loop.quit()
    
    sys.exit(0)


def on_control(action, data):
    """收到控制信号，输出 action|data"""
    action = str(action) if action else ""
    data = str(data) if data else ""
    
    # ★★★ 只输出到 stdout ★★★
    try:
        print(f"{action}|{data}", flush=True)
    except BrokenPipeError:
        # ★★★ 管道断了，说明主脚本退出了，自己退出 ★★★
        print("📡 管道已关闭，退出", file=sys.stderr)
        if main_loop:
            main_loop.quit()
        sys.exit(0)

def main():
    global main_loop
    
    # ★★★ 注册信号处理 ★★★
    signal.signal(signal.SIGTERM, cleanup)  # pkill 默认发送
    signal.signal(signal.SIGINT, cleanup)   # Ctrl+C
    signal.signal(signal.SIGHUP, cleanup)   # 终端关闭
    
    # 初始化 DBus
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    
    # 注册信号监听
    bus.add_signal_receiver(
        on_control,
        dbus_interface='com.ayaplayer.Interface',
        signal_name='Control',
        path='/com/ayaplayer/Control'
    )
    
    print(f"📡 监听中... (PID: {os.getpid()})", file=sys.stderr)
    
    # 运行主循环
    main_loop = GLib.MainLoop()
    try:
        main_loop.run()
    # except KeyboardInterrupt:
    #     pass
    finally:
        cleanup()


if __name__ == '__main__':
    main()
