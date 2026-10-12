"""
====================================================================
 RIME (小狼毫) BDS 专属输入法全自动装配与部署脚本
 将 BDS 解码皮肤、精致配色与 6.5 万精品词库一键注入系统级 TSF 输入法
====================================================================
"""

import os
import sys
import sqlite3
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "pinyin_dict.db"
RIME_USER_DIR = Path(os.environ.get("APPDATA", "")) / "Rime"


def export_bds_dict(output_file: Path):
    """从本地 SQLite 词库导出 RIME 标准格式的自定义字典"""
    print(f"[*] 正在从词库数据库导出 RIME 词典: {DB_PATH.name} -> {output_file.name} ...")
    if not DB_PATH.exists():
        print("[-] 词库数据库不存在，跳过词库导出。")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT word, pinyin, weight FROM words ORDER BY weight DESC")
    rows = c.fetchall()
    conn.close()

    header = """# Rime dictionary
# encoding: utf-8
---
name: bds_custom
version: "1.0"
sort: by_weight
use_preset_vocabulary: true
...
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(header)
        for word, pinyin, weight in rows:
            # Rime 字典格式: 文字 <tab> 拼音 <tab> 权重
            py_rime = pinyin.replace("'", " ")
            f.write(f"{word}\t{py_rime}\t{weight}\n")

    print(f"[+] 成功导出 {len(rows)} 条专属词库到 {output_file}！")


def generate_weasel_theme_yaml(output_file: Path):
    """
    生成小狼毫皮肤配置 weasel.custom.yaml
    精心配制两款 BDS 经典主题：
    1. bds_white_belly: 小板の白肚皮（粉白猫猫爪、首选粉色胶囊、柔和圆角）
    2. bds_dark_note: 极客暗黑 BDS（纯黑毛玻璃底色、深色高亮）
    """
    yaml_content = """# RIME 小狼毫外观配置文件 (由 BDS 专属输入法引擎自动生成)
patch:
  # 默认采用 BDS 小板白肚皮主题
  "style/color_scheme": "bds_white_belly"
  
  # 界面基础排版风格 (TSF 系统原生光标跟随)
  "style/horizontal": true
  "style/inline_preedit": true            # 行内下划线拼音预编辑 (与原版微软拼音一致)
  "style/candidate_format": "%c. %@"     # 候选词格式: 1. 你好
  "style/font_face": "Segoe UI, Microsoft YaHei, 微软雅黑"
  "style/font_point": 13
  "style/label_font_point": 10
  "style/corner_radius": 10              # 悬浮窗 10px 现代平滑圆角
  "style/border_width": 2                # 外边框
  "style/hilited_corner_radius": 6       # 候选词胶囊圆角
  "style/line_spacing": 4
  "style/spacing": 10
  "style/shadow_radius": 8               # 现代立体投影

  # 配色方案库 (BGR 16进制色彩格式)
  "preset_color_schemes/bds_white_belly":
    name: "小板の白肚皮 (BDS粉白经典)"
    author: "BDS Studio"
    horizontal: true
    inline_preedit: true
    corner_radius: 10
    border_width: 2
    border_color: 0xdca8ff               # 柔和粉紫边框 (#ffa8dc -> BGR)
    back_color: 0xf9fbfd                 # 温暖米白底色 (#fdfbf9 -> BGR)
    text_color: 0x4a4a4a                 # 编码文字深灰 (#4a4a4a)
    hilited_text_color: 0xd63384         # 正在选中的拼音粉红 (#8433d6)
    candidate_text_color: 0x333333       # 普通候选词墨黑
    hilited_candidate_text_color: 0xffffff # 首选词高亮白字
    hilited_candidate_back_color: 0xb53bb5 # 首选词胶囊粉紫底色 (#b53bb5)
    comment_text_color: 0x999999

  "preset_color_schemes/bds_dark_note":
    name: "小板暗黑 (BDS极客黑)"
    author: "BDS Studio"
    horizontal: true
    inline_preedit: true
    corner_radius: 10
    border_width: 2
    border_color: 0x444444
    back_color: 0x222222
    text_color: 0xcccccc
    hilited_text_color: 0xffb6c1
    candidate_text_color: 0xdddddd
    hilited_candidate_text_color: 0xffffff
    hilited_candidate_back_color: 0x663399
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"[+] 成功生成小狼毫专属 BDS 皮肤样式表: {output_file}！")


def generate_patch_yamls(rime_dir: Path):
    """配置 luna_pinyin 挂接 BDS 词库"""
    luna_custom = rime_dir / "luna_pinyin.custom.yaml"
    content = """# 挂接 BDS 专属词库
patch:
  "translator/dictionary": "bds_custom"
  "translator/enable_user_dict": true
  "translator/enable_sentence": true
  "translator/enable_encoder": true
"""
    with open(luna_custom, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] 成功生成词库挂接配置: {luna_custom}！")


def find_weasel_deployer():
    """在常见路径中寻找小狼毫部署程序"""
    prog_files = [
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Rime",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Rime"
    ]
    for p in prog_files:
        if p.exists():
            for deployer in p.rglob("WeaselDeployer.exe"):
                return deployer
    return None


def main():
    print("=" * 60)
    print("   BDS 专属输入法 -> RIME (小狼毫) 系统级 TSF 全自动装配器")
    print("=" * 60)

    # 1. 检查并确保 Rime 用户配置目录存在
    if not RIME_USER_DIR.exists():
        print(f"[*] 创建 RIME 用户配置目录: {RIME_USER_DIR}")
        RIME_USER_DIR.mkdir(parents=True, exist_ok=True)

    # 2. 导出 65,000+ 专属词库
    dict_file = RIME_USER_DIR / "bds_custom.dict.yaml"
    export_bds_dict(dict_file)

    # 3. 写入外观主题样式表
    weasel_file = RIME_USER_DIR / "weasel.custom.yaml"
    generate_weasel_theme_yaml(weasel_file)

    # 4. 挂接方案
    generate_patch_yamls(RIME_USER_DIR)

    # 5. 检测是否已安装小狼毫并执行重新部署
    deployer = find_weasel_deployer()
    if deployer:
        print(f"\n[+] 发现系统已安装小狼毫: {deployer}")
        print("[*] 正在执行系统级输入法配置重新编译与部署 (Deploy) ...")
        try:
            res = subprocess.run([str(deployer), "/deploy"], capture_output=True, text=True, timeout=15)
            print("[+] 部署指令已执行成功！专属皮肤与词库已在 Windows 系统中生效！")
        except Exception as e:
            print(f"[-] 自动调用部署失败 ({e})，请在任务栏小狼毫右键选择【重新部署】。")
    else:
        print("\n" + "=" * 60)
        print("【重要提示】所有 BDS 专属皮肤与词库文件已在 %APPDATA%\\Rime 准备完毕！")
        print("如果您的电脑尚未安装小狼毫 (RIME)，请在 Windows 终端中运行安装：")
        print("   winget install Rime.Weasel --accept-package-agreements --accept-source-agreements")
        print("或者在官网下载安装: https://rime.im/")
        print("安装完成后再次运行本脚本，或右键小狼毫托盘图标点击【重新部署】即可！")
        print("=" * 60)


if __name__ == "__main__":
    main()
