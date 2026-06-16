@echo off
chcp 65001 >nul
title PES6 Preset Manager

:: Instalar pywin32 si no esta
python -c "import winreg" >nul 2>&1
if %errorlevel% neq 0 (
    echo Instalando dependencia pywin32...
    pip install pywin32 --quiet
)

where python >nul 2>&1
if %errorlevel% == 0 (
    python "%~dp0pes6_preset_manager.py"
    goto :fin
)

echo Python no esta instalado.
echo Descargalo en: https://www.python.org/downloads/
echo Marca "Add Python to PATH" al instalar.
pause
start https://www.python.org/downloads/

:fin
