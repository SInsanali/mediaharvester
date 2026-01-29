#!/bin/bash
# Media Harvester - macOS launcher
# Double-click this file to run the downloader

cd "$(dirname "$0")" || exit 1

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    echo "Please install it from https://www.python.org/downloads/"
    echo ""
    read -rp "Press Enter to close..."
    exit 1
fi

python3 mediaharvester.py

echo ""
read -rp "Press Enter to close..."
