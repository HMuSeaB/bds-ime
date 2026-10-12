@echo off
chcp 65001 >nul
title BDS / ZIP 自动解锁与解包工具

echo ========================================================
echo        🐾 BDS / ZIP 皮肤自动解码与解锁工具 🐾
echo ========================================================
echo.

cd /d "%~dp0"

if "%~1"=="" (
    echo [模式] 正在全盘扫描当前目录及所有子文件夹...
    echo.
    python scripts/auto_bds_unlocker.py . -x
) else (
    echo [模式] 正在处理指定拖拽的文件/文件夹: "%~1"
    echo.
    python scripts/auto_bds_unlocker.py "%~1" -x
)

echo.
echo ========================================================
echo 处理完毕！已成功解锁并解包到对应目录。
echo 按任意键退出本窗口...
pause >nul
