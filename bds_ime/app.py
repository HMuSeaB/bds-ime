"""
BDS-IME 应用程序主控制器 (Application Controller)
模块化统一调度核心输入引擎、界面呈现、嵌入式工坊与大模型补全。
"""

import os
import sys
import time
import queue
import ctypes
from ctypes import wintypes
import threading
import tkinter as tk

from bds_ime.config import (
    DB_PATH, SOUND_FILE, MUTEX_NAME, SKIN_FLAG_FILE,
    load_skin_config
)
from bds_ime.core.engine import PinyinEngine
from bds_ime.core.sound import SoundHelper
from bds_ime.core.ai_client import AICandidateHelper
from bds_ime.core.hook import (
    KeyboardHookManager,
    VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_SPACE, VK_RETURN, VK_BACK,
    VK_ESCAPE, VK_DELETE, VK_OEM_MINUS, VK_OEM_PLUS,
    VK_OEM_COMMA, VK_OEM_PERIOD, VK_PRIOR, VK_NEXT
)
from bds_ime.core.input_sender import SendInputHelper
from bds_ime.ui.native_candidate import NativeCandidateWindow
from bds_ime.studio.server import EmbeddedStudioServer

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class BDSInputMethodApp:
    def __init__(self):
        # 1. 单实例互斥锁
        self._mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            print("[!] BDS-IME 已在后台运行中，请勿重复启动。")
            os._exit(0)

        # 2. 核心子系统初始化
        self.engine = PinyinEngine(DB_PATH)
        self.sound = SoundHelper(SOUND_FILE)
        self.skin_cfg = load_skin_config()

        # 3. 水杉同款大模型联想
        self.ai_helper = AICandidateHelper(lambda: self.skin_cfg)

        # 4. 状态机
        self.input_buffer = ""
        self.all_candidates = []
        self.cand_page = 0
        self.pinyin_disp = ""
        self.is_chinese_mode = True
        self.reload_counter = 0

        # 5. UI 呈现层
        self.event_queue = queue.Queue()
        self.ui = NativeCandidateWindow(self.commit_word)
        if self.skin_cfg:
            self.ui.apply_skin(self.skin_cfg)

        # 6. 内置皮肤创作工坊嵌入式服务 (后台静默启动)
        self.studio = EmbeddedStudioServer(18888)
        self.studio.start_background()

        # 7. 桌面状态小药丸
        self._setup_status_pill()

        # 8. 启动底层键盘钩子
        self.hook_mgr = KeyboardHookManager(self.handle_key)
        self.hook_mgr.start()

        # 9. 欢迎就绪弹窗与击键音
        self._show_startup_toast()
        self.sound.play()

        # 10. 事件循环轮询
        self.ui.root.after(10, self._process_queue)

    def run(self):
        """进入 GUI 主消息循环"""
        self.ui.root.mainloop()

    def update_pinyin(self):
        """输入拼音变化时查询词库与异步预测"""
        self.cand_page = 0
        if self.input_buffer:
            self.sound.play()
            self.pinyin_disp, self.all_candidates = self.engine.query(self.input_buffer, limit=60)
            self._render_current_page()

            # 异步触发大模型智能长句联想推测 (水杉同款)
            if len(self.input_buffer) >= 4:
                self.ai_helper.async_predict(
                    self.pinyin_disp,
                    lambda ai_text: self.event_queue.put(("AI_CANDIDATE", ai_text))
                )
        else:
            self.all_candidates = []
            self.ui.hide()

    def _render_current_page(self):
        total_cands = len(self.all_candidates)
        total_pages = max(1, (total_cands + 4) // 5)
        self.cand_page = max(0, min(self.cand_page, total_pages - 1))
        start_idx = self.cand_page * 5
        page_cands = self.all_candidates[start_idx : start_idx + 5]
        self.ui.show_candidates(self.pinyin_disp, page_cands, self.cand_page, total_pages)

    def commit_word(self, word: str):
        self.sound.play()
        # 剥离大模型前缀
        if word.startswith("🤖 "):
            word = word[3:].strip()
        self.engine.learn_word(word, self.input_buffer)
        self.input_buffer = ""
        self.all_candidates = []
        self.cand_page = 0
        self.ui.hide()

        def do_send():
            time.sleep(0.015)
            SendInputHelper.send_unicode_string(word)
        threading.Thread(target=do_send, daemon=True).start()

    def toggle_mode(self):
        self.is_chinese_mode = not self.is_chinese_mode
        self.pill_lbl.config(
            text="中" if self.is_chinese_mode else "英",
            bg="#212529" if self.is_chinese_mode else "#495057"
        )
        if not self.is_chinese_mode:
            self.input_buffer = ""
            self.ui.hide()

    def open_studio(self):
        """打开内置皮肤工坊与调色台"""
        self.studio.open_in_browser()

    def safe_exit(self):
        try:
            self.ui.root.quit()
        except Exception:
            pass
        os._exit(0)

    def handle_key(self, vk: int) -> bool:
        """全局按键过滤与处理"""
        # 1. 组合快捷键与修饰键绝对穿透：Ctrl、Alt、Win 放行给操作系统
        if (user32.GetAsyncKeyState(0x11) & 0x8000) or \
           (user32.GetAsyncKeyState(0x12) & 0x8000) or \
           (user32.GetAsyncKeyState(0x5B) & 0x8000) or \
           (user32.GetAsyncKeyState(0x5C) & 0x8000):
            # 全局快捷退出热键: Ctrl + Shift + Q
            if vk == ord('Q') and (user32.GetAsyncKeyState(0x10) & 0x8000):
                self.safe_exit()
                return True
            # 打开皮肤创作工坊热键: Ctrl + Shift + S
            if vk == ord('S') and (user32.GetAsyncKeyState(0x10) & 0x8000):
                self.open_studio()
                return True
            if self.input_buffer:
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
            return False

        # Shift 切换中英文
        if vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            if not self.input_buffer:
                self.toggle_mode()
            return False

        if not self.is_chinese_mode:
            return False

        # 缓冲区有内容时的处理
        if self.input_buffer:
            # 空格 -> 选中第 1 个候选词上屏
            if vk == VK_SPACE:
                total_cands = len(self.all_candidates)
                if total_cands > 0:
                    start_idx = self.cand_page * 5
                    self.commit_word(self.all_candidates[start_idx])
                else:
                    self.commit_word(self.input_buffer)
                return True

            # 数字键 1~5 -> 选词上屏
            if ord('1') <= vk <= ord('5'):
                idx = (vk - ord('1')) + (self.cand_page * 5)
                if idx < len(self.all_candidates):
                    self.commit_word(self.all_candidates[idx])
                    return True

            # 翻页键 (- / =, , / ., PageUp / PageDown)
            if vk in (VK_OEM_MINUS, VK_OEM_COMMA, VK_PRIOR):
                if self.cand_page > 0:
                    self.cand_page -= 1
                    self._render_current_page()
                return True

            if vk in (VK_OEM_PLUS, VK_OEM_PERIOD, VK_NEXT):
                total_pages = max(1, (len(self.all_candidates) + 4) // 5)
                if self.cand_page < total_pages - 1:
                    self.cand_page += 1
                    self._render_current_page()
                return True

            # 回车键 -> 直接上屏原始英文字母
            if vk == VK_RETURN:
                raw = self.input_buffer
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
                threading.Thread(target=lambda: SendInputHelper.send_unicode_string(raw), daemon=True).start()
                return True

            # 退格键
            if vk == VK_BACK:
                self.input_buffer = self.input_buffer[:-1]
                self.update_pinyin()
                return True

            # Delete / Esc
            if vk in (VK_DELETE, VK_ESCAPE):
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
                return True

        # 输入字母 A~Z
        if ord('A') <= vk <= ord('Z'):
            ch = chr(vk).lower()
            self.input_buffer += ch
            self.update_pinyin()
            return True

        return False

    def _process_queue(self):
        while not self.event_queue.empty():
            item = self.event_queue.get_nowait()
            action, data = item
            if action == "AI_CANDIDATE":
                ai_text = data
                ai_formatted = f"🤖 {ai_text}"
                if self.input_buffer and ai_formatted not in self.all_candidates and ai_text not in self.all_candidates:
                    insert_pos = min(4, len(self.all_candidates))
                    self.all_candidates.insert(insert_pos, ai_formatted)
                    self._render_current_page()

        # 检查皮肤热重载信号
        self.reload_counter = (self.reload_counter + 1) % 30
        if self.reload_counter == 0:
            if SKIN_FLAG_FILE.exists():
                try:
                    SKIN_FLAG_FILE.unlink(missing_ok=True)
                    new_skin = load_skin_config()
                    if new_skin:
                        self.skin_cfg = new_skin
                        self.ui.apply_skin(new_skin)
                        print(f"[+] 动态热换肤已生效: {new_skin.get('name')}")
                except Exception:
                    pass

        self.ui.root.after(10, self._process_queue)

    def _setup_status_pill(self):
        """屏幕右下角中英状态悬浮药丸"""
        self.pill = tk.Toplevel(self.ui.root)
        self.pill.overrideredirect(True)
        self.pill.attributes("-topmost", True)
        self.pill.attributes("-alpha", 0.90)

        sw = self.ui.root.winfo_screenwidth()
        sh = self.ui.root.winfo_screenheight()
        self.pill.geometry(f"52x28+{sw - 85}+{sh - 95}")

        self.pill_lbl = tk.Label(
            self.pill, text="中", font=("Segoe UI", 10, "bold"),
            bg="#212529", fg="#ffffff", cursor="hand2"
        )
        self.pill_lbl.pack(fill="both", expand=True)
        self.pill_lbl.bind("<Button-1>", lambda e: self.toggle_mode())
        self.pill_lbl.bind("<Button-2>", lambda e: self.open_studio())  # 鼠标中键打开工坊
        self.pill_lbl.bind("<Button-3>", lambda e: self.safe_exit())

    def _show_startup_toast(self):
        try:
            toast = tk.Toplevel(self.ui.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.attributes("-alpha", 0.96)
            toast.config(bg="#ffb6c1")

            frame = tk.Frame(toast, bg="#fefbf9", padx=18, pady=12)
            frame.pack(padx=2, pady=2, fill="both", expand=True)

            title = tk.Label(
                frame, text="🐾 BDS-IME 工业级一体化输入法已就绪！",
                font=("Microsoft YaHei", 12, "bold"), fg="#d63384", bg="#fefbf9"
            )
            title.pack(anchor="w")

            desc = tk.Label(
                frame,
                text="• 快捷键保护：Ctrl+C/V、Alt+Tab 100% 原生穿透\n• 皮肤工坊：按 Ctrl+Shift+S 打开专属可视化皮肤设计台\n• 智能联想：已内置水杉同款 DeepSeek / Ollama 智能长句补全",
                font=("Microsoft YaHei", 9), fg="#495057", bg="#fefbf9", justify="left"
            )
            desc.pack(anchor="w", pady=(4, 0))

            sw = self.ui.root.winfo_screenwidth()
            sh = self.ui.root.winfo_screenheight()
            w, h = 460, 110
            toast.geometry(f"{w}x{h}+{(sw - w)//2}+{sh - 180}")
            toast.after(3500, lambda: toast.destroy())
        except Exception:
            pass
