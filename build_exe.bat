@echo off
chcp 65001 >nul
title Build PES6 Settings+

:: Build a single-file Windows executable that bundles controller.png and the
:: pygame-ce / Pillow dependencies. Requires Python with those packages.
:: Output: dist\pes6_settings_plus.exe

python -m pip install --quiet pyinstaller pygame-ce Pillow

python -m PyInstaller --noconfirm --onefile --windowed ^
    --name pes6_settings_plus ^
    --add-data "controller.png;." ^
    pes6_settings_plus.py

echo.
echo Done. See dist\pes6_settings_plus.exe
pause
