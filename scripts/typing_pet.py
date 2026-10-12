"""
BDS 桌面打字萌宠伴侣 (Desktop Typing Companion)
零侵入、免换输入法。打字时同步呈现 BDS 萌宠动效与原版敲击音效。
"""

import os
import sys
import time
import queue
import ctypes
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

# 开启 Windows 高 DPI 适配，防止模糊
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Win32 音效 API
winmm = ctypes.windll.winmm
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_SPACE = 0x20
VK_BACK = 0x08
VK_RETURN = 0x0D

BASE_DIR = Path(__file__).resolve().parent.parent


class SoundEngine:
    """低延迟多通道 BDS 原版按键音效引擎"""
    def __init__(self):
        self.sound_packs = {
            "cat": BASE_DIR / "sound_packs" / "cat",
            "rabbit_cute": BASE_DIR / "sound_packs" / "rabbit_cute",
            "rabbit_ios": BASE_DIR / "sound_packs" / "rabbit_ios",
            "rabbit_bb": BASE_DIR / "sound_packs" / "rabbit_blackberry"
        }
        self.current_pack = "cat"
        self.muted = False
        self.pool_size = 6
        self.alias_idx = 0
        self.opened_aliases = []
        self._init_aliases()

    def _init_aliases(self):
        # 关闭老别名
        for alias in self.opened_aliases:
            winmm.mciSendStringW(f"close {alias}", None, 0, None)
        self.opened_aliases.clear()

        pack_dir = self.sound_packs.get(self.current_pack)
        if not pack_dir or not pack_dir.exists():
            return

        # 预加载通用按键音与功能按键音
        files = {
            "key1": pack_dir / "x1an.ogg",
            "key2": pack_dir / "x2gn.ogg",
            "space": pack_dir / "x4kg.ogg",
            "back": pack_dir / "x3sc.ogg",
            "enter": pack_dir / "x5fs.ogg",
        }

        self.key_aliases = []
        for name, p in files.items():
            if p.exists():
                safe_p = str(p.resolve()).replace("\\", "/")
                # 为常用键建立轮询通道，防止连续打字相互切断
                for i in range(self.pool_size):
                    alias = f"snd_{name}_{i}"
                    cmd = f'open "{safe_p}" type mpegvideo alias {alias}'
                    ret = winmm.mciSendStringW(cmd, None, 0, None)
                    if ret == 0:
                        self.opened_aliases.append(alias)
                        if name in ["key1", "key2"]:
                            self.key_aliases.append(alias)

    def set_pack(self, pack_name: str):
        if pack_name in self.sound_packs:
            self.current_pack = pack_name
            self._init_aliases()

    def play_key(self, vk_code: int):
        if self.muted:
            return
        
        target_alias = None
        if vk_code == VK_SPACE:
            target_alias = f"snd_space_{self.alias_idx % self.pool_size}"
        elif vk_code == VK_BACK:
            target_alias = f"snd_back_{self.alias_idx % self.pool_size}"
        elif vk_code == VK_RETURN:
            target_alias = f"snd_enter_{self.alias_idx % self.pool_size}"
        else:
            if self.key_aliases:
                target_alias = self.key_aliases[self.alias_idx % len(self.key_aliases)]
        
        if target_alias:
            self.alias_idx += 1
            winmm.mciSendStringW(f"play {target_alias} from 0", None, 0, None)

    def close(self):
        for alias in self.opened_aliases:
            winmm.mciSendStringW(f"close {alias}", None, 0, None)


class DesktopPetApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BDS Typing Companion")

        # 窗口无边框、置顶
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # 纯黑作为透明透色
        self.trans_color = "#010101"
        self.root.attributes("-transparentcolor", self.trans_color)
        self.root.config(bg=self.trans_color)

        self.sound_engine = SoundEngine()
        self.event_queue = queue.Queue()

        # 皮肤数据
        self.pet_skins = {
            "cat": {
                "name": "🐾 像素喵喵爪",
                "img": BASE_DIR / "pet_assets" / "cat_pet.png",
                "w": 180, "h": 90,
                "default_pack": "cat"
            },
            "rabbit": {
                "name": "🐰 小板爪爪兔",
                "img": BASE_DIR / "pet_assets" / "rabbit_pet.png",
                "w": 180, "h": 96,
                "default_pack": "rabbit_cute"
            }
        }
        self.current_skin = "cat"

        # 动画状态
        self.is_bouncing = False
        self.scale_factor = 1.0

        # UI 元素
        self.label = tk.Label(self.root, bg=self.trans_color, bd=0)
        self.label.pack()

        # 初始定位在屏幕右下角（任务栏上方）
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.pos_x = sw - 240
        self.pos_y = sh - 200
        self.root.geometry(f"+{self.pos_x}+{self.pos_y}")

        # 加载图像
        self._load_pet_image()

        # 鼠标拖拽事件
        self.label.bind("<ButtonPress-1>", self._start_drag)
        self.label.bind("<B1-Motion>", self._do_drag)
        self.label.bind("<Button-3>", self._show_context_menu)

        # 构建右键菜单
        self._build_menu()

        # 启动键盘监听钩子
        self._start_keyboard_hook()

        # 定时器消费按键动效
        self.root.after(20, self._process_events)

    def _load_pet_image(self, pressed=False):
        skin_cfg = self.pet_skins[self.current_skin]
        img_path = skin_cfg["img"]
        if not img_path.exists():
            return

        im = Image.open(img_path).convert("RGBA")
        base_w, base_h = skin_cfg["w"], skin_cfg["h"]
        
        # 按下时产生 Q 弹形变（横向稍微压扁，模拟拍打爪子）
        if pressed:
            w = int(base_w * 1.08)
            h = int(base_h * 0.88)
        else:
            w = base_w
            h = base_h

        im_resized = im.resize((w, h), Image.Resampling.LANCZOS)
        
        # 将透明区域的纯黑设为透色保护
        self.tk_img = ImageTk.PhotoImage(im_resized)
        self.label.config(image=self.tk_img)

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        self.pos_x += dx
        self.pos_y += dy
        self.root.geometry(f"+{self.pos_x}+{self.pos_y}")

    def _build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0, bg="#1e222a", fg="#ffffff", activebackground="#3e4451")
        
        # 皮肤切换
        skin_menu = tk.Menu(self.menu, tearoff=0, bg="#1e222a", fg="#ffffff", activebackground="#3e4451")
        skin_menu.add_command(label="🐾 像素喵喵爪", command=lambda: self.switch_skin("cat"))
        skin_menu.add_command(label="🐰 小板爪爪兔", command=lambda: self.switch_skin("rabbit"))
        self.menu.add_cascade(label="🎨 切换皮肤形象", menu=skin_menu)

        # 音效切换
        sound_menu = tk.Menu(self.menu, tearoff=0, bg="#1e222a", fg="#ffffff", activebackground="#3e4451")
        sound_menu.add_command(label="🐱 喵喵爪原声 (Cat)", command=lambda: self.sound_engine.set_pack("cat"))
        sound_menu.add_command(label="🐰 爪爪兔可爱音", command=lambda: self.sound_engine.set_pack("rabbit_cute"))
        sound_menu.add_command(label="📱 iOS 经典机械音", command=lambda: self.sound_engine.set_pack("rabbit_ios"))
        sound_menu.add_command(label="🍇 黑莓清脆按键音", command=lambda: self.sound_engine.set_pack("rabbit_bb"))
        sound_menu.add_separator()
        sound_menu.add_command(label="🔇 静音模式 (仅动效)", command=self.toggle_mute)
        self.menu.add_cascade(label="🔊 切换打字音效", menu=sound_menu)

        self.menu.add_separator()
        self.menu.add_command(label="📌 复位到右下角", command=self.reset_pos)
        self.menu.add_command(label="❌ 退出伴侣", command=self.quit)

    def _show_context_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def switch_skin(self, skin_key: str):
        self.current_skin = skin_key
        cfg = self.pet_skins[skin_key]
        self.sound_engine.set_pack(cfg["default_pack"])
        self._load_pet_image(pressed=False)

    def toggle_mute(self):
        self.sound_engine.muted = not self.sound_engine.muted

    def reset_pos(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.pos_x = sw - 240
        self.pos_y = sh - 200
        self.root.geometry(f"+{self.pos_x}+{self.pos_y}")

    def on_key_event(self, vk_code: int):
        self.event_queue.put(vk_code)

    def _process_events(self):
        has_key = False
        last_vk = None
        while not self.event_queue.empty():
            last_vk = self.event_queue.get_nowait()
            has_key = True

        if has_key:
            # 播放按键音
            self.sound_engine.play_key(last_vk)
            # 执行下按弹跳
            self._load_pet_image(pressed=True)
            self.root.after(80, lambda: self._load_pet_image(pressed=False))

        self.root.after(20, self._process_events)

    def _start_keyboard_hook(self):
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)

        def hook_cb(nCode, wParam, lParam):
            if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                vk = ctypes.cast(lParam, ctypes.POINTER(ctypes.c_ulong)).contents.value
                self.on_key_event(vk)
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._hook_cb_ref = HOOKPROC(hook_cb)

        def hook_thread():
            h_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_cb_ref, None, 0)
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            user32.UnhookWindowsHookEx(h_hook)

        t = threading.Thread(target=hook_thread, daemon=True)
        t.start()

    def quit(self):
        self.sound_engine.close()
        self.root.destroy()
        sys.exit(0)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DesktopPetApp()
    app.run()
