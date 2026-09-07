#!/usr/bin/env python3
"""
Auto-register for the ManaBar Pub Quiz.

Requirements:
    pip install requests beautifulsoup4

Usage:
    python register_pubquiz.py                # next Wednesday
    python register_pubquiz.py 2026-09-16     # a specific quiz date
"""

import sys
import json
import datetime as dt
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# site details
BASE_URL = "https://manabar.ch"
URL_TMPL = BASE_URL + "/en/event/weekly-pub-quiz-{date}"  # {date} = YYYY-MM-DD
QUIZ_WEEKDAY = 2  # Wednesday=2
CONFIG_FILE = Path(__file__).with_name("config.json")

# maps json to keys
KEY_TO_LABEL = {
    "name": "name",
    "email": "email",
    "team": "team",
    "group_size": "group size",
    "message": "message",
}
REQUIRED_KEYS = ["name", "email", "team", "group_size"]


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        sys.exit(f"! {CONFIG_FILE.name} not found.")
    with CONFIG_FILE.open(encoding="utf-8") as fh:
        cfg = json.load(fh)
    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        sys.exit(f"! config.json is missing values for: {', '.join(missing)}")
    return cfg


def next_quiz_date(weekday: int = QUIZ_WEEKDAY) -> dt.date:
    """Date of the next occurrence of `weekday` (today counts if it matches)."""
    today = dt.date.today()
    days_ahead = (weekday - today.weekday()) % 7
    return today + dt.timedelta(days=days_ahead)


def field_name_for_label(form, keyword: str):
    """Return the input `name` whose <label> text contains `keyword`."""
    for label in form.find_all("label"):
        if keyword in label.get_text(strip=True).lower():
            target_id = label.get("for")
            if target_id:
                el = form.find(id=target_id)
                if el and el.get("name"):
                    return el["name"]
    return None


def build_payload(form, cfg: dict) -> dict:
    """Seed the payload with every existing field value, then overlay ours."""
    payload = {}

    # seed with existing values
    for el in form.find_all(["input", "textarea"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "textarea":
            payload[name] = el.get_text() or ""
        elif el.get("type") == "checkbox":
            # tick data policy
            payload[name] = el.get("value") or "on"
        else:
            payload[name] = el.get("value", "")

    # Overlay your details, matched by label text.
    for key, keyword in KEY_TO_LABEL.items():
        name = field_name_for_label(form, keyword)
        if name is None:
            print(f"  ! Could not find a field for '{keyword}' — skipping.")
            continue
        payload[name] = cfg.get(key, "")

    return payload


def main():
    cfg = load_config()

    date = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else next_quiz_date()
    url = URL_TMPL.format(date=date.isoformat())
    print(f"Quiz date : {date:%A %d %B %Y}")
    print(f"Event URL : {url}")

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (pub-quiz-registration-script)"

    # Fetch the live form
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if form is None:
        sys.exit("! No <form> found on the page — the URL or page layout changed.")

    payload = build_payload(form, cfg)
    action = urljoin(url, form.get("action") or url)
    method = (form.get("method") or "get").lower()

    print("\nSubmitting:")
    for k, v in payload.items():
        print(f"  {k} = {v!r}")

    # Submit using the form's own method.
    if method == "post":
        result = session.post(action, data=payload, timeout=30)
    else:
        result = session.get(action, params=payload, timeout=30)
    result.raise_for_status()

    # verify manually first check
    text = result.text.lower()
    good = "thank" in text or "success" in text or "confirm" in text
    bad = "error" in text or "required" in text

    print(f"\nHTTP {result.status_code}  ->  {result.url}")
    if good and not bad:
        print("--> Looks like the registration went through.")
    else:
        print(
            "!! Couldn't confirm success from the response. Verify manually!"
        )


if __name__ == "__main__":
    main()
