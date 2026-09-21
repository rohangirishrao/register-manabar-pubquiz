#!/usr/bin/env python3
"""
Auto-register for the ManaBar Pub Quiz.

Your details live in config.json (git-ignored). Copy config.example.json to
config.json and fill it in.

Requirements:
    pip install requests beautifulsoup4

Usage:
    python register_pubquiz.py                # next Wednesday
    python register_pubquiz.py 2026-09-23     # a specific quiz date
"""

import sys
import json
import datetime as dt
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# site details, never changes
BASE_URL = "https://manabar.ch"
URL_TMPL = BASE_URL + "/en/event/weekly-pub-quiz-{date}"  # {date} = YYYY-MM-DD
SUBMIT_URL = "https://directus.manabar.ch/items/form_submissions"
QUIZ_WEEKDAY = 2  # Monday=0 ... Wednesday=2
CONFIG_FILE = Path(__file__).with_name("config.json")

KEY_TO_LABEL = {
    "email": "email",
    "team": "team",
    "group_size": "group size",
    "message": "message",
    "name": "name",
}
REQUIRED_KEYS = ["name", "email", "team", "group_size", "form_id"]


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        sys.exit(
            f"! {CONFIG_FILE.name} not found. Copy config.example.json to "
            f"config.json and fill it in."
        )
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


def config_key_for_label(label_text: str):
    """Return the config key whose keyword appears in this label's text."""
    text = label_text.strip().lower()
    for key, keyword in KEY_TO_LABEL.items():
        if keyword in text:
            return key
    return None


def build_answers(form, cfg: dict) -> list:
    """Read the weekly field ids from the form and pair them with the values."""
    # Map field id -> label text, from <label for="ID">.
    id_to_label = {
        lbl.get("for"): lbl.get_text(strip=True)
        for lbl in form.find_all("label")
        if lbl.get("for")
    }

    answers = []
    for el in form.find_all(["input", "textarea"]):
        fid = el.get("name")
        if not fid or fid == "data_policy":
            continue
        if el.get("type") in ("submit", "button"):
            continue

        if el.get("type") == "hidden":
            value = el.get("value", "")  # e.g. the event date
        else:
            key = config_key_for_label(id_to_label.get(fid, ""))
            if key is None:
                print(
                    f"  ! Field {fid} (label {id_to_label.get(fid)!r}) has no "
                    f"config mapping — sending empty."
                )
                value = ""
            else:
                value = cfg.get(key, "")
        answers.append({"field": fid, "value": value})

    return answers


def main():
    cfg = load_config()

    date = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else next_quiz_date()
    url = URL_TMPL.format(date=date.isoformat())
    print(f"Quiz date : {date:%A %d %B %Y}")
    print(f"Event URL : {url}")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (pub-quiz-registration-script)",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/",
        }
    )

    # Fetch the live page and read this week's form field ids.
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    form = BeautifulSoup(resp.text, "html.parser").find("form")
    if form is None:
        sys.exit("! No <form> found on the page — the URL or page layout changed.")

    payload = {
        "form": cfg["form_id"],
        "answers": build_answers(form, cfg),
        "data_policy": True,
    }

    print("\nSubmitting to Directus:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    result = session.post(SUBMIT_URL, json=payload, timeout=30)

    print(f"\nHTTP {result.status_code}")
    if result.status_code == 204:
        print("--> Success. You're registered.")
    else:
        print("!! Unexpected response — registration may NOT have gone through.")
        print(result.text[:500])


if __name__ == "__main__":
    main()
