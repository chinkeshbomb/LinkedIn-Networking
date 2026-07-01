"""Configuration for LinkedIn Automator."""

import random
import os

# --- Rate Limiting (Human-like behavior) ---
MIN_DELAY_BETWEEN_ACTIONS = 3  # seconds (scrolling, clicking)
MAX_DELAY_BETWEEN_ACTIONS = 8  # seconds
PAGE_SCROLL_DELAY_MIN = 2
PAGE_SCROLL_DELAY_MAX = 5

# --- Session Limits ---
# No cap per keyword. Runs until all pages are done.
# Set to a very high number (effectively unlimited within a session)
SESSION_LIMIT_MIN = 9999
SESSION_LIMIT_MAX = 9999
SESSION_DURATION_HOURS = 5

# --- Pacing ---
# 4 minutes between each profile
MIN_DELAY_BETWEEN_REQUESTS = 240
MAX_DELAY_BETWEEN_REQUESTS = 240

# --- Browser Settings ---
# Chrome connects via CDP - no bundled browser needed
CHROME_DEBUG_PORT = 9222
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Default Filters ---
# These geoUrn IDs are always applied unless overridden
DEFAULT_LOCATION_IDS = ["104305776", "106204383", "106031264", "100542498"]  # UAE, Dubai, Abu Dhabi, Sharjah

# --- LinkedIn URLs ---
LINKEDIN_BASE = "https://www.linkedin.com"
LINKEDIN_SEARCH_PEOPLE = "https://www.linkedin.com/search/results/people/"
LINKEDIN_MESSAGING = "https://www.linkedin.com/messaging/"

# --- Data Storage ---
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "connections.json")
LOG_FILE = os.path.join(DATA_DIR, "automation.log")


def random_delay(min_s=MIN_DELAY_BETWEEN_ACTIONS, max_s=MAX_DELAY_BETWEEN_ACTIONS):
    """Return a random delay for human-like timing."""
    return random.uniform(min_s, max_s)


def session_limit():
    """Randomize session limit between 50-60."""
    return random.randint(SESSION_LIMIT_MIN, SESSION_LIMIT_MAX)
