#!/bin/bash
# Run Clip Review locally without building a .app (Python required)
set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python3" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/pip install --quiet -r requirements.txt
fi

echo "Starting Clip Review at http://127.0.0.1:8765"
echo "Press Ctrl+C to stop."
open "http://127.0.0.1:8765" &
.venv/bin/python3 server.py
