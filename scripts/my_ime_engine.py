"""
我的专属轻量 Windows 输入法引擎原型 (My IME Engine MVP)
特性：
1. 真正能打字：基于 65,000+ 高频词库，在微信、记事本、浏览器中输入拼音，空格上屏汉字！
2. 零侵入：不修改系统注册表，随开随关，安全稳定。
3. 原生集成 BDS 皮肤美学与按键音效：候选窗采用 BDS 视觉排版，击键伴随原版音效。
4. 动态调频：支持记忆用户习惯，常用词优先置顶。
"""

import os
import sys
import time
import json
import re
import queue
import sqlite3
import ctypes
from ctypes import wintypes
import threading
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import ttk

# Windows 高 DPI 适配
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# 终端 UTF-8 保护
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
winmm = ctypes.windll.winmm

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

# 严格配置 64 位 Windows 下 User32 HOOK 接口的参数类型 (避免 OverflowError: int too long)
HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = wintypes.LPARAM
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

VK_BACK = 0x08
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_DELETE = 0x2E
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "pinyin_dict.db"

# 标准普通话拼音音节全集
PINYIN_SYLLABLES = set([
    'a', 'ai', 'an', 'ang', 'ao', 'ba', 'bai', 'ban', 'bang', 'bao', 'bei', 'ben', 'beng', 'bi', 'bian', 'biao', 'bie', 'bin', 'bing', 'bo', 'bu',
    'ca', 'cai', 'can', 'cang', 'cao', 'ce', 'cen', 'ceng', 'cha', 'chai', 'chan', 'chang', 'chao', 'che', 'chen', 'cheng', 'chi', 'chong', 'chou', 'chu', 'chua', 'chuai', 'chuan', 'chuang', 'chui', 'chun', 'chuo', 'ci', 'cong', 'cou', 'cu', 'cuan', 'cui', 'cun', 'cuo',
    'da', 'dai', 'dan', 'dang', 'dao', 'de', 'dei', 'den', 'deng', 'di', 'dia', 'dian', 'diao', 'die', 'ding', 'diu', 'dong', 'dou', 'du', 'duan', 'dui', 'dun', 'duo',
    'e', 'ei', 'en', 'eng', 'er', 'fa', 'fan', 'fang', 'fei', 'fen', 'feng', 'fiao', 'fo', 'fou', 'fu',
    'ga', 'gai', 'gan', 'gang', 'gao', 'ge', 'gei', 'gen', 'geng', 'gong', 'gou', 'gu', 'gua', 'guai', 'guan', 'guang', 'gui', 'gun', 'guo',
    'ha', 'hai', 'han', 'hang', 'hao', 'he', 'hei', 'hen', 'heng', 'hong', 'hou', 'hu', 'hua', 'huai', 'huan', 'huang', 'hui', 'hun', 'huo',
    'ji', 'jia', 'jian', 'jiang', 'jiao', 'jie', 'jin', 'jing', 'jiong', 'jiu', 'ju', 'juan', 'jue', 'jun',
    'ka', 'kai', 'kan', 'kang', 'kao', 'ke', 'kei', 'ken', 'keng', 'kong', 'kou', 'ku', 'kua', 'kuai', 'kuan', 'kuang', 'kui', 'kun', 'kuo',
    'la', 'lai', 'lan', 'lang', 'lao', 'le', 'lei', 'leng', 'li', 'lia', 'lian', 'liang', 'liao', 'lie', 'lin', 'ling', 'liu', 'lo', 'long', 'lou', 'lu', 'luan', 'lun', 'luo', 'lv', 'lve',
    'ma', 'mai', 'man', 'mang', 'mao', 'me', 'mei', 'men', 'meng', 'mi', 'mian', 'miao', 'mie', 'min', 'ming', 'miu', 'mo', 'mou', 'mu',
    'na', 'nai', 'nan', 'nang', 'nao', 'ne', 'nei', 'nen', 'neng', 'ni', 'nia', 'nian', 'niang', 'niao', 'nie', 'nin', 'ning', 'niu', 'nong', 'nou', 'nu', 'nuan', 'nun', 'nuo', 'nv', 'nve',
    'o', 'ou', 'pa', 'pai', 'pan', 'pang', 'pao', 'pei', 'pen', 'peng', 'pi', 'pian', 'piao', 'pie', 'pin', 'ping', 'po', 'pou', 'pu',
    'qi', 'qia', 'qian', 'qiang', 'qiao', 'qie', 'qin', 'qing', 'qiong', 'qiu', 'qu', 'quan', 'que', 'qun',
    'ran', 'rang', 'rao', 're', 'ren', 'reng', 'ri', 'rong', 'rou', 'ru', 'rua', 'ruan', 'rui', 'run', 'ruo',
    'sa', 'sai', 'san', 'sang', 'sao', 'se', 'sen', 'seng', 'sha', 'shai', 'shan', 'shang', 'shao', 'she', 'shei', 'shen', 'sheng', 'shi', 'shou', 'shu', 'shua', 'shuai', 'shuan', 'shuang', 'shui', 'shun', 'shuo', 'si', 'song', 'sou', 'su', 'suan', 'sui', 'sun', 'suo',
    'ta', 'tai', 'tan', 'tang', 'tao', 'te', 'tei', 'teng', 'ti', 'tian', 'tiao', 'tie', 'ting', 'tong', 'tou', 'tu', 'tuan', 'tui', 'tun', 'tuo',
    'wa', 'wai', 'wan', 'wang', 'wei', 'wen', 'weng', 'wo', 'wu',
    'xi', 'xia', 'xian', 'xiang', 'xiao', 'xie', 'xin', 'xing', 'xiong', 'xiu', 'xu', 'xuan', 'xue', 'xun',
    'ya', 'yan', 'yang', 'yao', 'ye', 'yi', 'yin', 'ying', 'yo', 'yong', 'you', 'yu', 'yuan', 'yue', 'yun',
    'za', 'zai', 'zan', 'zang', 'zao', 'ze', 'zei', 'zen', 'zeng', 'zha', 'zhai', 'zhan', 'zhang', 'zhao', 'zhe', 'zhen', 'zheng', 'zhi', 'zhong', 'zhou', 'zhu', 'zhua', 'zhuai', 'zhuan', 'zhuang', 'zhui', 'zhun', 'zhuo', 'zi', 'zong', 'zou', 'zu', 'zuan', 'zui', 'zun', 'zuo'
])


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_u", _INPUT_UNION)
    ]

user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint

class SendInputHelper:
    """Windows 原生 Unicode 模拟上屏引擎"""
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    INPUT_KEYBOARD = 1

    @classmethod
    def send_unicode_string(cls, text: str):
        """将选中的文本逐字安全注入到当前活动窗口"""
        for ch in text:
            code = ord(ch)
            # 按下
            inp_down = INPUT(type=cls.INPUT_KEYBOARD)
            inp_down.ki.wVk = 0
            inp_down.ki.wScan = code
            inp_down.ki.dwFlags = cls.KEYEVENTF_UNICODE
            inp_down.ki.time = 0
            inp_down.ki.dwExtraInfo = 0
            user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))

            # 抬起
            inp_up = INPUT(type=cls.INPUT_KEYBOARD)
            inp_up.ki.wVk = 0
            inp_up.ki.wScan = code
            inp_up.ki.dwFlags = cls.KEYEVENTF_UNICODE | cls.KEYEVENTF_KEYUP
            inp_up.ki.time = 0
            inp_up.ki.dwExtraInfo = 0
            user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))


class PinyinEngine:
    """拼音切分、模糊联想与词典检索引擎"""
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)

    def segment(self, s: str) -> list[str]:
        """正向最大匹配切分拼音"""
        res = []
        i = 0
        n = len(s)
        while i < n:
            matched = None
            for length in range(min(6, n - i), 0, -1):
                sub = s[i:i+length]
                if sub in PINYIN_SYLLABLES:
                    matched = sub
                    i += length
                    break
            if matched:
                res.append(matched)
            else:
                res.append(s[i])
                i += 1
        return res

    def query(self, raw_input: str, limit: int = 60) -> tuple[str, list[str]]:
        """输入拼音字母串，输出分词显示与丰富候选词列表 (支持长句贪心智能拼接)"""
        raw = raw_input.lower()
        if not raw:
            return "", []

        syllables = self.segment(raw)
        pinyin_display = "'".join(syllables)
        compact_py = "".join(syllables)

        cur = self.conn.cursor()
        # 1. 优先完全精准匹配 (获取全量匹配词汇)
        cur.execute(
            "SELECT word FROM words WHERE pinyin = ? ORDER BY weight DESC LIMIT ?",
            (compact_py, limit)
        )
        candidates = [r[0] for r in cur.fetchall()]

        # 2. 如果包含多个音节，执行贪心最长词组拼接 (如 kuai'jie'jian'yong'bu'liao -> 快捷键 + 用不了)
        if len(syllables) > 1:
            assembled_chunks = []
            idx = 0
            n_syl = len(syllables)
            while idx < n_syl:
                matched_word = None
                for span in range(min(4, n_syl - idx), 0, -1):
                    chunk_py = "".join(syllables[idx : idx + span])
                    cur.execute(
                        "SELECT word FROM words WHERE pinyin = ? ORDER BY weight DESC LIMIT 1",
                        (chunk_py,)
                    )
                    row = cur.fetchone()
                    if row:
                        matched_word = row[0]
                        idx += span
                        break
                if matched_word:
                    assembled_chunks.append(matched_word)
                else:
                    assembled_chunks.append(syllables[idx])
                    idx += 1
            if assembled_chunks:
                full_phrase = "".join(assembled_chunks)
                if full_phrase not in candidates:
                    candidates.insert(0, full_phrase)

        # 3. 不足时前缀模糊联想补全
        if len(candidates) < limit:
            needed = limit - len(candidates)
            placeholders = ",".join(["?"] * len(candidates)) if candidates else "''"
            sql = f"""
                SELECT word FROM words 
                WHERE pinyin LIKE ? AND word NOT IN ({placeholders}) 
                ORDER BY weight DESC LIMIT ?
            """
            cur.execute(sql, [f"{compact_py}%"] + candidates + [needed])
            more = [r[0] for r in cur.fetchall()]
            candidates.extend(more)

        return pinyin_display, candidates

    def learn_word(self, word: str, pinyin: str):
        """用户选词调频自学习"""
        try:
            cur = self.conn.cursor()
            cur.execute("UPDATE words SET weight = weight + 50 WHERE word = ? AND pinyin = ?", (word, pinyin.replace("'", "")))
            self.conn.commit()
        except Exception:
            pass


class SoundHelper:
    """按键原声音效支持"""
    def __init__(self):
        self.sound_file = BASE_DIR / "sound_packs" / "cat" / "x1an.ogg"
        self.alias_idx = 0
        if self.sound_file.exists():
            safe_p = str(self.sound_file.resolve()).replace("\\", "/")
            for i in range(4):
                winmm.mciSendStringW(f'open "{safe_p}" type mpegvideo alias ime_snd_{i}', None, 0, None)

    def play(self):
        if self.sound_file.exists():
            alias = f"ime_snd_{self.alias_idx % 4}"
            self.alias_idx += 1
            winmm.mciSendStringW(f"play {alias} from 0", None, 0, None)


class AICandidateHelper:
    """水杉同款大模型长句联想推测客户端 (兼容 OpenAI/DeepSeek/Ollama 规范)"""
    def __init__(self, config_getter):
        self.config_getter = config_getter
        self.current_req_id = 0
        self.lock = threading.Lock()

    def async_predict(self, pinyin_str: str, on_success_callback):
        cfg = self.config_getter() or {}
        ai_cfg = cfg.get("ai", {})
        if not ai_cfg.get("enabled", False):
            return

        base_url = ai_cfg.get("baseUrl", "https://api.deepseek.com/v1").rstrip("/")
        api_key = ai_cfg.get("apiKey", "")
        model = ai_cfg.get("model", "deepseek-chat")

        # 若无 key 且不是本地 ollama，直接略过
        if not api_key and "127.0.0.1" not in base_url and "localhost" not in base_url:
            return

        with self.lock:
            self.current_req_id += 1
            req_id = self.current_req_id

        def _worker():
            try:
                url = f"{base_url}/chat/completions"
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是一个输入法整句联想引擎。根据拼音输出最可能的一句自然中文（控制在2-10字内），严禁任何解释。"},
                        {"role": "user", "content": f"拼音: {pinyin_str}"}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 30
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}" if api_key else "Bearer ollama"
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=1.8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        text = data["choices"][0]["message"]["content"].strip()
                        text = re.sub(r'[\r\n"\'`]+', '', text)
                        with self.lock:
                            if req_id == self.current_req_id and text:
                                on_success_callback(text)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()


class ModernCandidateWindow:
    """BDS 风格现代化悬浮候选窗"""
    def __init__(self, engine: PinyinEngine, on_commit_callback):
        self.engine = engine
        self.on_commit = on_commit_callback

        self.root = tk.Tk()
        self.root.title("MyIME Candidate")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)

        # BDS 视觉调色板 (像素喵喵爪风格)
        self.bg_color = "#fefbf9"
        self.border_color = "#ffb6c1"
        self.text_color = "#2c2c2c"
        self.first_color = "#d63384"
        self.pinyin_color = "#6c757d"
        self.accent_pill = "#ffe4e9"

        self.root.config(bg=self.border_color)

        self.main_frame = tk.Frame(self.root, bg=self.bg_color, padx=10, pady=8)
        self.main_frame.pack(padx=2, pady=2, fill="both", expand=True)

        # 拼音组合行
        # 拼音组合行与翻页提示
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

        # 初始隐藏
        self.root.withdraw()
        self.current_candidates = []
        self.current_pinyin = ""

    def show_candidates(self, pinyin_display: str, candidates: list[str], page: int = 0, total_pages: int = 1):
        self.current_pinyin = pinyin_display
        self.current_candidates = candidates

        if not candidates:
            self.root.withdraw()
            return

        self.lbl_pinyin.config(text=pinyin_display)
        if total_pages > 1:
            self.lbl_page.config(text=f"({page + 1}/{total_pages}  -/=翻页)")
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

        # 定位到鼠标附近或屏幕中心偏下
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        x = pt.x + 15
        y = pt.y + 25

        # 边界防溢出
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if x + 400 > sw:
            x = sw - 410
        if y + 80 > sh:
            y = pt.y - 80

        self.root.geometry(f"+{x}+{y}")
        self.root.deiconify()

    def apply_skin(self, skin_cfg: dict):
        """动态热更新候选窗配色与视觉参数"""
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
        except Exception as e:
            print(f"[!] 动态换肤更新异常: {e}")

    def hide(self):
        self.root.withdraw()
        self.current_candidates.clear()
        self.current_pinyin = ""


class IMEController:
    """输入法核心状态机与全局按键分发器"""
    def __init__(self):
        self.engine = PinyinEngine(DB_PATH)
        self.sound = SoundHelper()
        self.input_buffer = ""
        self.all_candidates = []
        self.cand_page = 0
        self.pinyin_disp = ""
        self.is_chinese_mode = True

        self.event_queue = queue.Queue()
        self.ui = ModernCandidateWindow(self.engine, self.commit_word)

        # 加载当前皮肤配置与 AI 助手
        self.current_skin_cfg = self._load_current_skin()
        if self.current_skin_cfg:
            self.ui.apply_skin(self.current_skin_cfg)

        self.ai_helper = AICandidateHelper(lambda: self.current_skin_cfg)
        self.reload_counter = 0

        # 托盘/状态指示小浮条 (置于右下角任务栏正上方，保证清晰可见)
        self._setup_status_pill()

        # 启动按键钩子
        self._start_hook()

        # 启动时展示精致就绪通知提示卡并播放按键音效
        self._show_startup_toast()
        self.sound.play()

        # UI 循环监听事件
        self.ui.root.after(10, self._process_queue)

    def _load_current_skin(self) -> dict:
        skin_file = BASE_DIR / "assets" / "current_skin.json"
        if skin_file.exists():
            try:
                with open(skin_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def update_pinyin(self):
        """输入拼音变化时重新查询并渲染第 1 页候选词"""
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
        """根据当前页码切片候选词并刷新候选浮窗"""
        total_cands = len(self.all_candidates)
        total_pages = max(1, (total_cands + 4) // 5)
        self.cand_page = max(0, min(self.cand_page, total_pages - 1))
        start_idx = self.cand_page * 5
        page_cands = self.all_candidates[start_idx : start_idx + 5]
        self.ui.show_candidates(self.pinyin_disp, page_cands, self.cand_page, total_pages)

    def _show_startup_toast(self):
        """启动时在屏幕居中下方展示 3 秒 BDS 专属输入法就绪卡片"""
        try:
            toast = tk.Toplevel(self.ui.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.attributes("-alpha", 0.96)
            toast.config(bg="#ffb6c1")

            frame = tk.Frame(toast, bg="#fefbf9", padx=18, pady=12)
            frame.pack(padx=2, pady=2, fill="both", expand=True)

            title = tk.Label(
                frame, text="🐾 BDS 专属输入法已成功启动！",
                font=("Microsoft YaHei", 12, "bold"), fg="#d63384", bg="#fefbf9"
            )
            title.pack(anchor="w")

            desc = tk.Label(
                frame, text="• 快捷键保护：Ctrl+C/V、Alt+Tab 等系统快捷键完全放行\n• 选词与翻页：按空格选首词，按 - / = 翻页浏览海量词库\n• 退出方式：按 Ctrl+Shift+Q 或右键右下角 [中] 药丸",
                font=("Microsoft YaHei", 9), fg="#495057", bg="#fefbf9", justify="left"
            )
            desc.pack(anchor="w", pady=(4, 0))

            sw = self.ui.root.winfo_screenwidth()
            sh = self.ui.root.winfo_screenheight()
            w, h = 440, 105
            x = (sw - w) // 2
            y = sh - 180
            toast.geometry(f"{w}x{h}+{x}+{y}")

            toast.after(3500, lambda: toast.destroy())
        except Exception:
            pass

    def _setup_status_pill(self):
        """屏幕右下角的中/英状态药丸 (抬高到任务栏上方)"""
        self.pill = tk.Toplevel(self.ui.root)
        self.pill.overrideredirect(True)
        self.pill.attributes("-topmost", True)
        self.pill.attributes("-alpha", 0.90)

        sw = self.ui.root.winfo_screenwidth()
        sh = self.ui.root.winfo_screenheight()
        # Windows 11 任务栏通常高 48px，放在底部偏上 90px 处，确保醒目可见
        self.pill.geometry(f"52x28+{sw - 85}+{sh - 95}")

        self.pill_lbl = tk.Label(
            self.pill, text="中", font=("Segoe UI", 10, "bold"),
            bg="#212529", fg="#ffffff", cursor="hand2"
        )
        self.pill_lbl.pack(fill="both", expand=True)
        self.pill_lbl.bind("<Button-1>", lambda e: self.toggle_mode())
        self.pill_lbl.bind("<Button-3>", lambda e: self.safe_exit())

    def safe_exit(self):
        """安全退出输入法并释放所有资源"""
        try:
            self.ui.root.quit()
        except Exception:
            pass
        os._exit(0)

    def toggle_mode(self):
        self.is_chinese_mode = not self.is_chinese_mode
        self.pill_lbl.config(
            text="中" if self.is_chinese_mode else "英",
            bg="#212529" if self.is_chinese_mode else "#495057"
        )
        if not self.is_chinese_mode:
            self.input_buffer = ""
            self.ui.hide()

    def commit_word(self, word: str):
        self.sound.play()
        # 若为大模型联想长句，剥离前缀机器人图标
        if word.startswith("🤖 "):
            word = word[3:].strip()
        self.engine.learn_word(word, self.input_buffer)
        self.input_buffer = ""
        self.all_candidates = []
        self.cand_page = 0
        self.ui.hide()
        # 延迟 15ms 等待空格键完全被系统拦截并释放，再注入 Unicode 字符，防止按键时序冲突
        def do_send():
            time.sleep(0.015)
            SendInputHelper.send_unicode_string(word)
        threading.Thread(target=do_send, daemon=True).start()

    def handle_key(self, vk: int) -> bool:
        """
        核心分发逻辑：
        返回 True 表示拦截并消费该按键
        返回 False 表示放行给系统正常输入
        """
        # 1. 组合快捷键与修饰键保护：如果当前按下了 Ctrl、Alt 或 Win 键，绝不拦截！放行给系统执行系统快捷键 (如 Ctrl+C, Ctrl+V, Alt+Tab, Win+D 等)
        if (user32.GetAsyncKeyState(0x11) & 0x8000) or \
           (user32.GetAsyncKeyState(0x12) & 0x8000) or \
           (user32.GetAsyncKeyState(0x5B) & 0x8000) or \
           (user32.GetAsyncKeyState(0x5C) & 0x8000):
            # 全局快捷退出热键: Ctrl + Shift + Q
            if vk == ord('Q') and (user32.GetAsyncKeyState(0x10) & 0x8000):
                self.safe_exit()
                return True
            # 如果快捷键触发时有残余拼音，自动取消
            if self.input_buffer:
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
            return False

        # Shift 键切换中英文
        if vk in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT):
            if not self.input_buffer:
                self.toggle_mode()
            return False

        if not self.is_chinese_mode:
            return False

        # 如果输入缓冲区有内容
        if self.input_buffer:
            # 翻页: = (0xBB), . (0xBE), PageDown (0x22) -> 下一页
            if vk in (0xBB, 0xBE, 0x22):
                total_pages = max(1, (len(self.all_candidates) + 4) // 5)
                if self.cand_page + 1 < total_pages:
                    self.cand_page += 1
                    self._render_current_page()
                return True

            # 翻页: - (0xBD), , (0xBC), PageUp (0x21) -> 上一页
            if vk in (0xBD, 0xBC, 0x21):
                if self.cand_page > 0:
                    self.cand_page -= 1
                    self._render_current_page()
                return True

            # 空格或数字1 -> 上屏当前页首选
            if vk == VK_SPACE or vk == ord('1'):
                if self.ui.current_candidates:
                    self.commit_word(self.ui.current_candidates[0])
                    return True

            # 2~5 键选词
            if ord('2') <= vk <= ord('5'):
                idx = vk - ord('1')
                if idx < len(self.ui.current_candidates):
                    self.commit_word(self.ui.current_candidates[idx])
                    return True

            # 回车键 -> 将原始英文字符串直接上屏
            if vk == VK_RETURN:
                raw = self.input_buffer
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
                threading.Thread(target=lambda: SendInputHelper.send_unicode_string(raw), daemon=True).start()
                return True

            # 退格键 -> 删减一个拼音字母
            if vk == VK_BACK:
                self.input_buffer = self.input_buffer[:-1]
                self.update_pinyin()
                return True

            # Delete 键或 Esc 键 -> 取消当前拼音输入
            if vk in (VK_DELETE, VK_ESCAPE):
                self.input_buffer = ""
                self.all_candidates = []
                self.ui.hide()
                return True

        # 输入字母 A~Z (仅大写和小写字母虚拟键码 0x41~0x5A)
        if ord('A') <= vk <= ord('Z'):
            ch = chr(vk).lower()
            self.input_buffer += ch
            self.update_pinyin()
            return True

        # 其他所有按键（包括没有拼音时的 Delete、Backspace、回车、方向键、标点符号等）一律放行给系统！
        return False

    def _process_queue(self):
        while not self.event_queue.empty():
            item = self.event_queue.get_nowait()
            action, data = item
            if action == "UPDATE_UI":
                py_disp, cands = data
                self.ui.show_candidates(py_disp, cands)
            elif action == "HIDE_UI":
                self.ui.hide()
            elif action == "AI_CANDIDATE":
                ai_text = data
                ai_formatted = f"🤖 {ai_text}"
                if self.input_buffer and ai_formatted not in self.all_candidates and ai_text not in self.all_candidates:
                    # 智能插入到第 5 个候选项位置 (或末尾) 作为高智力长句补全
                    insert_pos = min(4, len(self.all_candidates))
                    self.all_candidates.insert(insert_pos, ai_formatted)
                    self._render_current_page()

        # 检查皮肤热重载信号 (约每 300ms 检查一次)
        self.reload_counter = (self.reload_counter + 1) % 30
        if self.reload_counter == 0:
            flag_file = BASE_DIR / "assets" / "skin_reload.flag"
            if flag_file.exists():
                try:
                    flag_file.unlink(missing_ok=True)
                    new_skin = self._load_current_skin()
                    if new_skin:
                        self.current_skin_cfg = new_skin
                        self.ui.apply_skin(new_skin)
                        print(f"[+] 输入法已热重载应用新皮肤「{new_skin.get('name', 'Custom')}」！")
                except Exception:
                    pass

        self.ui.root.after(10, self._process_queue)

    def _start_hook(self):
        def hook_proc(nCode, wParam, lParam):
            try:
                if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    vk = kb.vkCode
                    if self.handle_key(vk):
                        return 1  # 拦截消费该按键，不传递给当前活动应用
            except Exception:
                pass
            try:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)
            except Exception:
                return 0

        self._hook_ref = HOOKPROC(hook_proc)

        def hook_thread():
            h_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_ref, None, 0)
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            user32.UnhookWindowsHookEx(h_hook)

        t = threading.Thread(target=hook_thread, daemon=True)
        t.start()

    def run(self):
        print("\n" + "=" * 55)
        print("🎉 【我的专属输入法 MVP】已成功启动！")
        print("  • 切换中/英：按 Shift 键，或点击屏幕右下角 [中/英] 标识")
        print("  • 打字测试：切到任意记事本、微信、浏览器，输入字母即刻出词")
        print("  • 上屏按键：按 空格键 或 数字 1~5 键直接打出汉字")
        print("  • 退出方法：在控制台按 Ctrl + C 或关闭本窗口")
        print("=" * 55 + "\n")
        self.ui.root.mainloop()


if __name__ == "__main__":
    # 单例互斥体保护：防止重复启动多个进程导致底层键盘钩子冲突
    MUTEX_NAME = "Local\\BDS_IME_SINGLE_INSTANCE_MUTEX"
    _single_instance_mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # 183 = ERROR_ALREADY_EXISTS
        sys.exit(0)

    if not DB_PATH.exists():
        print("[-] 词库未就绪，正在准备...")
    app = IMEController()
    app.run()
