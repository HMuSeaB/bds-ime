"""
Windows 原生 MCI 按键无损音效驱动
"""

import ctypes
from pathlib import Path

winmm = ctypes.windll.winmm


class SoundHelper:
    """按键原声音效播放器 (基于 Windows 内部 MCI 多实例音频通道)"""
    def __init__(self, sound_file_path: Path):
        self.sound_file = sound_file_path
        self.alias_idx = 0
        self.available = False
        if self.sound_file.exists():
            safe_p = str(self.sound_file.resolve()).replace("\\", "/")
            try:
                for i in range(4):
                    winmm.mciSendStringW(f'open "{safe_p}" type mpegvideo alias ime_snd_{i}', None, 0, None)
                self.available = True
            except Exception:
                pass

    def play(self):
        if self.available:
            alias = f"ime_snd_{self.alias_idx % 4}"
            self.alias_idx += 1
            winmm.mciSendStringW(f"play {alias} from 0", None, 0, None)
