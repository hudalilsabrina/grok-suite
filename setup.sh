#!/usr/bin/env bash
# Setup grok-suite (Linux / macOS)
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m patchright install chromium
.venv/bin/python -m camoufox fetch
echo
echo "Selesai. Contoh:"
echo "  xvfb-run -a .venv/bin/python grok.py harvest"
