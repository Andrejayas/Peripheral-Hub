@echo off
title Peripheral Hub
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo Ada error saat menjalankan Peripheral Hub.
    pause
)
