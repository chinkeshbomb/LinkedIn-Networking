# LinkedIn Connection Automator

Browser automation tool for sending LinkedIn connection requests with personalized notes and follow-up messages.

## Features

- **Search & Connect**: Search LinkedIn with keywords/filters, send connection requests with personalized notes ({name} placeholder)
- **Follow-Up Sequences**: 3-stage follow-up messages triggered manually
- **Reply Detection**: Skips follow-ups if the person has already replied
- **Human-Like Behavior**: Random delays (3-15s), natural scroll patterns, randomized daily limits (50-60/day)
- **Persistent Login**: Uses browser profile so you only log in once
- **Web UI**: Simple dashboard to configure campaigns, track stats, view history

## Setup

### Quick Start (Windows)
```
Double-click start.bat
```

### Manual Setup
```bash
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt
playwright install chromium
python app.py
```

Then open http://localhost:5000

## First Run

1. Start the app
2. Click "Start Campaign" — a browser window will open
3. **Log in to LinkedIn manually** in that browser window (first time only)
4. The login session persists in `browser_data/` — you won't need to log in again
5. After logging in, click Start Campaign again

## How It Works

### Connection Requests
1. Enter your search keywords (same as LinkedIn search)
2. Choose filters (2nd/3rd connections, title filter)
3. Write your connection note (300 char max, use `{name}` for first name)
4. Click Start — the bot searches, scrolls through results, and sends connection requests

### Follow-Ups
1. Go to the Follow-Up tab
2. Write messages for Stage 1, 2, 3
3. Select which stage to send
4. Click Send Follow-Ups — it checks each connection for replies first, then messages those who haven't replied

## Configuration

Edit `config.py` to adjust:
- Delay ranges (make it faster/slower)
- Daily limits (default 50-60)
- Browser headless mode (set `HEADLESS = True` for background)

## Files

```
├── app.py              Flask web server + API
├── automator.py        Core Playwright automation (search, connect)
├── follow_up.py        Follow-up message logic + reply detection
├── config.py           All configurable settings
├── templates/
│   └── index.html      Web UI
├── data/
│   └── connections.json Tracking database
├── browser_data/       Persistent browser session (login stays)
├── start.bat           One-click launcher
└── requirements.txt    Python dependencies
```

## Risks

- LinkedIn may restrict your account if they detect automation
- The tool uses random delays and human-like behavior to minimize detection
- Keep daily limits reasonable (50-60 is already pushing it)
- Don't run 24/7 — use it during normal business hours
- If LinkedIn shows a CAPTCHA, stop and solve it manually

## Note

This is a personal productivity tool. Use responsibly.
