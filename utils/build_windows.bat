@echo off
rem builds ..\Semiautomatic_masking_windows\Semiautomatic_masking.exe (the users do not need Python). Double-click this file on Windows.
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this file again.
    pause
    exit /b
)
python -m venv .build_env
call .build_env\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name Semiautomatic_masking --icon icon.ico --hidden-import matplotlib.backends.backend_tkagg --exclude-module IPython --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide6 --exclude-module pytest Semiautomatic_masking.py
if exist ..\Semiautomatic_masking_windows rmdir /s /q ..\Semiautomatic_masking_windows
move dist\Semiautomatic_masking ..\Semiautomatic_masking_windows
rmdir /s /q build dist .build_env
echo.
echo Done. Open ..\Semiautomatic_masking_windows\Semiautomatic_masking.exe
pause
