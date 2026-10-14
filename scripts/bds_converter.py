"""
BDS to Windows IME Theme Converter
将百度输入法移动端 .bds 皮肤包转换为 Windows 桌面输入法主题套件。

支持输出：
1. 水杉输入法 (MSIME-Windows) WebView2 候选窗主题 (HTML/CSS)
2. RIME 小狼毫 (Weasel) 调色板方案 (weasel.custom.yaml)
3. 独立交互式打字仿真预览器 (preview.html)
"""

import os
import sys
import re
import json
import base64
import struct
import zipfile
import shutil
from pathlib import Path


class BDSParser:
    def __init__(self, bds_path: str):
        self.bds_path = Path(bds_path)
        if not self.bds_path.exists():
            raise FileNotFoundError(f"找不到皮肤文件: {bds_path}")
        self.zf = zipfile.ZipFile(self.bds_path, 'r')
        self.files = self.zf.namelist()
        self.info = self._parse_info()
        self.styles = self._parse_styles()
        self.cand_cfg = self._parse_cand_cfg()
        self.til_cfg = self._parse_til_cfg()

    def _read_text(self, filename: str) -> str:
        """安全读取压缩包内文本，自适应 UTF-8/GBK 编码与 BOM"""
        raw = self.zf.read(filename)
        for enc in ['utf-8-sig', 'utf-8', 'gb18030', 'gbk']:
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode('latin1', errors='ignore')

    def _parse_info(self) -> dict:
        info = {
            "name": self.bds_path.stem,
            "style": "default",
            "author": "Metasequoia / BDS Community",
        }
        if "Info.txt" in self.files:
            text = self._read_text("Info.txt")
            for line in text.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k.strip().lower()] = v.strip()
        return info

    def _parse_styles(self) -> dict:
        """解析 default.css (实际为 INI 结构) 中的颜色与切图映射"""
        css_file = None
        for candidate in ["res/default.css", "port/res/default.css", "land/res/default.css"]:
            if candidate in self.files:
                css_file = candidate
                break
        if not css_file:
            return {}

        text = self._read_text(css_file)
        styles = {}
        curr_style = None

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^\[STYLE(\d+)\]", line, re.IGNORECASE)
            if m:
                curr_style = m.group(1)
                styles[curr_style] = {}
                continue
            if curr_style and "=" in line:
                k, v = line.split("=", 1)
                styles[curr_style][k.strip().upper()] = v.strip()
        return styles

    def _parse_cand_cfg(self) -> dict:
        """解析候选栏配置 (port/cand1.cnd)"""
        cnd_file = None
        for candidate in ["port/cand1.cnd", "land/cand1.cnd", "cand1.cnd"]:
            if candidate in self.files:
                cnd_file = candidate
                break
        if not cnd_file:
            return {}

        text = self._read_text(cnd_file)
        cfg = {"cand": {}, "switch": {}}
        curr_sec = "cand"

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                curr_sec = line[1:-1].strip().lower()
                if curr_sec not in cfg:
                    cfg[curr_sec] = {}
                continue
            if "=" in line and curr_sec in cfg:
                k, v = line.split("=", 1)
                cfg[curr_sec][k.strip().upper()] = v.strip()
        return cfg

    def _parse_til_cfg(self) -> dict:
        """解析 9-patch 切片文件 (cand.til / bj.til)"""
        til_file = None
        for candidate in ["port/res/cand.til", "res/cand.til", "land/res/cand.til", "port/res/bj.til", "res/bj.til"]:
            if candidate in self.files:
                til_file = candidate
                break
        if not til_file:
            return {}

        text = self._read_text(til_file)
        tiles = {}
        curr_img = None

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^\[IMG(\d+)\]", line, re.IGNORECASE)
            if m:
                curr_img = int(m.group(1))
                tiles[curr_img] = {}
                continue
            if curr_img and "=" in line:
                k, v = line.split("=", 1)
                tiles[curr_img][k.strip().upper()] = v.strip()
        return tiles

    @staticmethod
    def argb_to_css(hex_str: str, default: str = "#333333") -> str:
        """转换 AARRGGBB 或 RRGGBB 为 CSS 格式 (#RRGGBB 或 rgba)"""
        if not hex_str:
            return default
        hex_str = hex_str.strip().lstrip("#")
        try:
            if len(hex_str) == 8:
                a = int(hex_str[0:2], 16) / 255.0
                r = int(hex_str[2:4], 16)
                g = int(hex_str[4:6], 16)
                b = int(hex_str[6:8], 16)
                if a >= 0.99:
                    return f"#{hex_str[2:8].lower()}"
                return f"rgba({r}, {g}, {b}, {a:.2f})"
            elif len(hex_str) == 6:
                return f"#{hex_str.lower()}"
        except Exception:
            pass
        return default

    def get_color(self, style_id: str, field: str = "NM_COLOR", default: str = "#222222") -> str:
        s = self.styles.get(str(style_id), {})
        val = s.get(field.upper())
        return self.argb_to_css(val, default)

    def extract_cand_image(self) -> tuple[bytes | None, str]:
        """提取候选框切图 (cand.png 或备用图片)"""
        for candidate in ["port/res/cand.png", "res/cand.png", "land/res/cand.png", "res/bj.png"]:
            if candidate in self.files:
                return self.zf.read(candidate), candidate
        return None, ""

    def extract_mascot_image(self) -> tuple[bytes | None, str]:
        """提取装饰图/立绘图 (demo.png / back.png)"""
        for candidate in ["demo.png", "res/back.png"]:
            if candidate in self.files:
                return self.zf.read(candidate), candidate
        return None, ""

    def calculate_9patch_slices(self) -> dict:
        """
        计算 9-patch 的 CSS border-image 切割宽度。
        SOURCE_RECT=x,y,w,h; INNER_RECT=ix,iy,iw,ih
        """
        img1 = self.til_cfg.get(1, {})
        source = img1.get("SOURCE_RECT")
        inner = img1.get("INNER_RECT")

        if source and inner:
            try:
                sx, sy, sw, sh = map(int, source.split(","))
                ix, iy, iw, ih = map(int, inner.split(","))
                top = iy - sy
                left = ix - sx
                bottom = sh - (top + ih)
                right = sw - (left + iw)
                return {
                    "top": max(1, top),
                    "right": max(1, right),
                    "bottom": max(1, bottom),
                    "left": max(1, left),
                    "w": sw,
                    "h": sh,
                    "has_9patch": True
                }
            except Exception:
                pass
        
        # 默认回退 12px 切片
        return {"top": 12, "right": 12, "bottom": 12, "left": 12, "w": 100, "h": 100, "has_9patch": False}


class ThemeGenerator:
    """负责将 BDS 属性渲染成水杉输入法主题、RIME 配置与网页预览"""
    def __init__(self, parser: BDSParser):
        self.parser = parser
        self.info = parser.info
        self.slices = parser.calculate_9patch_slices()
        cand_sec = parser.cand_cfg.get("cand", {})

        # 获取前景色、首选高亮色与常规文字颜色
        fore_style = cand_sec.get("FORE_STYLE", "160")
        first_fore = cand_sec.get("FIRST_FORE", "210")
        
        # 智能推断背景主基调（深色或浅色）
        self.text_color = parser.get_color(fore_style, "NM_COLOR", "#2b2b2b")
        self.first_color = parser.get_color(first_fore, "NM_COLOR", "#000000")
        
        # 确定高亮色对比与背景透明度
        is_dark = "黑" in self.info.get("name", "") or "dark" in self.info.get("name", "").lower()
        if is_dark and self.text_color == "#2b2b2b":
            self.text_color = "#e0e0e0"
            self.first_color = "#ffffff"
            self.fallback_bg = "#202020"
        else:
            self.fallback_bg = "#fbfaf8" if not is_dark else "#222222"

        self.cand_img_bytes, self.cand_img_name = parser.extract_cand_image()
        self.mascot_bytes, self.mascot_name = parser.extract_mascot_image()

    def generate_msime_theme_css(self, img_relative_path: str = "cand.png") -> str:
        """生成适配水杉输入法 WebView2 候选窗的 CSS 皮肤代码"""
        slice_str = f"{self.slices['top']} {self.slices['right']} {self.slices['bottom']} {self.slices['left']}"
        # 桌面端自适应边框宽度 (避免移动端高分辨率切片直接导致桌面端边框过粗)
        bw_top = min(self.slices['top'], 16)
        bw_right = min(self.slices['right'], 16)
        bw_bottom = min(self.slices['bottom'], 16)
        bw_left = min(self.slices['left'], 16)
        border_width_str = f"{bw_top}px {bw_right}px {bw_bottom}px {bw_left}px"

        border_img_rule = ""
        if self.cand_img_bytes:
            border_img_rule = f"""
      border-style: solid;
      border-width: {border_width_str};
      border-image-source: url('{img_relative_path}');
      border-image-slice: {slice_str} fill;
      border-image-repeat: stretch;
      background: transparent;
"""
        else:
            border_img_rule = f"""
      background-color: {self.fallback_bg};
      border: 1px solid rgba(128, 128, 128, 0.25);
      border-radius: 8px;
"""

        return f"""/*
 * 水杉输入法 (MSIME-Windows) 皮肤主题: {self.info.get('name', 'BDS Theme')}
 * 自动转换自百度输入法 BDS 皮肤包
 */

:root {{
  --msime-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  --msime-text-color: {self.text_color};
  --msime-first-color: {self.first_color};
  --msime-pinyin-color: rgba(128, 128, 128, 0.85);
}}

body {{
  font-family: var(--msime-font-family);
  font-size: 17px;
  height: 100vh;
  margin: 0;
  overflow: hidden;
  background: transparent;
  user-select: none;
}}

/* 候选窗主容器 (九宫格拉伸还原 BDS 切图) */
.container {{
  margin: 0;
  padding: 6px 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
  display: flex;
  flex-direction: column;
  width: fit-content;
  {border_img_rule}
}}

/* 编码/拼音行 */
.pinyin-row {{
  margin-bottom: 4px;
  padding: 0 4px;
}}

.pinyin-row .text {{
  font-size: 0.9em;
  color: var(--msime-pinyin-color);
  letter-spacing: 0.5px;
}}

/* 候选项列表容器 */
.candidates-row {{
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  padding: 2px 4px;
}}

.row-wrapper {{
  position: relative;
}}

/* 候选词单元 */
.cand {{
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.15s ease;
  cursor: pointer;
}}

.cand .text {{
  color: var(--msime-text-color);
  font-weight: 400;
}}

/* 鼠标悬停 */
.cand:hover {{
  background-color: rgba(128, 128, 128, 0.14);
}}

/* 首选项高亮 */
.first {{
  background-color: rgba(128, 128, 128, 0.22);
}}

.first .text {{
  color: var(--msime-first-color);
  font-weight: 600;
}}

/* 首选高亮指示条 */
.first::before {{
  content: "";
  position: absolute;
  left: 2px;
  top: 50%;
  transform: translateY(-50%);
  height: 0.75em;
  width: 3px;
  background: var(--msime-first-color);
  border-radius: 2px;
}}
"""

    def generate_msime_theme_html(self, css_filename: str = "theme.css") -> str:
        """生成与水杉输入法 WebView2 完全兼容的候选窗 HTML 文件"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' https://msime-contracts; style-src 'unsafe-inline' https://candidate-skins https://appassets; img-src data: https://appassets https://candidate-skins file:; font-src data: https://appassets https://candidate-skins">
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>水杉输入法候选窗 - {self.info.get('name', 'BDS Theme')}</title>
  <link rel="stylesheet" href="{css_filename}">
</head>
<body>
  <!-- 拼音/编码行 -->
  <div class="container" id="pinyin-container">
    <div class="pinyin-row">
      <div class="row pinyin">
        <div class="text">ni'hao</div>
      </div>
    </div>
  </div>

  <!-- 候选词行 -->
  <div class="container" id="container">
    <div class="candidates-row">
      <div class="row-wrapper">
        <div class="row cand first">
          <div class="text">1. 你好</div>
        </div>
      </div>
      <div class="row-wrapper">
        <div class="row cand">
          <div class="text">2. 拟好</div>
        </div>
      </div>
      <div class="row-wrapper">
        <div class="row cand">
          <div class="text">3. 您好</div>
        </div>
      </div>
      <div class="row-wrapper">
        <div class="row cand">
          <div class="text">4. 泥壕</div>
        </div>
      </div>
      <div class="row-wrapper">
        <div class="row cand">
          <div class="text">5. 你浩</div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""

    def generate_msime_skin_toml(self, skin_id: str, has_bg: bool = True, has_deco: bool = False) -> str:
        """
        生成水杉输入法 (Metasequoia IME) 官方标准 skin.toml 皮肤配置
        规范: https://github.com/metasequoiaime/msime-windows
        """
        corner_radius = max(6, min(14, self.slices.get("top", 8)))

        bg_block = ""
        if has_bg:
            bg_block = """
[candidate_window.background]
image = "assets/background.png"
fit = "stretch"
opacity = 0.95
"""

        deco_block = ""
        if has_deco:
            deco_block = """
[candidate_window.decoration]
image = "assets/character.png"
width_dip = 60
align = "right"
"""

        name = self.info.get("name", skin_id)
        author = self.info.get("author", "BDS Community")

        return f"""# 水杉输入法 (Metasequoia IME) 皮肤配置规范
# 自动生成自百度输入法官方皮肤包: {name}
schema_version = 1
id = "{skin_id}"
name = "{name}"
version = "1.0.0"
author = "{author}"
base = "fluent"

[supports]
layouts = ["horizontal", "vertical"]
themes = ["light", "dark"]

[candidate_window]
min_width_dip = 160
corner_radius_dip = {corner_radius}
{bg_block}{deco_block}
[candidate.light]
surface = "{self.fallback_bg}"
text = "{self.text_color}"
selected = "#E8F0FE"
accent = "{self.first_color}"
number = "#888888"
border = "#E2E8F0"

[candidate.dark]
surface = "#222222"
text = "{self.text_color if self.fallback_bg == '#222222' else '#EDEDED'}"
selected = "#333333"
accent = "{self.first_color if self.fallback_bg == '#222222' else '#60A5FA'}"
number = "#888888"
border = "#383838"
"""

    def generate_rime_weasel_yaml(self) -> str:
        """生成 RIME 小狼毫 weasel.custom.yaml 风格的配色配置"""
        def to_bgr(css_hex):
            h = css_hex.lstrip("#")
            if len(h) == 6:
                return f"0x{h[4:6]}{h[2:4]}{h[0:2]}"
            return "0x000000"

        scheme_id = "bds_" + re.sub(r"[^\w]", "_", self.info.get("name", "theme")).lower()
        return f"""# RIME 小狼毫配色方案 - {self.info.get('name')}
# 添加到 %APPDATA%\\Rime\\weasel.custom.yaml
patch:
  "style/color_scheme": "{scheme_id}"
  "preset_color_schemes/{scheme_id}":
    name: "{self.info.get('name')}"
    author: "BDS Converter"
    horizontal: true
    inline_preedit: false
    candidate_format: "%c. %@"
    corner_radius: 8
    border_height: 4
    border_width: 8
    back_color: {to_bgr(self.fallback_bg)}
    border_color: 0x888888
    text_color: {to_bgr(self.text_color)}
    hilited_text_color: {to_bgr(self.first_color)}
    hilited_back_color: 0x22000000
    candidate_text_color: {to_bgr(self.text_color)}
    hilited_candidate_text_color: {to_bgr(self.first_color)}
    hilited_candidate_back_color: 0x22888888
"""

    def generate_interactive_preview_html(self) -> str:
        """生成完全独立的交互式打字仿真预览 HTML (单文件内联 Base64)"""
        cand_b64 = ""
        if self.cand_img_bytes:
            cand_b64 = f"data:image/png;base64,{base64.b64encode(self.cand_img_bytes).decode('ascii')}"

        demo_b64 = ""
        if self.mascot_bytes:
            demo_b64 = f"data:image/png;base64,{base64.b64encode(self.mascot_bytes).decode('ascii')}"

        slice_css = f"{self.slices['top']} {self.slices['right']} {self.slices['bottom']} {self.slices['left']}"
        bw_top = min(self.slices['top'], 16)
        bw_right = min(self.slices['right'], 16)
        bw_bottom = min(self.slices['bottom'], 16)
        bw_left = min(self.slices['left'], 16)
        border_width_css = f"{bw_top}px {bw_right}px {bw_bottom}px {bw_left}px"

        border_style_css = ""
        if cand_b64:
            border_style_css = f"""
      border-style: solid;
      border-width: {border_width_css};
      border-image-source: url('{cand_b64}');
      border-image-slice: {slice_css} fill;
      border-image-repeat: stretch;
      background: transparent;
"""
        else:
            border_style_css = f"""
      background-color: {self.fallback_bg};
      border: 1px solid rgba(128,128,128,0.25);
      border-radius: 8px;
"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Windows 输入法 BDS 皮肤实时打字交互 - {self.info.get('name')}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: #0f141c;
      color: #e5e9f0;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }}

    header {{
      padding: 16px 24px;
      background: #18202c;
      border-bottom: 1px solid #2d3748;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    header h1 {{
      font-size: 1.15rem;
      margin: 0;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .tag {{
      font-size: 0.75rem;
      background: #3182ce;
      color: #fff;
      padding: 2px 8px;
      border-radius: 4px;
    }}

    .workspace {{
      flex: 1;
      display: flex;
      padding: 24px;
      gap: 24px;
    }}

    /* 模拟打字主编辑区 */
    .editor-card {{
      flex: 3;
      background: #1a2230;
      border: 1px solid #2d3748;
      border-radius: 12px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      position: relative;
    }}

    .editor-title {{
      font-size: 0.9rem;
      color: #a0aec0;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
    }}

    .typing-box {{
      flex: 1;
      background: #111822;
      border: 1px solid #4a5568;
      border-radius: 8px;
      padding: 16px;
      font-size: 1.25rem;
      color: #edf2f7;
      outline: none;
      position: relative;
      cursor: text;
      overflow-y: auto;
      line-height: 1.8;
    }}

    .typing-box:focus {{
      border-color: #63b3ed;
      box-shadow: 0 0 0 1px #63b3ed;
    }}

    .cursor {{
      display: inline-block;
      width: 2px;
      height: 1.25rem;
      background: #63b3ed;
      vertical-align: middle;
      animation: blink 1s infinite;
    }}

    @keyframes blink {{
      0%, 49% {{ opacity: 1; }}
      50%, 100% {{ opacity: 0; }}
    }}

    /* 悬浮候选窗模拟 (关键还原层) */
    .ime-candidate-window {{
      position: absolute;
      top: 140px;
      left: 60px;
      z-index: 999;
      display: flex;
      flex-direction: column;
      width: fit-content;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
      user-select: none;
      transition: all 0.08s ease;
      {border_style_css}
    }}

    .pinyin-header {{
      padding: 4px 8px;
      font-size: 0.85rem;
      color: rgba(128, 128, 128, 0.9);
      letter-spacing: 0.5px;
      border-bottom: 1px dashed rgba(128, 128, 128, 0.2);
      margin-bottom: 4px;
    }}

    .cand-row {{
      display: flex;
      flex-direction: row;
      gap: 8px;
      padding: 4px 6px;
      align-items: center;
    }}

    .cand-item {{
      display: inline-flex;
      align-items: center;
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 1.05rem;
      color: {self.text_color};
      transition: all 0.12s ease;
      position: relative;
      cursor: pointer;
    }}

    .cand-item:hover {{
      background: rgba(128, 128, 128, 0.15);
    }}

    .cand-item.active {{
      background: rgba(128, 128, 128, 0.24);
      color: {self.first_color};
      font-weight: 600;
    }}

    .cand-item.active::before {{
      content: "";
      position: absolute;
      left: 2px;
      top: 50%;
      transform: translateY(-50%);
      height: 0.7em;
      width: 3px;
      background: {self.first_color};
      border-radius: 2px;
    }}

    /* 侧边信息栏 */
    .sidebar {{
      flex: 1.4;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}

    .info-card {{
      background: #1a2230;
      border: 1px solid #2d3748;
      border-radius: 12px;
      padding: 16px;
      font-size: 0.85rem;
    }}

    .info-card h3 {{
      margin-top: 0;
      font-size: 0.95rem;
      color: #90cdf4;
      border-bottom: 1px solid #2d3748;
      padding-bottom: 8px;
    }}

    .info-item {{
      display: flex;
      justify-content: space-between;
      margin: 8px 0;
      color: #cbd5e0;
    }}

    .info-val {{
      font-family: monospace;
      color: #e2e8f0;
    }}

    .color-swatch {{
      display: inline-block;
      width: 14px;
      height: 14px;
      border-radius: 3px;
      border: 1px solid rgba(255,255,255,0.2);
      vertical-align: middle;
      margin-right: 4px;
    }}

    .mascot-box {{
      text-align: center;
      margin-top: 10px;
    }}

    .mascot-img {{
      max-width: 100%;
      max-height: 180px;
      border-radius: 8px;
      border: 1px solid #2d3748;
    }}

    .instructions {{
      margin-top: 10px;
      line-height: 1.6;
      color: #a0aec0;
      font-size: 0.82rem;
    }}

    .key-badge {{
      background: #2d3748;
      color: #edf2f7;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.75rem;
      border: 1px solid #4a5568;
    }}
  </style>
</head>
<body>
  <header>
    <h1>
      <span>🐾 BDS 皮肤 PC 输入法交互预览器</span>
      <span class="tag">{self.info.get('name')}</span>
    </h1>
    <div style="font-size: 0.85rem; color: #a0aec0;">
      支持实时键盘击键 / 空格上屏 / 1~5 键选词
    </div>
  </header>

  <div class="workspace">
    <!-- 编辑区 -->
    <div class="editor-card">
      <div class="editor-title">
        <span>输入测试区域（点击下方文本框开始打字测试）</span>
        <span style="font-size: 0.8rem; color: #718096;">提示：随意按下英文字母体验拼音候选浮窗</span>
      </div>

      <div class="typing-box" id="typingArea" tabindex="0">
        <span id="committedText">点击这里直接打字：水杉输入法与BDS皮肤适配非常丝滑！</span>
        <span class="cursor"></span>
      </div>

      <!-- 悬浮输入法候选窗 -->
      <div class="ime-candidate-window" id="imeWindow">
        <div class="pinyin-header" id="imePinyin">shui'shan'shu'ru'fa</div>
        <div class="cand-row" id="imeCandList">
          <div class="cand-item active">1. 水杉输入法</div>
          <div class="cand-item">2. 水杉</div>
          <div class="cand-item">3. 随身输入法</div>
          <div class="cand-item">4. 水神</div>
          <div class="cand-item">5. 瑞士法郎</div>
        </div>
      </div>
    </div>

    <!-- 侧栏参数详情 -->
    <div class="sidebar">
      <div class="info-card">
        <h3>🎨 提取的 BDS 视觉参数</h3>
        <div class="info-item">
          <span>皮肤名称</span>
          <span class="info-val">{self.info.get('name')}</span>
        </div>
        <div class="info-item">
          <span>文字颜色</span>
          <span class="info-val">
            <span class="color-swatch" style="background:{self.text_color};"></span>{self.text_color}
          </span>
        </div>
        <div class="info-item">
          <span>首选高亮颜色</span>
          <span class="info-val">
            <span class="color-swatch" style="background:{self.first_color};"></span>{self.first_color}
          </span>
        </div>
        <div class="info-item">
          <span>9-Patch 切片</span>
          <span class="info-val">{self.slices['top']}px / {self.slices['right']}px / {self.slices['bottom']}px / {self.slices['left']}px</span>
        </div>
        <div class="info-item">
          <span>切片模式</span>
          <span class="info-val">{'自适应九宫格 (9-Patch)' if self.slices.get('has_9patch') else '平铺背景'}</span>
        </div>
      </div>

      <div class="info-card">
        <h3>⌨️ 交互快捷指令</h3>
        <div class="instructions">
          • 输入 <span class="key-badge">a-z</span>：触发拼音候选浮窗<br>
          • 按下 <span class="key-badge">Space</span>：首选词上屏<br>
          • 按下 <span class="key-badge">1~5</span>：指定候选词上屏<br>
          • 按下 <span class="key-badge">Backspace</span>：退格清除拼音<br>
          • 按下 <span class="key-badge">Esc</span>：关闭当前候选窗
        </div>
      </div>

      {'<div class="info-card"><div class="mascot-box"><img src="' + demo_b64 + '" class="mascot-img" alt="Demo Image"><div style="margin-top:6px; color:#718096; font-size:0.75rem;">提取自原 BDS 皮肤演示壁纸</div></div></div>' if demo_b64 else ''}
    </div>
  </div>

  <script>
    // 简易拼音词典模拟库
    const pinyinDict = {{
      "shui": ["水", "税", "谁", "睡", "说"],
      "shan": ["山", "杉", "闪", "衫", "扇"],
      "shu": ["书", "数", "树", "输", "熟"],
      "ru": ["入", "如", "儒", "汝", "辱"],
      "fa": ["法", "发", "伐", "乏", "阀"],
      "ni": ["你", "泥", "拟", "逆", "妮"],
      "hao": ["好", "号", "浩", "耗", "毫"],
      "wo": ["我", "握", "卧", "窝", "涡"],
      "de": ["的", "得", "地", "德", "登"],
      "pi": ["皮", "批", "披", "辟", "脾"],
      "fu": ["肤", "福", "服", "复", "府"],
      "miao": ["喵", "秒", "妙", "描", "苗"],
      "zhua": ["爪", "抓", "挝"],
      "note": ["Note", "便签", "笔记", "记录"]
    }};

    const mockWordMap = {{
      "shuishan": ["水杉", "水仙", "税率"],
      "shuishanshuru": ["水杉输入", "随身输入"],
      "shuishanshurufa": ["水杉输入法", "水杉", "随身输入法", "水神", "瑞士法郎"],
      "nihao": ["你好", "拟好", "您好", "泥壕", "你浩"],
      "miaomiao": ["喵喵", "苗苗", "瞄瞄"],
      "miaomiaozhua": ["喵喵爪", "喵喵", "妙妙抓"],
      "xiangsu": ["像素", "向宿", "香酥"],
      "heise": ["黑色", "和色", "黑涩"]
    }};

    let currentInput = "";
    const typingArea = document.getElementById("typingArea");
    const committedText = document.getElementById("committedText");
    const imeWindow = document.getElementById("imeWindow");
    const imePinyin = document.getElementById("imePinyin");
    const imeCandList = document.getElementById("imeCandList");

    function updateIme() {{
      if (!currentInput) {{
        imeWindow.style.display = "none";
        return;
      }}
      imeWindow.style.display = "flex";
      imePinyin.textContent = currentInput;

      // 匹配候选词
      let candidates = mockWordMap[currentInput.toLowerCase()];
      if (!candidates) {{
        // 分词提取首个拼音
        const firstSyl = currentInput.slice(0, 4);
        candidates = pinyinDict[firstSyl] || [currentInput, currentInput.toUpperCase(), "输入测试", "效果预览", "候选五"];
      }}

      imeCandList.innerHTML = "";
      candidates.slice(0, 5).forEach((cand, idx) => {{
        const div = document.createElement("div");
        div.className = "cand-item" + (idx === 0 ? " active" : "");
        div.textContent = `${{idx + 1}}. ${{cand}}`;
        div.onclick = () => commitWord(cand);
        imeCandList.appendChild(div);
      }});
    }}

    function commitWord(word) {{
      committedText.textContent += word;
      currentInput = "";
      updateIme();
    }}

    window.addEventListener("keydown", (e) => {{
      // 仅在获得焦点或全局捕获
      if (e.key === "Backspace") {{
        if (currentInput.length > 0) {{
          e.preventDefault();
          currentInput = currentInput.slice(0, -1);
          updateIme();
        }} else if (committedText.textContent.length > 0) {{
          e.preventDefault();
          committedText.textContent = committedText.textContent.slice(0, -1);
        }}
        return;
      }}

      if (e.key === "Escape") {{
        currentInput = "";
        updateIme();
        return;
      }}

      if (currentInput.length > 0) {{
        if (e.key === " " || e.key === "Enter") {{
          e.preventDefault();
          const firstCand = imeCandList.querySelector(".cand-item.active");
          if (firstCand) {{
            const text = firstCand.textContent.replace(/^\\d+\\.\\s*/, "");
            commitWord(text);
          }}
          return;
        }}

        if (/^[1-5]$/.test(e.key)) {{
          e.preventDefault();
          const idx = parseInt(e.key) - 1;
          const items = imeCandList.querySelectorAll(".cand-item");
          if (items[idx]) {{
            const text = items[idx].textContent.replace(/^\\d+\\.\\s*/, "");
            commitWord(text);
          }}
          return;
        }}
      }}

      if (/^[a-zA-Z]$/.test(e.key) && !e.ctrlKey && !e.altKey && !e.metaKey) {{
        e.preventDefault();
        currentInput += e.key.toLowerCase();
        updateIme();
      }}
    }});

    // 初始化展示
    updateIme();
  </script>
</body>
</html>
"""


def generate_safe_skin_id(theme_name: str) -> str:
    """生成符合水杉输入法规范的皮肤 ID 与文件夹标识 (英文/数字/下划线)"""
    clean = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5]', '_', theme_name)
    clean = re.sub(r'_+', '_', clean).strip('_')
    if not clean:
        clean = "theme"
    return f"bds_{clean.lower()}"


def process_bds(bds_path: str, output_base_dir: str):
    """处理单个 BDS 文件并生成整套皮肤资源与水杉输入法官方主题包"""
    parser = BDSParser(bds_path)
    theme_name = parser.info.get("name", Path(bds_path).stem)
    # 安全文件夹名称
    safe_folder = re.sub(r'[\\/*?:"<>| ]', '_', theme_name)
    out_dir = Path(output_base_dir) / safe_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    gen = ThemeGenerator(parser)

    # 1. 导出候选框切图
    cand_bytes, _ = parser.extract_cand_image()
    if cand_bytes:
        with open(out_dir / "cand.png", "wb") as f:
            f.write(cand_bytes)

    # 2. 导出立绘壁纸
    demo_bytes, _ = parser.extract_mascot_image()
    if demo_bytes:
        with open(out_dir / "preview_art.png", "wb") as f:
            f.write(demo_bytes)

    # 3. 生成水杉输入法 (MSIME) 主题文件 (WebView2 HTML/CSS)
    msime_css = gen.generate_msime_theme_css("cand.png")
    with open(out_dir / "theme.css", "w", encoding="utf-8") as f:
        f.write(msime_css)

    msime_html = gen.generate_msime_theme_html("theme.css")
    with open(out_dir / "candidate_window.html", "w", encoding="utf-8") as f:
        f.write(msime_html)

    # 4. 生成 RIME 小狼毫配色方案
    rime_yaml = gen.generate_rime_weasel_yaml()
    with open(out_dir / "weasel.custom.yaml", "w", encoding="utf-8") as f:
        f.write(rime_yaml)

    # 5. 生成单文件独立交互预览页面
    preview_html = gen.generate_interactive_preview_html()
    with open(out_dir / "interactive_preview.html", "w", encoding="utf-8") as f:
        f.write(preview_html)

    # 6. 生成水杉输入法 (Metasequoia IME) 官方规范外部皮肤包 (skin.toml + assets/)
    skin_id = generate_safe_skin_id(theme_name)
    msime_pkg_dir = Path("msime_skins") / skin_id
    msime_assets_dir = msime_pkg_dir / "assets"
    msime_assets_dir.mkdir(parents=True, exist_ok=True)

    has_bg = False
    if cand_bytes:
        with open(msime_assets_dir / "background.png", "wb") as f:
            f.write(cand_bytes)
        has_bg = True

    has_deco = False
    if demo_bytes:
        with open(msime_assets_dir / "character.png", "wb") as f:
            f.write(demo_bytes)
        has_deco = True

    msime_skin_toml = gen.generate_msime_skin_toml(skin_id, has_bg=has_bg, has_deco=has_deco)
    with open(msime_pkg_dir / "skin.toml", "w", encoding="utf-8") as f:
        f.write(msime_skin_toml)

    # 7. 自动部署到水杉输入法用户目录 (%LOCALAPPDATA%\metasequoiaime\skins)
    local_app_data = os.environ.get("LOCALAPPDATA")
    installed_path = None
    if local_app_data:
        target_msime_skins = Path(local_app_data) / "metasequoiaime" / "skins" / skin_id
        try:
            target_msime_skins.mkdir(parents=True, exist_ok=True)
            shutil.copytree(msime_pkg_dir, target_msime_skins, dirs_exist_ok=True)
            installed_path = target_msime_skins
        except Exception as e:
            print(f"    [!] 自动同步到水杉皮肤目录失败: {e}")

    print(f"[+] 成功转换: {theme_name}")
    print(f"    - 目标目录: {out_dir}")
    print(f"    - 水杉输入法 HTML/CSS: {out_dir / 'candidate_window.html'}")
    print(f"    - 小狼毫 YAML 配色: {out_dir / 'weasel.custom.yaml'}")
    print(f"    - 交互式打字预览: {out_dir / 'interactive_preview.html'}")
    print(f"    - 水杉官方皮肤包 (skin.toml): {msime_pkg_dir}")
    if installed_path:
        print(f"    - [已就绪] 自动安装到水杉目录: {installed_path}")

    return {
        "name": theme_name,
        "folder": safe_folder,
        "skin_id": skin_id,
        "preview_url": f"{safe_folder}/interactive_preview.html",
        "html_url": f"{safe_folder}/candidate_window.html",
        "css_url": f"{safe_folder}/theme.css",
        "yaml_url": f"{safe_folder}/weasel.custom.yaml",
        "msime_dir": str(msime_pkg_dir),
        "msime_installed": str(installed_path) if installed_path else None,
        "has_art": bool(demo_bytes),
        "text_color": gen.text_color,
        "first_color": gen.first_color,
    }



def generate_index_dashboard(themes: list, output_base_dir: str):
    """生成包含所有转换皮肤的统一控制台主页"""
    cards_html = ""
    for t in themes:
        msime_btn = ""
        if t.get("msime_dir"):
            msime_btn = f"""<a href="../{t['msime_dir']}" target="_blank" class="btn btn-secondary">📦 查看水杉皮肤包 ({t['skin_id']})</a>"""

        cards_html += f"""
      <div class="theme-card">
        <div class="card-header">
          <h3>{t['name']}</h3>
          <span class="badge">已转换</span>
        </div>
        <div class="card-body">
          <div class="meta-row">
            <span>文字色: <span class="color-dot" style="background:{t['text_color']};"></span>{t['text_color']}</span>
            <span>首选色: <span class="color-dot" style="background:{t['first_color']};"></span>{t['first_color']}</span>
          </div>
          <div class="card-actions">
            <a href="{t['preview_url']}" target="_blank" class="btn btn-primary">🚀 启动交互打字预览</a>
            {msime_btn}
            <a href="{t['html_url']}" target="_blank" class="btn btn-secondary">📄 查看 Webview HTML</a>
            <a href="{t['yaml_url']}" target="_blank" class="btn btn-secondary">⚙️ 小狼毫配置</a>
          </div>
        </div>
      </div>
"""

    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BDS 皮肤接入 Windows 输入法 - 主题套件控制台</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: #0d1117;
      color: #c9d1d9;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: #161b22;
      border-bottom: 1px solid #30363d;
      padding: 32px 48px;
    }}
    header h1 {{
      margin: 0 0 10px 0;
      color: #58a6ff;
      font-size: 1.8rem;
    }}
    header p {{
      margin: 0;
      color: #8b949e;
      font-size: 1rem;
    }}
    .container {{
      max-width: 1100px;
      margin: 32px auto;
      padding: 0 24px;
      width: 100%;
      flex: 1;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 24px;
      margin-bottom: 40px;
    }}
    .theme-card {{
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: transform 0.2s, border-color 0.2s;
    }}
    .theme-card:hover {{
      transform: translateY(-4px);
      border-color: #58a6ff;
      box-shadow: 0 12px 24px rgba(0, 0, 0, 0.3);
    }}
    .card-header {{
      padding: 16px 20px;
      background: #21262d;
      border-bottom: 1px solid #30363d;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .card-header h3 {{
      margin: 0;
      font-size: 1.15rem;
      color: #f0f6fc;
    }}
    .badge {{
      font-size: 0.75rem;
      background: #238636;
      color: #fff;
      padding: 2px 8px;
      border-radius: 12px;
    }}
    .card-body {{
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      flex: 1;
    }}
    .meta-row {{
      display: flex;
      gap: 16px;
      font-size: 0.85rem;
      color: #8b949e;
    }}
    .color-dot {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      vertical-align: middle;
      margin-right: 4px;
      border: 1px solid rgba(255,255,255,0.2);
    }}
    .card-actions {{
      margin-top: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .btn {{
      display: block;
      text-align: center;
      padding: 10px 14px;
      border-radius: 6px;
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 500;
      transition: background 0.15s;
    }}
    .btn-primary {{
      background: #238636;
      color: #fff;
    }}
    .btn-primary:hover {{
      background: #2ea043;
    }}
    .btn-secondary {{
      background: #21262d;
      color: #58a6ff;
      border: 1px solid #30363d;
    }}
    .btn-secondary:hover {{
      background: #30363d;
    }}
    .guide-section {{
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 12px;
      padding: 28px;
      margin-top: 24px;
      line-height: 1.7;
    }}
    .guide-section h2 {{
      color: #f0f6fc;
      margin-top: 0;
      font-size: 1.3rem;
      border-bottom: 1px solid #30363d;
      padding-bottom: 12px;
    }}
    code {{
      background: #21262d;
      padding: 2px 6px;
      border-radius: 4px;
      color: #f0883e;
      font-size: 0.9em;
    }}
    ol {{
      padding-left: 20px;
    }}
    li {{
      margin-bottom: 10px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>🎉 BDS 皮肤转 Windows 输入法控制台</h1>
    <p>成功从百度输入法手机端 .bds 皮肤提取并生成 Windows 桌面输入法全套适配主题。</p>
  </header>

  <div class="container">
    <div class="grid">
      {cards_html}
    </div>

    <div class="guide-section">
      <h2>📌 如何接入到 Windows 输入法使用？</h2>
      <ol>
        <li>
          <strong>体验与验证</strong>：点击上方任意皮肤卡片的 <code>🚀 启动交互打字预览</code>，即可在浏览器中全真模拟 Windows 桌面按键、首选高亮与拼音分词排版。
        </li>
        <li>
          <strong>接入水杉输入法 (Metasequoia IME) [推荐，一键生效]</strong>：
          <ul>
            <li>本转换器已全自动将生成的皮肤包复制到水杉专属目录：<code>%LOCALAPPDATA%\\metasequoiaime\\skins\\</code></li>
            <li>在 Windows 任务栏或托盘打开<strong>水杉输入法设置</strong> -> <strong>外观与主题</strong>。</li>
            <li>点击<strong>「刷新皮肤」</strong>（Refresh Skins），在皮肤列表中直接选择对应的 BDS 主题即可秒级换肤！</li>
          </ul>
        </li>
        <li>
          <strong>接入 RIME 小狼毫 (Weasel)</strong>：
          <ul>
            <li>打开对应目录下的 <code>weasel.custom.yaml</code>，将其中的配色代码段粘贴至 <code>%APPDATA%\\Rime\\weasel.custom.yaml</code>。</li>
            <li>点击小狼毫算法服务“重新部署”，即可使用提取出的纯正 BDS 配色方案。</li>
          </ul>
        </li>
      </ol>
    </div>
  </div>
</body>
</html>
"""
    out_file = Path(output_base_dir) / "index.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"[+] 统一控制台页面已生成: {out_file}")


if __name__ == "__main__":
    out_base = "converted_themes"
    if len(sys.argv) > 1:
        target_bds = sys.argv[1]
        out_base = sys.argv[2] if len(sys.argv) > 2 else "converted_themes"
        res = process_bds(target_bds, out_base)
        generate_index_dashboard([res], out_base)
    else:
        # 默认处理当前目录下所有 .bds 文件
        curr = Path(".")
        bds_files = list(curr.glob("*.bds"))
        if not bds_files:
            print("未在当前目录下找到 .bds 文件。")
        else:
            converted = []
            for bds in bds_files:
                res = process_bds(str(bds), out_base)
                converted.append(res)
            generate_index_dashboard(converted, out_base)

