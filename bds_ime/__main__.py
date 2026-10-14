"""
BDS-IME 统一主程序启动入口
支持命令行 `python -m bds_ime` 或编译为单文件 EXE 启动。
"""

import sys
import ctypes

# Windows 高 DPI 适配
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# 终端编码安全保护
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from bds_ime.app import BDSInputMethodApp


def main():
    app = BDSInputMethodApp()
    app.run()


if __name__ == "__main__":
    main()
