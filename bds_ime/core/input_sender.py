"""
Windows 原生 Unicode 模拟上屏模块 (SendInput 引擎)
严格匹配 64 位 Windows 系统下 INPUT 结构体 40 字节对齐标准。
"""

import time
import queue
import threading
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32


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
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    INPUT_KEYBOARD = 1

    @classmethod
    def _create_char_inputs(cls, code: int):
        """
        处理高位 Unicode (如 Emoji 🐾🤖🎉 及 CJK 扩展字)
        当 code > 0xFFFF 时，根据 UTF-16 规范拆解为代理对 (Surrogate Pair)
        """
        if code > 0xFFFF:
            high = 0xD800 + ((code - 0x10000) >> 10)
            low = 0xDC00 + ((code - 0x10000) & 0x3FF)
            codepoints = [high, low]
        else:
            codepoints = [code]

        res = []
        for cp in codepoints:
            inp_down = INPUT(type=cls.INPUT_KEYBOARD)
            inp_down.ki.wVk = 0
            inp_down.ki.wScan = cp
            inp_down.ki.dwFlags = cls.KEYEVENTF_UNICODE
            inp_down.ki.time = 0
            inp_down.ki.dwExtraInfo = 0
            res.append(inp_down)

            inp_up = INPUT(type=cls.INPUT_KEYBOARD)
            inp_up.ki.wVk = 0
            inp_up.ki.wScan = cp
            inp_up.ki.dwFlags = cls.KEYEVENTF_UNICODE | cls.KEYEVENTF_KEYUP
            inp_up.ki.time = 0
            inp_up.ki.dwExtraInfo = 0
            res.append(inp_up)

        return res

    @classmethod
    def send_unicode_string(cls, text: str):
        """将选中的文本逐字安全注入到当前活动窗口，支持 Emoji 与罕见字"""
        if not text:
            return

        for ch in text:
            inputs = cls._create_char_inputs(ord(ch))
            arr = (INPUT * len(inputs))(*inputs)
            ret = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
            if ret != len(inputs):
                # 备用回退方式：PostMessage WM_CHAR
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    for cp in inputs:
                        if not (cp.ki.dwFlags & cls.KEYEVENTF_KEYUP):
                            user32.SendMessageW(hwnd, 0x0102, cp.ki.wScan, 1)


class SendInputQueue:
    """
    单线程 FIFO 严格串行化上屏工作队列
    杜绝并发多线程 sleep 调度导致的字符打乱、倒装与交替穿插 Bug
    """
    _queue = queue.Queue()
    _worker_thread = None
    _lock = threading.Lock()

    @classmethod
    def _ensure_worker(cls):
        with cls._lock:
            if cls._worker_thread is None or not cls._worker_thread.is_alive():
                cls._worker_thread = threading.Thread(target=cls._worker_loop, daemon=True)
                cls._worker_thread.start()

    @classmethod
    def enqueue(cls, text: str, delay_before: float = 0.015):
        """入队等待顺序发送"""
        if not text:
            return
        cls._ensure_worker()
        cls._queue.put((text, delay_before))

    @classmethod
    def _worker_loop(cls):
        while True:
            try:
                text, delay_before = cls._queue.get()
                if delay_before > 0:
                    time.sleep(delay_before)
                SendInputHelper.send_unicode_string(text)
                cls._queue.task_done()
            except Exception:
                pass

