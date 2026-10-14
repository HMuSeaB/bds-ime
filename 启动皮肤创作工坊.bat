@echo off
chcp 65001 >nul
title BDS Skin Studio · 皮肤创作工坊

echo ========================================================
echo        🎨 BDS Skin Studio (皮肤创作工坊) 🎨
echo ========================================================
echo.
echo 正在启动可视化创作工作台...
echo 稍后将在浏览器中自动打开控制台面板。
echo.

cd /d "%~dp0"
python scripts/skin_studio_server.py

pause
