@echo off
chcp 65001 >nul
title 🐾 BDS-IME 工业级一体化输入法 (v2.0)
cd /d "%~dp0"
echo ========================================================
echo        🐾 BDS-IME 工业级一体化输入法 (v2.0) 🐾
echo ========================================================
echo.
echo [核心特性]
echo   1. 融合水杉输入法能力：支持大模型 AI 长句联想与现代皮肤规范。
echo   2. 内置皮肤创作工坊：随时按【Ctrl + Shift + S】或中键右下角药丸打开调色台。
echo   3. 快捷键绝对保护：Ctrl+C/V、Alt+Tab 100%% 原生穿透。
echo   4. 中英文切换：单按 Shift 键快速切换。
echo   5. 退出方式：按【Ctrl + Shift + Q】或右键右下角药丸安全退出。
echo.
echo 正在启动模块化输入法核心...
python -m bds_ime
pause
