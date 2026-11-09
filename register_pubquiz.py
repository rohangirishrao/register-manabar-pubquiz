#!/usr/bin/env python3
"""
Auto-register for the ManaBar Pub Quiz.

Reads the event's registration form from Directus (the CMS behind manabar.ch)
and submits your details from config.json, the same way the website does.
"""

import sys
import json
import time
import datetime as dt
from pathlib import Path

import requests

BASE_URL = "https://manabar.ch"
DIRECTUS_URL = "https://directus.manabar.ch"
EVENTS_URL = DIRECTUS_URL + "/items/events"
SUBMIT_URL = DIRECTUS_URL + "/items/form_submissions"
QUIZ_WEEKDAY = 2  # Monday=0 ... Wednesday=2
LANGUAGE = "en"
CONFIG_FILE = Path(__file__).with_name("config.json")

# How long to keep waiting for the form to go live (registration opens ~noon).
RETRY_INTERVAL = 5     # seconds between checks
RETRY_MAX_WAIT = 600   # give up after 10 minutes

# Directus field name -> key in config.json
FIELD_TO_CONFIG = {
    "name": "name",
    "email": "email",
    "team_name": "team",
    "amount_people": "group_size",
    "message": "message",
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


def fetch_form(session: requests.Session, slug: str):
    """Return (form_id, fields) for the event, or None if there's no form yet.

    Each event has a `content` list; the registration form is the entry whose
    collection is "form". Its fields are stored per language in `translations`.
    """
    resp = session.get(
        EVENTS_URL,
        params={
            "filter[slug][_eq]": slug,
            "fields": "content.collection,content.item.id,"
                      "content.item.translations.languages_code,"
                      "content.item.translations.fields.*",
        },
        timeout=30,
    )
    resp.raise_for_status()
    events = resp.json().get("data") or []
    if not events:
        return None

    for block in events[0].get("content") or []:
        if block.get("collection") != "form":
            continue
        translations = block["item"].get("translations") or []
        for translation in translations:
            if translation.get("languages_code", "").startswith(LANGUAGE):
                if translation.get("fields"):
                    return block["item"]["id"], translation["fields"]
    return None


def wait_for_form(session: requests.Session, slug: str):
    """Poll Directus until the registration form exists, then return it.

    Checks every RETRY_INTERVAL seconds for up to RETRY_MAX_WAIT seconds.
    """
    deadline = time.monotonic() + RETRY_MAX_WAIT
    attempt = 0
    while True:
        attempt += 1
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        try:
            form = fetch_form(session, slug)
            if form is not None:
                print(f"[{stamp}] attempt {attempt}: form is live", flush=True)
                return form
            reason = "no form for this event yet"
        except requests.RequestException as exc:
            reason = f"request failed ({exc.__class__.__name__})"

        if time.monotonic() >= deadline:
            sys.exit(f"[{stamp}] ! Gave up after {attempt} attempts: {reason}.")
        print(f"[{stamp}] attempt {attempt}: {reason}, retrying in "
              f"{RETRY_INTERVAL}s", flush=True)
        time.sleep(RETRY_INTERVAL)


def build_answers(fields: list, cfg: dict, date: dt.date) -> list:
    """Pair each form field with its value, like the website's form does."""
    answers = []
    for field in fields:
        if field.get("type") == "hidden":
            # The website fills "{{date}}" with the event date.
            value = (field.get("value") or "").replace("{{date}}", date.isoformat())
        elif field.get("name") in FIELD_TO_CONFIG:
            value = cfg.get(FIELD_TO_CONFIG[field["name"]], "")
        else:
            print(f"  ! Field {field.get('name')!r} has no config mapping — sending empty.")
            value = ""
        answers.append({"field": str(field["id"]), "value": value})
    return answers


def main():
    cfg = load_config()

    date = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else next_quiz_date()
    slug = f"weekly-pub-quiz-{date.isoformat()}"
    print(f"Quiz date : {date:%A %d %B %Y}")
    print(f"Event URL : {BASE_URL}/{LANGUAGE}/event/{slug}")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (pub-quiz-registration-script)",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/",
        }
    )

    form_id, fields = wait_for_form(session, slug)
    print(f"Form id   : {form_id}")

    payload = {
        "form": form_id,
        "answers": build_answers(fields, cfg, date),
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
