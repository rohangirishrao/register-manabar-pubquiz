# register-manabar-pubquiz

Quick script to register for [ManaBar](https://manabar.ch/en)'s weekly pub quiz automatically.

URL changes each week, so the script takes care of this.

## Setup

Clone the repo. Fill in your details in `config.example.json` and rename it to `config.json`.

```bash
pip install requests beautifulsoup4
```

## Usage

```bash
python register_pubquiz.py                # next Wednesday
python register_pubquiz.py 2026-09-16     # a specific quiz date
```

Failures will be shown in console.