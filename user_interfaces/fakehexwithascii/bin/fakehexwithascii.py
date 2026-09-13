#!/usr/bin/env python3
import json
import select
import sys
import tty
import termios
from io import BytesIO
import requests
import sys
import os 
import time
import signal
import subprocess
import math
import struct
import fcntl
import termios
import array
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

ASCII_CHARS = " .+=oxXW#"
should_exit = False
# ============================================
# 光标控制
# ============================================
def hide_cursor():
    sys.stdout.write('\033[?25l')
    sys.stdout.flush()

def show_cursor():
    sys.stdout.write('\033[?25h')
    sys.stdout.flush()

# ============================================
# DBus 统一信号发送
# ============================================

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

# ============================================
# 专属发送函数
# ============================================

def send_number(repeat_count):
    """发送数字按键"""
    send_control('number', str(repeat_count))

def send_pause(paused):
    """发送暂停/继续"""
    send_control('pause', 'true' if paused else 'false')

def send_skip():
    """发送跳过"""
    send_control('skip', '')

def send_quit():
    """发送退出"""
    send_control('quit', '')
    global should_exit 
    should_exit = True

def send_ui_started():
    """发送 UI 启动"""
    send_control('ui_started', str(os.getpid()))

def send_status(pid, title, cover, songleft, paused):
    """发送播放状态"""
    data = json.dumps({
        'pid': pid,
        'title': title,
        'cover': cover,
        'songleft': songleft,
        'paused': paused
    })
    send_control('status', data)

# ============================================
# 键盘监听
# ============================================
def read_key_nonblock():
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            if select.select([sys.stdin], [], [], 0.05)[0]:
                key = sys.stdin.read(1)
                return key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except:
        pass
    return None


def keyboard_listener():
    print("⌨️ 键盘监听已启动", file=sys.stderr)
    print("  1-9: 设置次数  p: 暂停  x: 跳过  q: 退出", file=sys.stderr)
    
    SONG_LOOP = 1
    REPEAT_COUNT = 0
    PAUSED = False
    
    while True:
        global should_exit
        if should_exit:
            sys.exit(0)
        key = read_key_nonblock()
        
        if key:
            if key in '123456789':
                SONG_LOOP = int(key)
                REPEAT_COUNT = SONG_LOOP - 1
                send_number(REPEAT_COUNT)
                print(f"\n\033[32m🔄 播放次数: {SONG_LOOP}\033[0m")
            
            elif key.lower() == 'd':
                should_exit = True

            elif key.lower() == 'p':
                PAUSED = not PAUSED
                send_pause(PAUSED)
                print("\n⏸ 已暂停" if PAUSED else "\n▶ 继续播放")
            
            elif key.lower() == 'x':
                send_skip()
                print("\n⏹ 跳过此曲")
            
            elif key.lower() == 'q':
                send_quit()
                print("\n👋 退出播放")
                return 'quit'
        
        # time.sleep(0.05)

# ============================================
# DBus 监听
# ============================================
class PlayerStatusListener:
    def __init__(self):
        self.pid = 0
        self.title = "等待播放..."
        self.cover = ""
        self.songleft = 0
        self.paused = False
        self.running = True
        self.status_updated = False
        
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        
        self.bus.add_signal_receiver(
            self.on_status_changed,
            dbus_interface='com.ayaplayer.Interface',
            signal_name='StatusChanged',
            path='/com/ayaplayer/Status'
        )
        
        print(f"📡 监听 DBus 信号...", file=sys.stderr)
        print(f"PID: {os.getpid()}", file=sys.stderr)
        print(f"💡 等待播放器发送状态...", file=sys.stderr)
        
        self.loop = GLib.MainLoop()
        import threading
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
    
    def _run_loop(self):
        self.loop.run()
    
    def on_status_changed(self, pid, title, cover, songleft=0, paused=False):
        self.pid = int(pid)
        self.title = str(title) if title else "未知曲目"
        self.cover = str(cover) if cover else "/tmp/default_cover.jpg"
        self.songleft = int(songleft)
        self.paused = bool(paused)
        self.status_updated = True
        # print(f"🎵 更新: {self.title} (剩余: {self.songleft})", file=sys.stderr)
    
    def get_status(self):
        return self.pid, self.title, self.cover, self.songleft, self.paused
    
    def has_status(self):
        return self.status_updated
    
    def stop(self):
        self.loop.quit()

# ============================================
# 工具函数
# ============================================
def height_to_char(h: int) -> str:
    max_val = 1000  
    idx = min(int(h * len(ASCII_CHARS) / (max_val + 1)), len(ASCII_CHARS) - 1)
    return ASCII_CHARS[idx]

def format_hexdump(data: bytes, offset: int) -> str:
    if len(data) < 16:
        data = data.ljust(16, b' ')
    elif len(data) > 16:
        data = data[:16]
    
    words = []
    for i in range(0, 16, 2):
        word = (data[i] << 8) | data[i + 1]
        words.append(f"{word:04x}")
    
    hex_str = ' '.join(words)
    ascii_str = ' '.join(chr(b) if 16 <= b <= 126 else '.' for b in data)
    return f"{offset:08x}: {hex_str}  {ascii_str}"

# ============================================
# SpinCircle 类
# ============================================
class SpinCircle:
    def __init__(self, width=50, hole_ratio=0.25):
        self.angle = 0
        self.width = width
        self.hole_ratio = hole_ratio
        self.image_path = None
        self.img = None
        
        # 先创建默认封面
        self._create_default_cover()
        self._load_image(self.image_path)
    
    def _create_default_cover(self):
        os.makedirs('/tmp', exist_ok=True)
        img = Image.new('RGB', (200, 200), color='#1a1a2e')
        draw = ImageDraw.Draw(img)
        draw.ellipse((20, 20, 180, 180), fill='#2d2d44', outline='#6c6c8a')
        draw.text((70, 65), '♪', fill='#ff6b6b')
        self.image_path = '/tmp/default_cover.jpg'
        img.save(self.image_path)
    
    def update_cover(self, new_path):
         """更新封面图片"""
         self.image_path = new_path
         self._load_image(new_path)
         return True
    
    def _load_image(self, image_path):
        try:
            if image_path.startswith('http://') or image_path.startswith('https://'):
                response = requests.get(image_path, timeout=5)
                img = Image.open(BytesIO(response.content)).convert('RGB')
            else:
                img = Image.open(image_path).convert('RGB')
            s = min(img.size)
            img = img.crop(((img.width-s)//2, (img.height-s)//2, (img.width+s)//2, (img.height+s)//2))
            img = img.resize((s, s))
            
            mask = Image.new('L', (s, s), 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0, s*20/24, s), fill=255)
            
            inner_size = int(s * self.hole_ratio)
            offset = (s - inner_size) // 2
            draw.ellipse((offset, offset, (offset + inner_size)*20/24, offset + inner_size), fill=0)
            
            result = Image.new('RGBA', (s, s), (0,0,0,0))
            result.paste(img, (0,0), mask)
            
            bg = Image.new('RGB', (s, s), (0, 0, 0))
            bg.paste(result, (0, 0), result)
            
            self.img = np.array(bg, dtype=np.int32)
            self.h, self.w_img = self.img.shape[:2]
            self.font_ratio = self.get_font_ratio()
        except Exception as e:
            print(f"⚠️ 加载封面失败: {e}", file=sys.stderr)
    
    def get_font_ratio(self):
        try:
            fd = sys.stdout.fileno()
            buf = struct.pack('HHHH', 0, 0, 0, 0)
            result = fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
            rows, cols, xpixel, ypixel = struct.unpack('HHHH', result)
            if xpixel > 0 and ypixel > 0 and rows > 0 and cols > 0:
                return (ypixel / rows) / (xpixel / cols)
        except (OSError, IOError, struct.error):
            pass
        return 1.0

    def get_ascii_lines_dual(self):
        if self.img is None:
            return []
        from PIL import Image
        img = Image.fromarray(self.img.astype(np.uint8)).rotate(self.angle)
        px = np.array(img, dtype=np.int32)
        h, w = px.shape[:2]
        
        cols = self.width
        rows = int(cols * (h/w) / self.font_ratio / 1)
        
        lines = []
        for y in range(rows):
            line = ""
            for x in range(cols):
                sx = int(x * w / cols)
                
                sy_top = int((y * 2) * h / (rows * 2))
                r1, g1, b1 = px[min(sy_top, h-1), sx]
                
                sy_bottom = int((y * 2 + 1) * h / (rows * 2))
                if sy_bottom < h:
                    r2, g2, b2 = px[sy_bottom, sx]
                else:
                    r2, g2, b2 = r1, g1, b1
                line += f"\033[38;2;{r2};{g2};{b2};48;2;{r1};{g1};{b1}m▄\033[0m"
            lines.append(line)
        return lines

# ============================================
# 主函数
# ============================================
def main():
    # ★★★ 初始化 DBus 监听器 ★★★
    listener = PlayerStatusListener()
    
    script_path = os.path.realpath(__file__)
    script_dir = os.path.dirname(script_path)

    # 配置文件：脚本在 bin/，配置在 ../config/cavacfg
    cava_cfg = os.path.normpath(os.path.join(script_dir, '..', 'config', 'cavacfg'))

    proc = subprocess.Popen(
        ['cava', '-p', cava_cfg],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    def cleanup(*_):
        proc.terminate()
        # proc.wait()
        show_cursor()
        os.system('reset')
        print("\rgood by\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    offset = 0
    spin = SpinCircle(50, 0.25)
    spin_lines = spin.get_ascii_lines_dual()
    spin.angle = (spin.angle + 3) % 360
    
    fd = sys.stdout.fileno()
    buf = struct.pack('HHHH', 0, 0, 0, 0)
    result = fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
    rows, cols, _, _ = struct.unpack('HHHH', result)

    showcircle = 0
    start_row = 0
    counter = 0
    last_cover = ""
    last_title = ""

    try:
        send_ui_started()
        # keyboard_listener()
        import threading
        threading.Thread(target=keyboard_listener, daemon=True).start()
        assert proc.stdout is not None
        global should_exit
        for line in proc.stdout:
            if should_exit:
                sys.exit(0)
            line = line.strip()
            if not line or not line[0].isdigit():
                continue

            try:
                # 发送 UI 启动信号
                # 启动键盘监听

                parts = line.strip().rstrip(';').split(';')
                heights = [int(x) for x in parts if x.strip()]
                if len(heights) != 16:
                    continue

                chars = ''.join(height_to_char(h) for h in heights)
                byte_data = chars.encode('ascii').ljust(16, b' ')[:16]

                pid, title, cover, songleft, paused = listener.get_status()
                if not paused:

                    print(format_hexdump(byte_data, offset))
                    
                    # ★★★ 从 DBus 获取状态 ★★★
                    
                    # ★★★ 封面变化时更新 ★★★
                    if cover and cover != last_cover:
                        spin.update_cover(cover)
                        last_cover = cover

                    status_text = f"▶ {title} 剩余: {songleft}次"
                    
                    sys.stdout.write("\r" + status_text + " " * 3)
                    sys.stdout.flush()
        
                    offset += 16
                    counter += 1
    
                    if counter % 10 == 0:
                        try:
                            fd = sys.stdout.fileno()
                            buf = struct.pack('HHHH', 0, 0, 0, 0)
                            result = fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
                            rows, cols, _, _ = struct.unpack('HHHH', result)

                            if title and title != last_title:
                                start_row = rows - 3
                                os.system('reset')
                                last_title = title

                            if title == '等待播放...' :
                                send_ui_started()

                    
                            if not showcircle:
                                if rows > 10:
                                    showcircle = 1
                                    start_row = rows - 3
                            else:
                                if rows <= 10:
                                    showcircle = 0
                                else:
                                    if start_row > 2:
                                        start_row -= 1
                        except:
                            pass
    
                    if showcircle and counter % 10 == 0:
                        spin_lines = spin.get_ascii_lines_dual()
                        spin.angle = (spin.angle + 3) % 360
    
                    if showcircle and spin_lines:
                        for i, spin_line in enumerate(spin_lines):
                            if rows - start_row - i > 3:
                                sys.stdout.write(f"\033[{start_row + i};1H")
                                sys.stdout.write(spin_line)
    
                    sys.stdout.write(f"\033[{rows};1H")

                else:
                    status_text = f"⏸ {title} 剩余: {songleft}次"
                    sys.stdout.write("\r" + status_text + " " * 3 )

            except Exception:
                continue

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()

def graceful_exit(signum, frame):
    print(f"\r📡 收到信号: {signum}", file=sys.stderr)
    global should_exit
    should_exit = True

signal.signal(signal.SIGTERM, graceful_exit)
signal.signal(signal.SIGINT, graceful_exit)  # ← 也注册 SIGINT

# ============================================
# 启动 - 不需要任何参数！
# ============================================
if __name__ == '__main__':
    hide_cursor()
    main()
