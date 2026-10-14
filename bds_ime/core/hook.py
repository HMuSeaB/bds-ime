"""
Win32 全局键盘钩子 (WH_KEYBOARD_LL) 与事件拦截调度器
"""

import os
import time
import queue
import ctypes
from ctypes import wintypes
import threading

from bds_ime.core.input_sender import SendInputHelper

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104

VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_SPACE = 0x20
VK_RETURN = 0x0D
VK_BACK = 0x08
VK_ESCAPE = 0x1B
VK_DELETE = 0x2E
VK_OEM_MINUS = 0xBD
VK_OEM_PLUS = 0xBB
VK_OEM_COMMA = 0xBC
VK_OEM_PERIOD = 0xBE
VK_PRIOR = 0x21
VK_NEXT = 0x22


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong)
    ]


HOOKPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]


class KeyboardHookManager:
    """管理全局键盘钩子线程与按键过滤分发"""
    def __init__(self, key_handler_callback):
        self.handler = key_handler_callback
        self.h_hook = None
        self._hook_ref = None

    def start(self):
        def hook_proc(nCode, wParam, lParam):
            try:
                if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if self.handler(kb.vkCode):
                        return 1  # 拦截消费该按键
            except Exception:
                pass
            try:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)
            except Exception:
                return 0

        self._hook_ref = HOOKPROC(hook_proc)

        def worker():
            self.h_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_ref, None, 0)
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if self.h_hook:
                user32.UnhookWindowsHookEx(self.h_hook)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
