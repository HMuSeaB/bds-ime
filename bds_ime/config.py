"""
BDS-IME 全局配置与运行时路径管理
"""

import os
import sys
import json
from pathlib import Path


# 资源基准路径适配 (支持源码运行与 PyInstaller 打包后的 sys._MEIPASS)
if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys._MEIPASS)
    DATA_DIR = Path(os.environ.get("APPDATA", ".")) / "BDS-IME"
else:
    APP_ROOT = Path(__file__).resolve().parent.parent
    DATA_DIR = APP_ROOT / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# 核心资源文件路径
DB_PATH = APP_ROOT / "data" / "pinyin_dict.db"
SOUND_FILE = APP_ROOT / "sound_packs" / "cat" / "x1an.ogg"
CURRENT_SKIN_FILE = DATA_DIR / "current_skin.json"
SKIN_FLAG_FILE = DATA_DIR / "skin_reload.flag"
STUDIO_HTML_DIR = APP_ROOT / "tools" / "skin_studio"

MUTEX_NAME = r"Local\BDS_IME_SINGLE_INSTANCE_MUTEX"


def load_skin_config() -> dict:
    """读取用户自定义皮肤配置"""
    if CURRENT_SKIN_FILE.exists():
        try:
            with open(CURRENT_SKIN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_skin_config(config_data: dict):
    """保存皮肤配置并触发热重载信号"""
    CURRENT_SKIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CURRENT_SKIN_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    with open(SKIN_FLAG_FILE, "w", encoding="utf-8") as f:
        f.write("reload")
