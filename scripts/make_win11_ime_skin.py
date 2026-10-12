"""
Windows 11 原生输入法专属 BDS 皮肤生成器
无需安装任何第三方输入法，直接利用 Windows 11 自带微软拼音的“自定义文本输入主题”特性。
"""

import os
from pathlib import Path
from PIL import Image, ImageEnhance

out_dir = Path("win11_native_skins")
out_dir.mkdir(exist_ok=True)

# 1. 像素喵喵爪
cat_bg_src = Path("unpacked_4082/res/back.png")
if cat_bg_src.exists():
    im = Image.open(cat_bg_src).convert("RGBA")
    # 裁剪优化为适合候选框横幅比例的图片
    # 尺寸约 1080x400
    w, h = im.size
    crop_im = im.crop((0, 0, w, int(h * 0.85)))
    crop_im.save(out_dir / "01_像素喵喵爪_微软拼音背景.png")
    print("[+] 生成: 01_像素喵喵爪_微软拼音背景.png")

# 2. 小板爪爪兔
rabbit_bg_src = Path("unpacked_爪爪兔/res/back.png")
if rabbit_bg_src.exists():
    im = Image.open(rabbit_bg_src).convert("RGBA")
    w, h = im.size
    crop_im = im.crop((0, 0, w, int(h * 0.85)))
    crop_im.save(out_dir / "02_小板爪爪兔_微软拼音背景.png")
    print("[+] 生成: 02_小板爪爪兔_微软拼音背景.png")

# 3. Note 黑色极简
demo_src = Path("converted_themes/Note___静态黑色/cand.png")
if demo_src.exists():
    im = Image.open(demo_src).convert("RGBA")
    im.save(out_dir / "03_Note静态黑_微软拼音背景.png")
    print("[+] 生成: 03_Note静态黑_微软拼音背景.png")

print("所有 Windows 11 微软拼音原生专属皮肤壁纸已生成至 win11_native_skins/ 目录！")
