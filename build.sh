#!/bin/bash
set -e

# Check for pyinstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

echo "Cleaning up previous builds..."
rm -rf build/ dist/ *.spec

echo "Building aps_ctl..."
# --onefile: Create a single executable
# --name: Name of the output binary
# --hidden-import: Explicitly import paramiko if auto-detection fails (usually not needed but safe)
pyinstaller --onefile --name aps_ctl aps_ctl.py

echo "Build complete!"
echo "--------------------------------------------------------"
echo "Binary location: dist/aps_ctl"
echo "IMPORTANT: You must copy 'aps_config.json' alongside the binary to the target machine."
echo "--------------------------------------------------------"
