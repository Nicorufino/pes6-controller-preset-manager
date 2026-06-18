@echo off
chcp 65001 >nul
title PES6 Settings+

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed.
    echo Download it from: https://www.python.org/downloads/
    echo Check "Add Python to PATH" during installation.
    pause
    start https://www.python.org/downloads/
    goto :eof
)

:: Install pygame-ce if missing (needed for live button capture)
python -c "import pygame" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependency pygame-ce...
    python -m pip install pygame-ce --quiet
)

:: Install Pillow if missing (used to show the controller image, if provided)
python -c "import PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependency Pillow...
    python -m pip install Pillow --quiet
)

python "%~dp0pes6_settings_plus.py"
