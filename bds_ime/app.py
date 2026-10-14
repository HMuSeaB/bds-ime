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
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
    VK_SHIFT, VK_LSHIFT, VK_RSHIFT, VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
    VK_MENU, VK_LMENU, VK_RMENU, VK_LWIN, VK_RWIN, VK_CAPITAL,
    VK_SPACE, VK_RETURN, VK_BACK, VK_ESCAPE, VK_DELETE,
    VK_OEM_MINUS, VK_OEM_PLUS, VK_OEM_COMMA, VK_OEM_PERIOD, VK_PRIOR, VK_NEXT,
    VK_NUMPAD0, VK_NUMPAD1, VK_NUMPAD2, VK_NUMPAD3, VK_NUMPAD4, VK_NUMPAD5,
    VK_NUMPAD6, VK_NUMPAD7, VK_NUMPAD8, VK_NUMPAD9
)
from bds_ime.core.input_sender import SendInputHelper, SendInputQueue
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

        # Shift 按键全周期状态跟踪 (防止组合键误切中英文)
        self.shift_pressed = False
        self.shift_combo_used = False

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
        # 剥离大模型标识前缀
        if word.startswith("🤖 "):
            word = word[3:].strip()
        self.engine.learn_word(word, self.input_buffer)
        self.input_buffer = ""
        self.all_candidates = []
        self.cand_page = 0
        self.ui.hide()

        # 统一使用严格串行化 FIFO 队列上屏，杜绝高频连击并发乱序
        SendInputQueue.enqueue(word, delay_before=0.015)

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
            if hasattr(self, 'hook_mgr'):
                self.hook_mgr.stop()
            if hasattr(self, '_mutex') and self._mutex:
                kernel32.CloseHandle(self._mutex)
                self._mutex = None
            self.ui.root.quit()
        except Exception:
            pass
        os._exit(0)

    def handle_key(self, event_type: int, vk: int) -> bool:
        """
        工业级全局按键过滤与快捷键安全调度引擎
        确保所有系统组合键 (Ctrl/Alt/Win/Shift组合) 绝对安全无冲突！
        """
        # =========================================================
        # 1. KEYUP 事件处理：精确判定 Shift 单按松开切换中英文
        # =========================================================
        if event_type in (WM_KEYUP, WM_SYSKEYUP):
            if vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
                # 只有当用户没有配合其他任何按键、单纯按下并松开 Shift 时，才切换中英文
                if self.shift_pressed and not self.shift_combo_used:
                    self.toggle_mode()
                self.shift_pressed = False
                self.shift_combo_used = False
            return False  # KEYUP 事件一律放行给操作系统

        # =========================================================
        # 2. 全方位修饰键状态实时判定 (包含左右分离物理键)
        # =========================================================
        ctrl_active = bool((user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) or
                           (user32.GetAsyncKeyState(VK_LCONTROL) & 0x8000) or
                           (user32.GetAsyncKeyState(VK_RCONTROL) & 0x8000))
        alt_active = bool((user32.GetAsyncKeyState(VK_MENU) & 0x8000) or
                          (user32.GetAsyncKeyState(VK_LMENU) & 0x8000) or
                          (user32.GetAsyncKeyState(VK_RMENU) & 0x8000))
        win_active = bool((user32.GetAsyncKeyState(VK_LWIN) & 0x8000) or
                          (user32.GetAsyncKeyState(VK_RWIN) & 0x8000))
        shift_active = bool((user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) or
                            (user32.GetAsyncKeyState(VK_LSHIFT) & 0x8000) or
                            (user32.GetAsyncKeyState(VK_RSHIFT) & 0x8000))

        # =========================================================
        # 3. 组合快捷键最高优先级免死穿透 (Ctrl / Alt / Win)
        # =========================================================
        if ctrl_active or alt_active or win_active:
            # 内部专用热键: Ctrl + Shift + Q (安全退出)
            if ctrl_active and shift_active and vk == ord('Q'):
                self.safe_exit()
                return True
            # 内部专用热键: Ctrl + Shift + S (呼出皮肤工坊)
            if ctrl_active and shift_active and vk == ord('S'):
                self.open_studio()
                return True

            # 任何其他系统快捷键 (如 Ctrl+C, Ctrl+V, Ctrl+A, Ctrl+Z, Alt+Tab, Win+D, Win+V, Win+. 等)
            # 100% 绝对不拦截，放行给宿主系统！
            if self.input_buffer:
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
            return False

        # =========================================================
        # 4. Shift 按下状态跟踪
        # =========================================================
        if vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            self.shift_pressed = True
            self.shift_combo_used = False
            return False  # 按下 Shift 时不拦截、不立即切换，等待 KeyUp

        # 用户按住了 Shift 配合其他键 (例如 Shift + A, Shift + 1)
        if shift_active:
            self.shift_combo_used = True
            # 如果按住 Shift + 字母 A~Z：用户的明确意图是输入大写英文字母！
            if ord('A') <= vk <= ord('Z'):
                if self.input_buffer:
                    # 提交已有拼音
                    self.commit_word(self.input_buffer)
                # 绝对放行给系统输入大写英文字母，严禁进拼音缓冲区！
                return False

        # =========================================================
        # 5. 大写锁定 (Caps Lock) 状态检测
        # =========================================================
        caps_locked = bool(user32.GetKeyState(VK_CAPITAL) & 1)
        if caps_locked:
            # 大写锁定开启时，字母全部直接放行给系统输入大写英文！
            return False

        # =========================================================
        # 6. 英文输入模式直接放行
        # =========================================================
        if not self.is_chinese_mode:
            return False

        # =========================================================
        # 7. 中文拼音缓冲区有内容时的交互
        # =========================================================
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

            # 数字键 1~5 (支持主键盘与小键盘) -> 选词上屏
            chosen_idx = None
            if ord('1') <= vk <= ord('5'):
                chosen_idx = vk - ord('1')
            elif VK_NUMPAD1 <= vk <= VK_NUMPAD5:
                chosen_idx = vk - VK_NUMPAD1

            if chosen_idx is not None:
                target_idx = chosen_idx + (self.cand_page * 5)
                if target_idx < len(self.all_candidates):
                    self.commit_word(self.all_candidates[target_idx])
                return True

            # 数字键 6~9 / 0 (拼音未决时直接拦截，防止数字渗漏污染输入框)
            if (ord('6') <= vk <= ord('9') or vk == ord('0') or
                VK_NUMPAD6 <= vk <= VK_NUMPAD9 or vk == VK_NUMPAD0):
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

            # 回车键 -> 直接上屏原始英文字母 (走 FIFO 串行队列)
            if vk == VK_RETURN:
                raw = self.input_buffer
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
                SendInputQueue.enqueue(raw, delay_before=0.01)
                return True

            # 退格键 (Backspace)
            if vk == VK_BACK:
                self.input_buffer = self.input_buffer[:-1]
                self.update_pinyin()
                return True

            # Delete / Esc (清空未决输入并关闭候选窗口，消费该事件)
            if vk in (VK_DELETE, VK_ESCAPE):
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
                return True

        # =========================================================
        # 8. 拼音字母输入 (仅限未按住 Shift 时的 A~Z)
        # =========================================================
        if ord('A') <= vk <= ord('Z'):
            ch = chr(vk).lower()
            self.input_buffer += ch
            self.update_pinyin()
            return True

        # =========================================================
        # 9. 中文全角标点符号自动映射 (仅在无未决拼音时生效)
        # =========================================================
        if not self.input_buffer and self.is_chinese_mode:
            punc = None
            if vk == VK_OEM_COMMA:
                punc = "《" if shift_active else "，"
            elif vk == VK_OEM_PERIOD:
                punc = "》" if shift_active else "。"
            elif vk == 0xBF:  # VK_OEM_2 (/ ?)
                punc = "？" if shift_active else "、"
            elif vk == 0xBA:  # VK_OEM_1 (; :)
                punc = "：" if shift_active else "；"
            elif vk == ord('1') and shift_active:
                punc = "！"
            elif vk == ord('6') and shift_active:
                punc = "……"
            elif vk == 0xC0 and shift_active:  # VK_OEM_3 (~ `)
                punc = "～"

            if punc:
                SendInputQueue.enqueue(punc, delay_before=0.01)
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
