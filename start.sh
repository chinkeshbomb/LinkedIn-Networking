#!/bin/bash
cd "$(dirname "$0")"

echo "========================================"
echo "  LinkedIn Automator - Starting..."
echo "========================================"
echo ""

# Check Python
python3 --version || { echo "ERROR: Python not found. Install from python.org"; exit 1; }

# Create venv if needed
if [ ! -f "venv/bin/python" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install deps if needed
python -c "import flask" 2>/dev/null || {
    echo "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
}

# Launch Chrome with debugging
echo "Launching Chrome..."
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9222 \
    --remote-allow-origins=* \
    --user-data-dir="$(pwd)/chrome_profile" \
    --no-first-run \
    --no-default-browser-check \
    https://www.linkedin.com &

sleep 4
echo ""
echo "Chrome running on port 9222"
echo "FIRST TIME: Log in to LinkedIn in Chrome."
echo "Open http://localhost:5000"
echo ""

python app.py
