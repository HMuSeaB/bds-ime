"""
Windows 原生 Unicode 模拟上屏模块 (SendInput 引擎)
严格匹配 64 位 Windows 系统下 INPUT 结构体 40 字节对齐标准。
"""

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
    def send_unicode_string(cls, text: str):
        """将选中的文本逐字安全注入到当前活动窗口"""
        for ch in text:
            code = ord(ch)
            inp_down = INPUT(type=cls.INPUT_KEYBOARD)
            inp_down.ki.wVk = 0
            inp_down.ki.wScan = code
            inp_down.ki.dwFlags = cls.KEYEVENTF_UNICODE
            inp_down.ki.time = 0
            inp_down.ki.dwExtraInfo = 0

            inp_up = INPUT(type=cls.INPUT_KEYBOARD)
            inp_up.ki.wVk = 0
            inp_up.ki.wScan = code
            inp_up.ki.dwFlags = cls.KEYEVENTF_UNICODE | cls.KEYEVENTF_KEYUP
            inp_up.ki.time = 0
            inp_up.ki.dwExtraInfo = 0

            inputs = (INPUT * 2)(inp_down, inp_up)
            ret = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
            if ret != 2:
                # 备用回退方式：PostMessage WM_CHAR
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    user32.SendMessageW(hwnd, 0x0102, code, 1)
