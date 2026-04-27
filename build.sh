#!/bin/bash
set -e

# Check for pyinstaller
if ! python3 -c "import PyInstaller" &> /dev/null; then
    echo "PyInstaller module not found in the current environment. Installing..."
    pip install pyinstaller
fi

echo "Cleaning up previous builds..."
rm -rf build/ dist/ *.spec

echo "Building aps..."
# --onefile: Create a single executable
# --name: Name of the output binary
# --hidden-import: Explicitly import paramiko if auto-detection fails (usually not needed but safe)
python3 -m PyInstaller --onefile --name aps aps.py

echo "Build complete!"
echo "--------------------------------------------------------"
echo "Binary location: dist/aps"
echo "IMPORTANT: Make sure to copy 'network.env' and 'aps_macros.json' alongside the binary."
echo "--------------------------------------------------------"
