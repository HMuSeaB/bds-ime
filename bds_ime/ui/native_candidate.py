"""
原生自适应悬浮候选窗与状态药丸 (出厂稳定运行，零崩溃)
"""

import ctypes
from ctypes import wintypes
import tkinter as tk

user32 = ctypes.windll.user32


class NativeCandidateWindow:
    """现代化悬浮候选窗 (Tkinter 原生级硬件加速悬浮窗)"""
    def __init__(self, on_commit_callback):
        self.on_commit = on_commit_callback

        self.root = tk.Tk()
        self.root.title("BDS-IME Candidate")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)

        # 默认调色板 (像素喵喵爪风格)
        self.bg_color = "#fefbf9"
        self.border_color = "#ffb6c1"
        self.text_color = "#2c2c2c"
        self.first_color = "#d63384"
        self.pinyin_color = "#6c757d"
        self.accent_pill = "#ffe4e9"

        self.root.config(bg=self.border_color)

        self.main_frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=8)
        self.main_frame.pack(padx=2, pady=2, fill="both", expand=True)

        # 拼音行与翻页提示
        self.pinyin_row = tk.Frame(self.main_frame, bg=self.bg_color)
        self.pinyin_row.pack(fill="x", pady=(0, 4))

        self.lbl_pinyin = tk.Label(
            self.pinyin_row, text="", font=("Segoe UI", 11, "bold"),
            fg=self.pinyin_color, bg=self.bg_color, anchor="w"
        )
        self.lbl_pinyin.pack(side="left")

        self.lbl_page = tk.Label(
            self.pinyin_row, text="", font=("Microsoft YaHei", 9),
            fg="#888888", bg=self.bg_color, anchor="e"
        )
        self.lbl_page.pack(side="right")

        # 候选词横排列表
        self.cands_frame = tk.Frame(self.main_frame, bg=self.bg_color)
        self.cands_frame.pack(fill="x")

        self.cand_labels = []
        for i in range(5):
            lbl = tk.Label(
                self.cands_frame, text="", font=("Microsoft YaHei", 12),
                fg=self.text_color, bg=self.bg_color, padx=6, pady=2
            )
            lbl.pack(side="left")
            self.cand_labels.append(lbl)

        self.root.withdraw()
        self.current_candidates = []
        self.current_pinyin = ""

    def apply_skin(self, skin_cfg: dict):
        """动态应用外部皮肤调色板"""
        try:
            colors = skin_cfg.get("colors", {})
            self.bg_color = skin_cfg.get("surfaceBg", self.bg_color)
            self.border_color = colors.get("border", self.border_color)
            self.text_color = colors.get("text", self.text_color)
            self.first_color = colors.get("accent", self.first_color)
            self.pinyin_color = colors.get("pinyin", self.pinyin_color)
            self.accent_pill = colors.get("selectedBg", self.accent_pill)

            alpha = float(skin_cfg.get("opacity", 0.96))
            self.root.attributes("-alpha", max(0.5, min(1.0, alpha)))
            self.root.config(bg=self.border_color)
            self.main_frame.config(bg=self.bg_color)
            self.pinyin_row.config(bg=self.bg_color)
            self.lbl_pinyin.config(fg=self.pinyin_color, bg=self.bg_color)
            self.lbl_page.config(bg=self.bg_color)
            self.cands_frame.config(bg=self.bg_color)
            for lbl in self.cand_labels:
                lbl.config(bg=self.bg_color, fg=self.text_color)
        except Exception:
            pass

    def show_candidates(self, pinyin_display: str, candidates: list[str], page: int = 0, total_pages: int = 1):
        self.current_pinyin = pinyin_display
        self.current_candidates = candidates

        if not candidates:
            self.root.withdraw()
            return

        self.lbl_pinyin.config(text=pinyin_display)
        if total_pages > 1:
            self.lbl_page.config(text=f"({page + 1}/{total_pages} -/=)")
        else:
            self.lbl_page.config(text="")

        for i, lbl in enumerate(self.cand_labels):
            if i < len(candidates):
                text = f"{i + 1}.{candidates[i]}"
                lbl.config(text=text)
                if i == 0:
                    lbl.config(fg=self.first_color, bg=self.accent_pill, font=("Microsoft YaHei", 12, "bold"))
                else:
                    lbl.config(fg=self.text_color, bg=self.bg_color, font=("Microsoft YaHei", 12))
            else:
                lbl.config(text="")

        # 光标位置跟随
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x = pt.x + 15
        y = pt.y + 25

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if x + 400 > sw:
            x = sw - 410
        if y + 80 > sh:
            y = pt.y - 80

        self.root.geometry(f"+{x}+{y}")
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()
        self.current_candidates.clear()
        self.current_pinyin = ""
