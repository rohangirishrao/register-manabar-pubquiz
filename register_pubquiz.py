#!/usr/bin/env python3
"""
Auto-register for the ManaBar Pub Quiz.
"""

import sys
import json
import time
import datetime as dt
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# site details, never changes
BASE_URL = "https://manabar.ch"
URL_TMPL = BASE_URL + "/en/event/weekly-pub-quiz-{date}"  # {date} = YYYY-MM-DD
DIRECTUS_URL = "https://directus.manabar.ch"
EVENTS_URL = DIRECTUS_URL + "/items/events"
SUBMIT_URL = DIRECTUS_URL + "/items/form_submissions"
QUIZ_WEEKDAY = 2  # Monday=0 ... Wednesday=2
CONFIG_FILE = Path(__file__).with_name("config.json")

# How long to keep waiting for the form to go live (registration opens ~noon).
RETRY_INTERVAL = 5     # seconds between checks
RETRY_MAX_WAIT = 600   # give up after 10 minutes

KEY_TO_LABEL = {
    "email": "email",
    "team": "team",
    "group_size": "group size",
    "message": "message",
    "name": "name",
}
REQUIRED_KEYS = ["name", "email", "team", "group_size"]


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


def fetch_form_id(session: requests.Session, slug: str):
    """Look up the event's form id in Directus (it changes every week).

    Each event has a `content` list; the registration form is the entry whose
    collection is "form". This is the same public read the site itself does.
    Returns None if the event or its form isn't there (yet).
    """
    resp = session.get(
        EVENTS_URL,
        params={
            "filter[slug][_eq]": slug,
            "fields": "content.collection,content.item",
        },
        timeout=30,
    )
    resp.raise_for_status()
    events = resp.json().get("data") or []
    if not events:
        return None
    for block in events[0].get("content") or []:
        if block.get("collection") == "form":
            return int(block["item"])
    return None


def wait_for_form(session: requests.Session, url: str, slug: str):
    """Poll until the registration form is live, then return (form, form_id).

    Registration opens around Monday noon, so the page can exist a few seconds
    before the form does. We keep checking every RETRY_INTERVAL seconds for up
    to RETRY_MAX_WAIT seconds, and give up after that.
    """
    deadline = time.monotonic() + RETRY_MAX_WAIT
    attempt = 0
    while True:
        attempt += 1
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        try:
            resp = session.get(url, timeout=30, headers={"Cache-Control": "no-cache"})
            resp.raise_for_status()
            form = BeautifulSoup(resp.text, "html.parser").find("form")
            form_id = fetch_form_id(session, slug) if form is not None else None
            if form is not None and form_id is not None:
                print(f"[{stamp}] attempt {attempt}: form is live", flush=True)
                return form, form_id
            reason = "no form on page" if form is None else "form id not in Directus"
        except requests.RequestException as exc:
            reason = f"request failed ({exc.__class__.__name__})"

        if time.monotonic() >= deadline:
            sys.exit(f"[{stamp}] ! Gave up after {attempt} attempts: {reason}.")
        print(f"[{stamp}] attempt {attempt}: {reason}, retrying in "
              f"{RETRY_INTERVAL}s", flush=True)
        time.sleep(RETRY_INTERVAL)


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
    slug = f"weekly-pub-quiz-{date.isoformat()}"
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

    # Wait until registration is open, then read this week's form field ids.
    form, form_id = wait_for_form(session, url, slug)
    print(f"Form id   : {form_id}")

    payload = {
        "form": form_id,
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
