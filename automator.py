"""LinkedIn Connection Automator - Core browser automation logic.

Flow (Option B):
1. Search page -> collect all profile URLs + names + connect/follow status
2. For each person, open profile in NEW TAB:
   - Scrape data (title, company, location)
   - Send connection request (3 dots -> Connect -> Add note -> Send)
   - Close tab
   - Wait 90-180 seconds
3. Next page, repeat
"""

import asyncio
import json
import os
import random
import logging
import subprocess
from datetime import datetime, date
from urllib.parse import urlencode, quote_plus

from playwright.async_api import async_playwright, Page, BrowserContext

import config

# Setup logging - both file and console
os.makedirs(config.DATA_DIR, exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Avoid duplicate handlers on reload
if not logger.handlers:
    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Console handler - handle Windows encoding
    import sys, io
    if hasattr(sys.stdout, 'buffer'):
        stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    else:
        stream = sys.stdout
    console_handler = logging.StreamHandler(stream)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# --- Data Management ---

def load_data():
    """Load connection tracking data."""
    if os.path.exists(config.DATA_FILE):
        with open(config.DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "connections_sent": [],
        "follow_only": [],
        "daily_counts": {},
    }


def save_data(data):
    """Save connection tracking data."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_today_count(data):
    """Get number of connections sent today (for display only)."""
    today = str(date.today())
    return data.get("daily_counts", {}).get(today, 0)


def increment_today_count(data):
    """Increment today's count (tracking only)."""
    today = str(date.today())
    if "daily_counts" not in data:
        data["daily_counts"] = {}
    data["daily_counts"][today] = data["daily_counts"].get(today, 0) + 1
    save_data(data)


# --- Browser Connection --------------------------------------------------------

async def get_browser_context() -> BrowserContext:
    """
    Connect to an existing Chrome instance via CDP.
    Uses your real Chrome browser — no automation fingerprints.
    """
    chrome_path = config.CHROME_PATH
    debug_port = config.CHROME_DEBUG_PORT
    user_data_dir = os.path.join(config.BASE_DIR, "chrome_profile")
    cdp_url = f"http://localhost:{debug_port}"

    p = await async_playwright().start()

    try:
        logger.info(f"Connecting to Chrome via CDP at {cdp_url}...")
        browser = await p.chromium.connect_over_cdp(cdp_url)
        logger.info("Connected to existing Chrome instance")
    except Exception as e:
        logger.info(f"No existing Chrome found ({e}). Launching Chrome...")
        os.makedirs(user_data_dir, exist_ok=True)
        subprocess.Popen(
            [
                chrome_path,
                f"--remote-debugging-port={debug_port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={user_data_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.linkedin.com",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for attempt in range(10):
            await asyncio.sleep(2)
            try:
                browser = await p.chromium.connect_over_cdp(cdp_url)
                logger.info("Connected to Chrome after launch")
                break
            except Exception:
                if attempt == 9:
                    raise RuntimeError(
                        f"Could not connect to Chrome on port {debug_port}. "
                        "Make sure Chrome is running with --remote-debugging-port=9222"
                    )

    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    logger.info(f"Browser context ready ({len(context.pages)} existing pages)")
    return context


# --- Helpers -------------------------------------------------------------------

async def human_delay(min_s=None, max_s=None):
    """Wait a random human-like amount of time."""
    min_s = min_s or config.MIN_DELAY_BETWEEN_ACTIONS
    max_s = max_s or config.MAX_DELAY_BETWEEN_ACTIONS
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_scroll(page: Page):
    """Scroll page like a human would."""
    scroll_amount = random.randint(300, 700)
    await page.mouse.wheel(0, scroll_amount)
    await human_delay(config.PAGE_SCROLL_DELAY_MIN, config.PAGE_SCROLL_DELAY_MAX)


async def countdown_wait(seconds: int, status_callback=None, sent_count=0, session_limit=0, page=None):
    """Wait with countdown logging every 30 seconds. Random idle scrolling if page provided."""
    mins = seconds / 60
    logger.info(f"Waiting {seconds}s ({mins:.1f} min) before next...")
    if status_callback:
        status_callback(f"Waiting {seconds}s ({mins:.1f} min)... [{sent_count}/{session_limit} sent]")

    remaining = seconds
    while remaining > 0:
        # Random idle behavior: scroll and mouse move to look human
        if page and random.random() < 0.4:
            try:
                scroll = random.randint(-200, 400)
                await page.evaluate(f"window.scrollBy(0, {scroll})")
                await asyncio.sleep(random.uniform(0.5, 1.5))
                x = random.randint(200, 900)
                y = random.randint(200, 600)
                await page.mouse.move(x, y)
            except Exception:
                pass

        wait_chunk = min(30, remaining)
        await asyncio.sleep(wait_chunk)
        remaining -= wait_chunk
        if remaining > 0:
            logger.info(f"{remaining}s remaining...")
            if status_callback:
                status_callback(f"{remaining}s remaining...")


# --- Login Check --------------------------------------------------------------

async def check_login(page: Page) -> bool:
    """Check login by navigating to a search page."""
    logger.info("Checking login status...")
    try:
        await page.goto(
            "https://www.linkedin.com/search/results/people/?keywords=test",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        await asyncio.sleep(3)
        current_url = page.url
        logger.info(f"Login check URL: {current_url}")

        if "login" in current_url or "authwall" in current_url or "checkpoint" in current_url:
            return False
        if "/search/" in current_url or "/feed" in current_url:
            return True
        return True
    except Exception as e:
        logger.error(f"Error checking login: {e}")
        return False


# --- Search Page Parsing ------------------------------------------------------

async def search_people(page: Page, keywords: str, filters: dict = None, page_num: int = 1):
    """Navigate to LinkedIn people search with keywords and filters via URL."""
    from linkedin_ids import lookup_location_ids, lookup_industry_ids

    params = {"keywords": keywords, "origin": "FACETED_SEARCH"}
    if page_num > 1:
        params["page"] = page_num

    # Always apply default UAE location unless overridden
    if filters and "location" in filters and filters["location"]:
        geo_ids = lookup_location_ids(filters["location"])
        if geo_ids:
            geo_encoded = "%5B" + "%2C".join(f"%22{gid}%22" for gid in geo_ids) + "%5D"
            params["geoUrn"] = geo_encoded
        else:
            geo_encoded = "%5B" + "%2C".join(f"%22{gid}%22" for gid in config.DEFAULT_LOCATION_IDS) + "%5D"
            params["geoUrn"] = geo_encoded
    else:
        geo_encoded = "%5B" + "%2C".join(f"%22{gid}%22" for gid in config.DEFAULT_LOCATION_IDS) + "%5D"
        params["geoUrn"] = geo_encoded

    if filters:
        if "industry" in filters and filters["industry"]:
            industry_str = ",".join(filters["industry"]) if isinstance(filters["industry"], list) else filters["industry"]
            ind_ids = lookup_industry_ids(industry_str)
            if ind_ids:
                ind_encoded = "%5B" + "%2C".join(f"%22{iid}%22" for iid in ind_ids) + "%5D"
                params["industry"] = ind_encoded
        if "title" in filters and filters["title"]:
            params["titleFreeText"] = filters["title"]
        if "company" in filters and filters["company"]:
            params["company"] = filters["company"]

    # Build URL
    url_parts = []
    for key, val in params.items():
        if key in ("geoUrn", "industry"):
            url_parts.append(f"{key}={val}")
        else:
            url_parts.append(f"{key}={quote_plus(str(val))}")

    url = config.LINKEDIN_SEARCH_PEOPLE + "?" + "&".join(url_parts)
    logger.info(f"Search URL: {url}")

    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(3)
    await human_scroll(page)
    await asyncio.sleep(2)
    return url


async def collect_profiles_from_search(page: Page) -> list:
    """
    Collect profile URLs and basic info from search results.
    Returns list of {name, profile_url, has_connect_button}.
    """
    results = []

    try:
        await page.wait_for_selector(
            'div[role="list"], [data-testid="lazy-column"], [data-component-type="LazyColumn"]',
            timeout=10000,
        )
    except Exception:
        logger.warning("Search results list did not load")
        return results

    # Scroll to load all results
    for _ in range(3):
        await human_scroll(page)

    # Collect Connect buttons (aria-label="Invite X to connect")
    connect_buttons = await page.query_selector_all(
        'a[aria-label*="to connect"], [aria-label*="to connect"]'
    )
    for btn in connect_buttons:
        try:
            aria = await btn.get_attribute("aria-label") or ""
            # Skip pending invitations (check componentkey if present, or aria-label)
            ck = await btn.get_attribute("componentkey") or ""
            if "_pending" in ck or "pending" in aria.lower():
                continue
            name = aria.replace("Invite ", "").replace(" to connect", "").strip()
            # Get profile URL from vanityName in href or nearby link
            href = await btn.get_attribute("href") or ""
            profile_url = ""
            if "vanityName=" in href:
                vanity = href.split("vanityName=")[1].split("&")[0]
                profile_url = f"https://www.linkedin.com/in/{vanity}/"
            elif "/in/" in href:
                profile_url = href.split("?")[0]
            
            # If no URL from the button itself, try finding nearby profile link via JS
            if not profile_url:
                profile_url = await page.evaluate("""(label) => {
                    const el = document.querySelector('[aria-label="' + label + '"]');
                    if (!el) return '';
                    let node = el;
                    for (let i = 0; i < 15; i++) {
                        node = node.parentElement;
                        if (!node) break;
                        const link = node.querySelector('a[href*="/in/"]');
                        if (link) return link.href.split('?')[0];
                    }
                    return '';
                }""", aria)

            if name:
                results.append({"name": name, "profile_url": profile_url, "has_connect_button": True})
        except Exception as e:
            logger.warning(f"Error parsing connect btn: {e}")

    # Collect Follow buttons (aria-label="Follow X")
    follow_buttons = await page.query_selector_all(
        'button[aria-label^="Follow "]'
    )
    for btn in follow_buttons:
        try:
            aria = await btn.get_attribute("aria-label") or ""
            name = aria.replace("Follow ", "").strip()
            # Skip navigation-related Follow buttons (they have short generic names)
            if not name or name in ("", "Follow"):
                continue
            # Get profile URL via JavaScript
            profile_url = await page.evaluate("""(buttonLabel) => {
                const buttons = document.querySelectorAll('button[aria-label="' + buttonLabel + '"]');
                for (const btn of buttons) {
                    let node = btn;
                    for (let i = 0; i < 15; i++) {
                        node = node.parentElement;
                        if (!node) break;
                        const link = node.querySelector('a[href*="/in/"]');
                        if (link) return link.href.split('?')[0];
                    }
                }
                return '';
            }""", aria)

            if name:
                results.append({"name": name, "profile_url": profile_url, "has_connect_button": False})
                if not profile_url:
                    logger.warning(f"  Follow-only '{name}' - no profile URL found")
        except Exception as e:
            logger.warning(f"Error parsing follow btn: {e}")

    logger.info(f"Collected {len(results)} profiles ({sum(1 for r in results if r['has_connect_button'])} connect, {sum(1 for r in results if not r['has_connect_button'])} follow-only)")
    return results


# --- Profile Scraping ---------------------------------------------------------

async def scrape_profile(page: Page) -> dict:
    """
    Scrape profile data from the currently loaded profile page.
    
    LinkedIn profile top card structure (sequential <p> elements):
    1. Name (e.g., "Ashwin Sujith - CHRM")
    2. Headline (e.g., "HR Professional | Talent Onboarding...")
    3. Company (e.g., "First Abu Dhabi Bank (FAB)")  
    4. Location (e.g., "Abu Dhabi Emirate, United Arab Emirates")
    
    Returns {title, company, location, about}.
    """
    data = {"title": "", "company": "", "location": "", "about": ""}

    try:
        # Wait for page to render, then scroll to load Experience section
        await asyncio.sleep(2)
        await page.evaluate("window.scrollBy(0, 400)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollBy(0, 600)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollBy(0, 600)")
        await asyncio.sleep(2)
        # Scroll back to top for the profile card scraping
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # 1. Get title from page title (always reliable)
        page_title = await page.title()
        logger.info(f"   Page title raw: {page_title}")
        if " - " in page_title and "LinkedIn" in page_title:
            data["title"] = page_title.split(" | LinkedIn")[0].split(" - ", 1)[1].strip()

        # 2. Extract company, location, job title from profile card
        profile_info = await page.evaluate("""() => {
            const result = {company: '', location: '', headline: '', job_title: '', about: ''};
            
            // Get all <p> tags with bounding rects (visible on screen)
            const allP = document.querySelectorAll('p');
            const texts = [];
            for (const p of allP) {
                const text = p.innerText.trim();
                if (text && text.length > 1 && text.length < 300) {
                    const rect = p.getBoundingClientRect();
                    if (rect.top > 50 && rect.top < 500 && rect.height > 0) {
                        texts.push({text: text, top: rect.top});
                    }
                }
            }
            texts.sort((a, b) => a.top - b.top);
            
            // Location keywords
            const locationKeywords = ['Dubai', 'Abu Dhabi', 'UAE', 'United Arab Emirates', 
                'Mumbai', 'India', 'Bangalore', 'Bengaluru', 'Delhi', 'London', 'Singapore', 
                'Riyadh', 'Saudi Arabia', 'Qatar', 'Doha', 'Bahrain', 'Kuwait', 'Sharjah',
                'Emirate', 'Province', 'Region', 'Area', 'Gurgaon', 'Gurugram', 'Noida',
                'Hyderabad', 'Pune', 'Chennai', 'Kolkata', 'Ahmedabad', 'Jaipur',
                'Haryana', 'Maharashtra', 'Karnataka', 'Tamil Nadu', 'Telangana',
                'Greater', 'Metropolitan', 'New York', 'California', 'Texas'];
            
            // Find location and company (company is <p> right before location)
            for (let i = 0; i < texts.length; i++) {
                const t = texts[i].text;
                for (const kw of locationKeywords) {
                    if (t.includes(kw) && t.length < 80) {
                        result.location = t;
                        if (i > 0) {
                            const prev = texts[i-1].text;
                            if (prev.length < 100 && !prev.includes('|') && 
                                prev !== 'Follow' && prev !== 'Connect' && prev !== 'Message') {
                                result.company = prev;
                            }
                        }
                        break;
                    }
                }
                if (result.location) break;
            }
            
            // Find headline (contains | separators)
            for (const t of texts) {
                if (t.text.includes('|') && t.text.length > 20 && t.text.length < 250) {
                    result.headline = t.text;
                    break;
                }
            }
            
            // --- Job Title from Experience section ---
            // Structure: <p>Job Title</p><p>Company · Full-time</p><p>Dates</p><p>Location</p>
            // The job title is the <p> RIGHT BEFORE the "Company · Full-time" line
            const allPFull = document.querySelectorAll('p');
            const pTexts = [];
            for (const p of allPFull) {
                const text = p.innerText.trim();
                if (text && text.length > 1) {
                    pTexts.push(text);
                }
            }
            
            for (let i = 0; i < pTexts.length; i++) {
                const text = pTexts[i];
                // Match: "Company · Full-time" or "Company · Part-time" etc.
                if (text.includes(' · ') && 
                    (text.includes('Full-time') || text.includes('Part-time') || 
                     text.includes('Contract') || text.includes('Self-employed') ||
                     text.includes('Freelance') || text.includes('Internship'))) {
                    
                    // Company is everything before " · "
                    const companyRaw = text.split(' · ')[0].trim();
                    // Clean company: take before first " - " or " | " if present
                    if (!result.company) {
                        if (companyRaw.includes(' - ')) {
                            result.company = companyRaw.split(' - ')[0].trim();
                        } else if (companyRaw.includes(' | ')) {
                            result.company = companyRaw.split(' | ')[0].trim();
                        } else {
                            result.company = companyRaw;
                        }
                    }
                    
                    // Job title is the <p> immediately BEFORE this one
                    if (i > 0) {
                        const prevText = pTexts[i - 1];
                        // Make sure it's not a date, location, or section header
                        if (prevText.length > 2 && prevText.length < 100 &&
                            !prevText.includes(' · ') &&
                            !prevText.includes('Experience') &&
                            !prevText.includes('present') &&
                            !prevText.match(/^[0-9]{4}/) &&
                            !prevText.match(/yr|mo/)) {
                            result.job_title = prevText;
                        }
                    }
                    break;
                }
            }
            
            // About section
            const boxes = document.querySelectorAll('[data-testid="expandable-text-box"]');
            if (boxes.length > 0) {
                result.about = boxes[0].innerText.trim().substring(0, 500);
            }
            
            return result;
        }""")

        if profile_info.get("company"):
            data["company"] = profile_info["company"]
        if profile_info.get("location"):
            data["location"] = profile_info["location"]
        if profile_info.get("job_title"):
            data["title"] = profile_info["job_title"]  # Actual role from Experience
        elif profile_info.get("headline"):
            # Extract clean title from headline: take part before first | or full if short
            headline = profile_info["headline"]
            if "|" in headline:
                data["title"] = headline.split("|")[0].strip()
            elif " at " in headline:
                data["title"] = headline.split(" at ")[0].strip()
            else:
                data["title"] = headline[:100]
        if profile_info.get("about"):
            data["about"] = profile_info["about"]

        # Clean company — if it contains | it grabbed too much from headline
        if data["company"] and "|" in data["company"]:
            data["company"] = data["company"].split("|")[0].strip()

        # Fallback: extract company from title "Role at Company"
        if not data["company"] and data["title"] and " at " in data["title"]:
            data["company"] = data["title"].split(" at ")[-1].strip()

    except Exception as e:
        logger.warning(f"Error scraping profile: {e}")

    return data


# --- Connection Request from Profile ------------------------------------------

async def send_connect_from_profile(page: Page, name: str, note: str) -> bool:
    """
    Send connection request from a profile page.
    Always uses: More (3 dots) -> Connect -> Add note -> Send
    Never tries the direct Connect button (unreliable on follow-only profiles).
    """
    try:
        # Scroll to top
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # Click "More" (3 dots) button via JS
        more_clicked = await page.evaluate("""() => {
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {
                const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                const hasSvg = btn.querySelector('svg[id*="overflow"]');
                if ((label.includes('more') || hasSvg) && 
                    btn.offsetParent !== null && 
                    btn.getBoundingClientRect().height > 0) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")

        if not more_clicked:
            logger.warning(f"No More button for {name}")
            return False

        await human_delay(1, 2)

        # Click "Connect" in the dropdown that just appeared
        # The dropdown item structure: <a> > <div> > <div> > <p>Connect</p>
        # Key insight: the dropdown is the LAST rendered overlay on the page
        # So we find all <a> tags containing <p>Connect</p> and click the LAST one
        connect_clicked = await page.evaluate("""() => {
            return new Promise(resolve => {
                setTimeout(() => {
                    // Find all <a> tags that contain a <p> with exact text "Connect"
                    const allLinks = document.querySelectorAll('a');
                    const connectLinks = [];
                    for (const a of allLinks) {
                        const pEls = a.querySelectorAll('p');
                        for (const p of pEls) {
                            if (p.innerText.trim() === 'Connect' && 
                                p.offsetParent !== null &&
                                p.getBoundingClientRect().height > 0) {
                                connectLinks.push(a);
                            }
                        }
                    }
                    
                    // Click the LAST one (dropdown renders after page content)
                    if (connectLinks.length > 0) {
                        connectLinks[connectLinks.length - 1].click();
                        resolve(true);
                        return;
                    }
                    
                    // Fallback: find last visible <p>Connect</p> and click its <a> parent
                    const allP = document.querySelectorAll('p');
                    const connectPs = [];
                    for (const p of allP) {
                        if (p.innerText.trim() === 'Connect' && 
                            p.offsetParent !== null &&
                            p.getBoundingClientRect().height > 0) {
                            connectPs.push(p);
                        }
                    }
                    if (connectPs.length > 0) {
                        const lastP = connectPs[connectPs.length - 1];
                        const link = lastP.closest('a') || lastP;
                        link.click();
                        resolve(true);
                        return;
                    }
                    
                    resolve(false);
                }, 1000);
            });
        }""")

        if not connect_clicked:
            logger.warning(f"No Connect in dropdown for {name}")
            await page.keyboard.press("Escape")
            return False

        logger.info(f"Clicked More -> Connect for {name}")
        await human_delay(2, 4)

        # --- Modal handling ---
        # Modal 1: "Add a note to your invitation?"
        # Wait for the modal to appear (LinkedIn takes 1-2s to render it)
        add_note_clicked = False
        try:
            # Try multiple selectors for "Add a note" button
            add_note_btn = await page.wait_for_selector(
                'button:has(span:text-is("Add a note")), '
                'button:has(span.artdeco-button__text:text-is("Add a note"))',
                timeout=8000,
            )
            if add_note_btn:
                await add_note_btn.click()
                add_note_clicked = True
                await human_delay(1, 2)
        except Exception:
            # Fallback: use JS to find and click
            add_note_clicked = await page.evaluate("""() => {
                const spans = document.querySelectorAll('span');
                for (const span of spans) {
                    if (span.innerText.trim() === 'Add a note' && 
                        span.offsetParent !== null) {
                        const btn = span.closest('button');
                        if (btn) { btn.click(); return true; }
                        span.click(); return true;
                    }
                }
                return false;
            }""")
            if add_note_clicked:
                await human_delay(1, 2)

        if not add_note_clicked:
            # Maybe "Send without a note" is showing instead
            send_without = await page.query_selector('button:has(span:text-is("Send without a note"))')
            if send_without:
                await send_without.click()
                await human_delay(2, 3)
                logger.info(f"Sent to {name} (no note - Add a note not found)")
                return True
            logger.warning(f"No Add a note button for {name}")
            await page.keyboard.press("Escape")
            return False

        # Modal 2: textarea
        note_field = None
        try:
            note_field = await page.wait_for_selector('textarea#custom-message', timeout=5000)
        except Exception:
            pass

        if not note_field:
            # Try "Send without a note"
            send_without = await page.query_selector('button:has(span:text-is("Send without a note"))')
            if send_without:
                await send_without.click()
                await human_delay(2, 3)
                logger.info(f"Sent to {name} (no note)")
                return True
            logger.warning(f"No note field for {name}")
            await page.keyboard.press("Escape")
            return False

        # Type note
        first_name = name.split(" ")[0]
        personalized_note = note.replace("{name}", first_name)
        await note_field.click()
        await asyncio.sleep(0.3)
        for char in personalized_note:
            await note_field.type(char, delay=random.randint(30, 80))
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.8))
        await human_delay(1, 2)

        # Click Send
        await asyncio.sleep(0.5)
        send_btn = await page.query_selector('button[aria-label="Send invitation"]:not([disabled])')
        if not send_btn:
            await asyncio.sleep(1)
            send_btn = await page.query_selector('button[aria-label="Send invitation"]:not([disabled])')

        if send_btn:
            await send_btn.click()
            await human_delay(2, 3)
            logger.info(f"Sent connection to {name}")
            return True
        else:
            # JS fallback
            sent = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const label = b.getAttribute('aria-label') || '';
                    if (label.includes('Send') && !b.disabled && b.offsetParent) {
                        b.click(); return true;
                    }
                }
                return false;
            }""")
            if sent:
                await human_delay(2, 3)
                logger.info(f"Sent to {name} (JS fallback)")
                return True
            logger.warning(f"Send disabled for {name}")
            await page.keyboard.press("Escape")
            return False

    except Exception as e:
        logger.error(f"Error connecting to {name}: {e}")
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False



# --- Send Connect from Search Page --------------------------------------------

async def send_connect_from_search(page: Page, name: str, note: str) -> bool:
    """
    Send connection request from the SEARCH RESULTS page.
    Clicks the Connect button by aria-label, handles the modal.
    """
    try:
        # Click the Connect button for this person (JS click for reliability)
        clicked = await page.evaluate("""(name) => {
            // Find any element with aria-label containing "Invite [name] to connect"
            const els = document.querySelectorAll('[aria-label*="to connect"]');
            for (const el of els) {
                const label = el.getAttribute('aria-label') || '';
                if (label.includes(name)) {
                    // Click the <a> parent if exists, otherwise click element itself
                    const link = el.closest('a') || el;
                    link.click();
                    return true;
                }
            }
            return false;
        }""", name)

        if not clicked:
            logger.warning(f"Connect button not found on search page for {name}")
            return False

        await human_delay(1, 3)

        # Modal 1: "Add a note?"
        try:
            add_note_btn = await page.wait_for_selector(
                'button:has(span:text-is("Add a note"))',
                timeout=5000,
            )
            if add_note_btn:
                await add_note_btn.click()
                await human_delay(1, 2)
        except Exception:
            pass

        # Modal 2: textarea
        note_field = None
        try:
            note_field = await page.wait_for_selector('textarea#custom-message', timeout=5000)
        except Exception:
            pass

        if not note_field:
            # Try "Send without a note"
            send_without = await page.query_selector('button:has(span:text-is("Send without a note"))')
            if send_without:
                await send_without.click()
                await human_delay(2, 3)
                logger.info(f"Sent to {name} (no note, from search)")
                return True
            logger.warning(f"No note field for {name} on search page")
            await page.keyboard.press("Escape")
            return False

        # Type note
        first_name = name.split(" ")[0]
        personalized_note = note.replace("{name}", first_name)
        await note_field.click()
        await asyncio.sleep(0.3)
        for char in personalized_note:
            await note_field.type(char, delay=random.randint(30, 80))
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.8))
        await human_delay(1, 2)

        # Click Send
        await asyncio.sleep(0.5)
        send_btn = await page.query_selector('button[aria-label="Send invitation"]:not([disabled])')
        if not send_btn:
            await asyncio.sleep(1)
            send_btn = await page.query_selector('button[aria-label="Send invitation"]:not([disabled])')

        if send_btn:
            await send_btn.click()
            await human_delay(2, 3)
            logger.info(f"Sent to {name} (from search page)")
            return True
        else:
            # JS fallback
            sent = await page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const label = b.getAttribute('aria-label') || '';
                    if (label.includes('Send') && !b.disabled && b.offsetParent) {
                        b.click(); return true;
                    }
                }
                return false;
            }""")
            if sent:
                await human_delay(2, 3)
                return True
            await page.keyboard.press("Escape")
            return False

    except Exception as e:
        logger.error(f"Error connecting from search for {name}: {e}")
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False


# --- Main Campaign ------------------------------------------------------------

async def run_connection_campaign(
    keywords: str,
    note_template: str,
    filters: dict = None,
    max_pages: int = 5,
    status_callback=None,
):
    """
    Campaign flow:
    - For each person on search results:
      A. If Connect button available -> send from search page
      B. Open profile in new tab -> scrape data
      C. If Follow-only -> try connect from profile (More -> Connect)
      D. Save EVERY profile to database with action taken
    """
    data = load_data()
    session_limit_val = config.session_limit()
    sent_count = 0
    skipped_count = 0
    already_sent_urls = {c["profile_url"] for c in data.get("connections_sent", [])}

    if "profiles_db" not in data:
        data["profiles_db"] = []
    existing_profile_urls = {p["profile_url"] for p in data["profiles_db"]}

    if "follow_only" not in data:
        data["follow_only"] = []

    if status_callback:
        status_callback(f"Session: {session_limit_val} requests | Pace: {config.MIN_DELAY_BETWEEN_REQUESTS}-{config.MAX_DELAY_BETWEEN_REQUESTS}s")

    context = await get_browser_context()
    search_page = await context.new_page()

    try:
        # Login check
        is_logged_in = await check_login(search_page)
        logger.info(f"Login: {'OK' if is_logged_in else 'FAILED'}")
        if not is_logged_in:
            msg = "Not logged in. Log in to LinkedIn in Chrome, then retry."
            if status_callback:
                status_callback(msg)
            await asyncio.sleep(60)
            return {"status": "not_logged_in", "sent": 0, "message": msg}

        if status_callback:
            status_callback(f"Logged in. Searching: {keywords}")
        logger.info(f"Campaign: keywords='{keywords}', max_pages={max_pages}")

        for page_num in range(1, max_pages + 1):
            if sent_count >= session_limit_val:
                if status_callback:
                    status_callback(f"Session limit reached ({session_limit_val}). Done!")
                break

            logger.info(f"-- Page {page_num} --")
            if status_callback:
                status_callback(f"Page {page_num}...")

            await search_people(search_page, keywords, filters, page_num)
            await human_delay(2, 4)

            profiles = await collect_profiles_from_search(search_page)
            if not profiles:
                # Check if the page has results but all are pending/already processed
                has_any_results = await search_page.query_selector(
                    '[data-testid="lazy-column"], div[role="list"]'
                )
                if has_any_results:
                    # Page has results but none are connectable — skip to next page
                    logger.info("Page has results but all are pending/already connected. Moving to next page.")
                    if status_callback:
                        status_callback(f"Page {page_num}: all profiles already processed. Next page...")
                    continue
                else:
                    logger.info("No results on this page, stopping.")
                    break

            if status_callback:
                status_callback(f"Page {page_num}: {len(profiles)} profiles")

            for person in profiles:
                if sent_count >= session_limit_val:
                    break

                name = person["name"]
                profile_url = person["profile_url"]
                has_connect = person["has_connect_button"]

                if not profile_url:
                    skipped_count += 1
                    continue

                # Skip entirely if already in profiles_db (processed in previous run)
                if profile_url in existing_profile_urls:
                    logger.info(f"Skip {name} (already in database)")
                    skipped_count += 1
                    continue

                # Check if already connected (skip CONNECT but still SCRAPE)
                already_connected = profile_url in already_sent_urls

                # --- A. Connect from SEARCH PAGE if button available ---
                connect_success = False
                action = ""

                if has_connect and not already_connected:
                    logger.info(f"[SEARCH] Connecting: {name}")
                    if status_callback:
                        status_callback(f"Connecting from search: {name}")
                    connect_success = await send_connect_from_search(search_page, name, note_template)
                    if connect_success:
                        action = "connected"
                        sent_count += 1
                        increment_today_count(data)
                        already_sent_urls.add(profile_url)
                    else:
                        action = "connect_failed_search"
                elif already_connected:
                    action = "already_sent"

                # --- B. Open profile in new tab, scrape data ---
                logger.info(f"[PROFILE] Scraping: {name}")
                if status_callback:
                    status_callback(f"Scraping: {name}")

                profile_data = {"title": "", "company": "", "location": "", "about": ""}
                profile_page = await context.new_page()
                try:
                    await profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
                    await human_delay(2, 4)
                    profile_data = await scrape_profile(profile_page)
                    logger.info(f"   Title: {profile_data['title']}")
                    logger.info(f"   Company: {profile_data['company']}")
                    logger.info(f"   Location: {profile_data['location']}")

                    # --- C. Follow-only: try connect from profile ---
                    if not has_connect and not connect_success and not already_connected:
                        logger.info(f"[PROFILE] Trying connect: {name}")
                        if status_callback:
                            status_callback(f"Connecting from profile: {name}")
                        connect_success = await send_connect_from_profile(profile_page, name, note_template)
                        if connect_success:
                            action = "connected_from_profile"
                            sent_count += 1
                            increment_today_count(data)
                            already_sent_urls.add(profile_url)
                        else:
                            action = "could_not_connect"

                except Exception as e:
                    logger.error(f"Error on profile {name}: {e}")
                    if not action:
                        action = "error"
                finally:
                    await profile_page.close()

                if not action:
                    action = "already_pending"

                # --- D. Save to database ---
                db_entry = {
                    "name": name,
                    "profile_url": profile_url,
                    "title": profile_data["title"],
                    "company": profile_data["company"],
                    "location": profile_data["location"],
                    "about": profile_data["about"],
                    "action": action,
                    "date": str(datetime.now()),
                    "search_keywords": keywords,
                }

                # Always add to profiles_db (update if exists)
                if profile_url not in existing_profile_urls:
                    data["profiles_db"].append(db_entry)
                    existing_profile_urls.add(profile_url)
                else:
                    # Update existing entry
                    for i, p in enumerate(data["profiles_db"]):
                        if p["profile_url"] == profile_url:
                            data["profiles_db"][i] = db_entry
                            break

                if connect_success:
                    data["connections_sent"].append({
                        **db_entry,
                        "note": note_template.replace("{name}", name.split(" ")[0]),
                        "status": "pending",
                    })

                if action in ("could_not_connect", "connect_failed_search"):
                    data["follow_only"].append(db_entry)

                save_data(data)

                logger.info(f"   Action: {action}")
                if status_callback:
                    mark = "[+]" if connect_success else "[x]"
                    status_callback(
                        f"{mark} {name} | {profile_data['title']} | {action} [{sent_count}/{session_limit_val}]"
                    )

                # --- E. Wait between EVERY profile (4 minutes) ---
                delay = 240
                await countdown_wait(delay, status_callback, sent_count, session_limit_val, search_page)

            await human_delay(3, 6)

    except Exception as e:
        logger.error(f"Campaign error: {e}")
        if status_callback:
            status_callback(f"Error: {e}")
    finally:
        try:
            await search_page.close()
        except Exception:
            pass

    # Save keyword stats
    if "keyword_stats" not in data:
        data["keyword_stats"] = {}
    data["keyword_stats"][keywords] = {
        "profiles_found": sent_count + skipped_count,
        "connected": sent_count,
        "skipped": skipped_count,
        "last_run": str(datetime.now()),
    }
    save_data(data)

    result = {
        "status": "completed",
        "sent": sent_count,
        "skipped": skipped_count,
        "session_limit": session_limit_val,
        "message": f"Done. Sent {sent_count}/{session_limit_val}, skipped {skipped_count}.",
    }
    logger.info(f"Result: {result}")
    return result
