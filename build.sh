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

echo "Packaging into zip..."
cd dist
cp ../network.env .
cp ../aps_macros.json .
zip aps_release.zip aps network.env aps_macros.json
cd ..

echo "Build and packaging complete!"
echo "--------------------------------------------------------"
echo "Binary location: dist/aps"
echo "Release package: dist/aps_release.zip"
echo "--------------------------------------------------------"
