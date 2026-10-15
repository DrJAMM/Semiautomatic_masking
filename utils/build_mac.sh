#!/bin/bash
# builds ../Semiautomatic_masking.app (double-click, no Python needed for the users). Run this on a Mac:  bash utils/build_mac.sh
cd "$(dirname "$0")"
python3 -m venv .build_env
source .build_env/bin/activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name Semiautomatic_masking --icon icon.icns --add-data icon.png:. \
    --hidden-import matplotlib.backends.backend_macosx \
    --exclude-module tkinter --exclude-module IPython --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide6 --exclude-module pytest Semiautomatic_masking.py
rm -rf ../Semiautomatic_masking.app
mv dist/Semiautomatic_masking.app ..
rm -rf build dist .build_env
echo "done: ../Semiautomatic_masking.app"
