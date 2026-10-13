"""
====================================================================
 BDS 专属输入法 - 工业级 Release 独立打包脚本
 使用 PyInstaller 生成零依赖的 Windows 独立运行程序与 GitHub 发布包
====================================================================
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

# 强制 UTF-8 编码，防止 Windows CI/CD (cp1252) 下打印中文报错
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
ASSETS_DIR = BASE_DIR / "assets"
ICON_PATH = ASSETS_DIR / "app.ico"
VERSION = "1.0.2"


def clean_previous_builds():
    """清理历史生成目录"""
    print("[*] 清理旧的构建缓存与输出目录...")
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def run_pyinstaller():
    """执行 PyInstaller 打包流程"""
    print(f"[*] 开始打包 BDS 专属输入法 v{VERSION} ...")

    entry_script = BASE_DIR / "scripts" / "my_ime_engine.py"
    if not entry_script.exists():
        print(f"[-] 找不到主程序入口: {entry_script}")
        return False

    # 数据包与静态资源打包参数
    # 格式: 源路径:目标相对目录 (Windows 下为 ;)
    datas = [
        f"{BASE_DIR / 'data' / 'pinyin_dict.db'};data",
        f"{BASE_DIR / 'sound_packs'};sound_packs",
        f"{BASE_DIR / 'pet_assets'};pet_assets",
        f"{BASE_DIR / 'assets'};assets",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",                    # 无黑框控制台
        "--name", "BDS-IME",
        f"--icon={ICON_PATH}",
    ]

    for d in datas:
        cmd.extend(["--add-data", d])

    # 包含主入口
    cmd.append(str(entry_script))

    print(f"[*] 执行构建命令: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    return res.returncode == 0


def create_release_zip():
    """将 dist/BDS-IME 打包为便于 GitHub Releases 分发的绿色免安装 Zip 压缩包"""
    out_dir = DIST_DIR / "BDS-IME"
    if not out_dir.exists():
        print("[-] 打包输出目录不存在，无法生成 Zip。")
        return None

    zip_name = DIST_DIR / f"BDS-IME-v{VERSION}-Windows-x64-Portable.zip"
    print(f"[*] 正在生成 GitHub 发行版绿色压缩包: {zip_name.name} ...")

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        for file in out_dir.rglob("*"):
            arcname = file.relative_to(out_dir)
            z.write(file, arcname)

    print(f"[+] 绿色免安装发布包已就绪: {zip_name} (体积: {zip_name.stat().st_size / 1024 / 1024:.2f} MB)")
    return zip_name


def main():
    print("=" * 60)
    print("   BDS 专属输入法 - 工业级自动化构建与发布流水线")
    print("=" * 60)

    clean_previous_builds()
    success = run_pyinstaller()

    if success:
        zip_path = create_release_zip()
        print("\n" + "=" * 60)
        print("[+] 构建成功！")
        print(f"1. 独立程序输出目录: {DIST_DIR / 'BDS-IME' / 'BDS-IME.exe'}")
        if zip_path:
            print(f"2. GitHub 发布用 Zip: {zip_path}")
        print("=" * 60)
    else:
        print("\n[-] 打包过程出现异常，请检查上述错误日志。")


if __name__ == "__main__":
    main()
