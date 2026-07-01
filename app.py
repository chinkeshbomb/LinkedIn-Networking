"""LinkedIn Automator - Web UI."""

import asyncio
import threading
import json
from datetime import date, datetime

from flask import Flask, render_template, request, jsonify, Response

import config
from automator import load_data, run_connection_campaign, get_today_count

app = Flask(__name__)

# Store live status messages
status_messages = []
is_running = False


def add_status(msg):
    """Add a status message (thread-safe)."""
    status_messages.append({"time": str(date.today()), "message": msg})
    # Keep last 100 messages
    if len(status_messages) > 100:
        status_messages.pop(0)


@app.route("/")
def index():
    """Main dashboard."""
    data = load_data()
    today_count = get_today_count(data)
    total_sent = len(data.get("connections_sent", []))
    total_follow_ups = len(data.get("follow_ups", []))
    replied = len([c for c in data.get("connections_sent", []) if c.get("status") == "replied"])

    stats = {
        "today_count": today_count,
        "session_limit": f"{config.SESSION_LIMIT_MIN}-{config.SESSION_LIMIT_MAX} per session",
        "pacing": f"~{config.SESSION_LIMIT_MIN // config.SESSION_DURATION_HOURS}-{config.SESSION_LIMIT_MAX // config.SESSION_DURATION_HOURS}/hr",
        "total_sent": total_sent,
        "total_follow_only": len(data.get("follow_only", [])),
    }
    return render_template("index.html", stats=stats)


@app.route("/api/start-campaign", methods=["POST"])
def start_campaign():
    """Start a connection campaign."""
    global is_running

    if is_running:
        return jsonify({"error": "A campaign is already running"}), 400

    payload = request.json
    keywords_list = payload.get("keywords_list", [])
    # Backward compat: single keyword string
    if not keywords_list:
        single = payload.get("keywords", "").strip()
        if single:
            keywords_list = [single]
    note_template = payload.get("note", "").strip()
    max_pages = int(payload.get("max_pages", 5))

    # Parse filters
    filters = {}
    title_filter = payload.get("title_filter", "").strip()
    if title_filter:
        filters["title"] = title_filter
    location_filter = payload.get("location_filter", "").strip()
    if location_filter:
        filters["location"] = location_filter
    industry_filter = payload.get("industry_filter", "").strip()
    if industry_filter:
        filters["industry"] = [i.strip() for i in industry_filter.split(",") if i.strip()]
    company_filter = payload.get("company_filter", "").strip()
    if company_filter:
        filters["company"] = company_filter

    if not keywords_list:
        return jsonify({"error": "Keywords are required"}), 400

    if not note_template:
        return jsonify({"error": "Connection note is required"}), 400

    if len(note_template) > 300:
        return jsonify({"error": "Note must be 300 characters or less (LinkedIn limit)"}), 400

    is_running = True
    status_messages.clear()
    add_status(f"Starting campaign: {len(keywords_list)} keyword(s)")

    def run_in_thread():
        global is_running
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            total_sent = 0
            for i, keywords in enumerate(keywords_list):
                if not is_running:
                    add_status("Stopped by user")
                    break
                add_status(f"--- Keyword {i+1}/{len(keywords_list)}: {keywords} ---")
                result = loop.run_until_complete(
                    run_connection_campaign(
                        keywords=keywords,
                        note_template=note_template,
                        filters=filters if filters else None,
                        max_pages=max_pages,
                        status_callback=add_status,
                    )
                )
                total_sent += result.get("sent", 0)
                add_status(f"Keyword '{keywords}' done: {result['message']}")

            add_status(f"All keywords done. Total sent: {total_sent}")
            loop.close()
        except Exception as e:
            add_status(f"Campaign error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            is_running = False

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

    return jsonify({"status": "started", "message": "Campaign started"})


@app.route("/api/status")
def get_status():
    """Get current status messages."""
    return jsonify({
        "running": is_running,
        "messages": status_messages[-20:],  # Last 20 messages
    })


@app.route("/api/connections")
def get_connections():
    """Get all tracked connections."""
    data = load_data()
    return jsonify({
        "connections": data.get("connections_sent", []),
        "follow_only": data.get("follow_only", []),
        "profiles_db": data.get("profiles_db", []),
    })


@app.route("/api/keywords")
def get_keywords():
    """Load preconfigured keywords from file."""
    import os
    keywords_file = os.path.join(config.DATA_DIR, "keywords.txt")
    if os.path.exists(keywords_file):
        with open(keywords_file, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]
        return jsonify({"keywords": keywords})
    return jsonify({"keywords": [], "error": "No keywords file found"})


@app.route("/api/stop", methods=["POST"])
def stop_campaign():
    """Signal to stop (note: won't kill mid-action, but prevents next iteration)."""
    global is_running
    is_running = False
    add_status("Stop requested - will finish current action then stop")
    return jsonify({"status": "stopping"})


@app.route("/api/download-excel")
def download_excel():
    """Download all connection data as Excel file."""
    import csv
    from io import StringIO
    from flask import Response

    data = load_data()
    connections = data.get("connections_sent", [])
    follow_only = data.get("follow_only", [])

    # Create CSV (Excel-compatible)
    output = StringIO()
    writer = csv.writer(output)

    # All profiles database
    writer.writerow(["=== ALL PROFILES DATABASE ==="])
    writer.writerow(["Name", "Title", "Company", "Location", "Profile URL", "Action", "Date", "Search Keywords"])
    for p in data.get("profiles_db", []):
        writer.writerow([
            p.get("name", ""),
            p.get("title", ""),
            p.get("company", ""),
            p.get("location", ""),
            p.get("profile_url", ""),
            p.get("action", ""),
            p.get("date", ""),
            p.get("search_keywords", ""),
        ])

    writer.writerow([])
    writer.writerow(["=== CONNECTIONS SENT ==="])
    writer.writerow(["Name", "Title", "Company", "Location", "Profile URL", "Date Sent", "Note", "Status"])
    for c in connections:
        writer.writerow([
            c.get("name", ""),
            c.get("title", ""),
            c.get("company", ""),
            c.get("location", ""),
            c.get("profile_url", ""),
            c.get("date_sent", ""),
            c.get("note", ""),
            c.get("status", ""),
            c.get("source", ""),
        ])

    writer.writerow([])
    writer.writerow(["=== FOLLOW-ONLY PROFILES ==="])
    writer.writerow(["Name", "Title", "Company", "Location", "Profile URL", "Date Seen", "Search Keywords", "Reason"])
    for f in follow_only:
        writer.writerow([
            f.get("name", ""),
            f.get("title", ""),
            f.get("company", ""),
            f.get("location", ""),
            f.get("profile_url", ""),
            f.get("date_seen", ""),
            f.get("search_keywords", ""),
            f.get("reason", ""),
        ])

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=linkedin_contacts_{timestamp}.csv"},
    )


if __name__ == "__main__":
    import os
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    app.run(debug=True, port=5000)
