# register-manabar-pubquiz

Quick script to register for [ManaBar](https://manabar.ch/en)'s weekly pub quiz automatically.

URL changes each week, so the script takes care of this.

## Setup

Clone the repo. Fill in your details in `config.example.json` and rename it to `config.json`.

```bash
pip install requests beautifulsoup4
```

The site posts registrations to its Directus CMS (`items/form_submissions`), so
the script does the same. The weekly field ids are scraped from the page
automatically; the one value you currently set yourself is `form_id` in
`config.json` (grab it from the submit request's payload in your browser's
Network tab — auto-detection is a TODO).

## Usage

```bash
python register_pubquiz.py                # next Wednesday
python register_pubquiz.py 2026-09-16     # a specific quiz date
```

A successful submission returns HTTP 204. Failures are shown in the console.