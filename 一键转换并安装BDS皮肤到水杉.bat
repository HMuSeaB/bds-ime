@echo off
chcp 65001 >nul
title 水杉输入法 (MSIME) BDS 皮肤一键转换与安装工具

echo ========================================================
echo   🌲 水杉输入法 (Metasequoia IME) BDS 皮肤一键安装工具 🌲
echo ========================================================
echo.

cd /d "%~dp0"

if "%~1"=="" (
    echo [模式] 正在转换当前目录下所有 .bds 皮肤...
    echo.
    python scripts/bds_converter.py
) else (
    echo [模式] 正在处理指定拖拽的 BDS 皮肤: "%~1"
    echo.
    python scripts/bds_converter.py "%~1"
)

echo.
echo ========================================================
echo 🎉 转换与部署完成！
echo.
echo 📌 如何在水杉输入法中启用：
echo 1. 打开水杉输入法【设置】 -> 【外观与主题】
echo 2. 点击【刷新皮肤】（Refresh Skins）
echo 3. 在皮肤列表中选择刚刚生成的 BDS 主题，即可秒级换肤！
echo.
echo 📁 皮肤已自动同步到：
echo    %%LOCALAPPDATA%%\metasequoiaime\skins\
echo ========================================================
echo 按任意键退出本窗口...
pause >nul
