# register-manabar-pubquiz

Quick script to register for [ManaBar](https://manabar.ch/en)'s weekly pub quiz automatically.

URL changes each week, so the script takes care of this.

## Setup

Clone the repo. Fill in your details in `config.example.json` and rename it to `config.json`.

The site posts registrations to its Directus CMS (`items/form_submissions`), so
the script does the same. Everything that changes weekly is detected
automatically: the form id is read from Directus (`items/events`, by slug) and
the field ids are scraped from the event page.

## Usage (recommended)

Install [pixi](https://pixi.prefix.dev/latest/).

Change directory to the repo.

```bash
pixi run python register_manabar_pubquiz.py # next Wednesday
pixi run python register_manabar_pubquiz.py 2026-09-30 # specific date
```

A successful submission returns HTTP 204. Failures are shown in the console.