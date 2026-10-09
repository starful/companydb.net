# CompanyDB

English-readable public company filings for personal investors — **Japan (EDINET)**, **Korea (DART)**, and the **US (SEC EDGAR)**.

**Live:** [https://companydb.net](https://companydb.net)

## What it does

- Pulls annual / securities reports from EDINET, Open DART, and SEC
- Lays out statements, multi-year trends, and note-driven takeaways in English
- Serves static company pages plus an index and compare view on Cloud Run

Coverage grows from a seed universe plus `data/universe_extra.json` (ticker queue). Pages and logos live under `output/`.

## Stack

| Piece | Detail |
|-------|--------|
| Build | `script/build_company_page.py` |
| Web | Flask (`app/`) + gunicorn — static `output/` + reactions API |
| Deploy | Cloud Run via `cloudbuild.yaml` / `./deploy.sh` |
| Secrets | `.env` (see `.env.example`) — EDINET / Open DART keys |

## Quick start

```bash
cd companydb
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill EDINET_API_KEY, OPENDART_API_KEY
```

### Build pages

```bash
# Missing tickers in the universe (optional market caps)
python3 script/build_company_page.py --universe --jp-limit 5 --kr-limit 2 --us-limit 2

# Index + compare only
python3 script/build_company_page.py --index

# Company logos (writes output/assets/logos/, patches pages)
python3 script/build_company_page.py --logos

# Add a ticker to the queue (build separately with --universe)
python3 script/build_company_page.py --add 4661 --market JP --name "Oriental Land Co., Ltd."
```

### Run locally

```bash
python3 -m flask --app wsgi:app run --port 8080
# → http://127.0.0.1:8080
```

## Deploy

```bash
# Cloud Build → Cloud Run (current tree)
./deploy.sh --deploy-only --with-deploy

# Optional: commit/push generated output first
./deploy.sh --deploy-only --with-git --with-deploy
```

Defaults: project `starful-258005`, service `companydb`, region `us-central1`.

Custom domain: **companydb.net** (maps to the Cloud Run service).

## Repo layout

```
script/build_company_page.py   # filings → HTML + catalog + logos
data/catalog.json              # company index data
data/universe_extra.json       # Hub/CLI-added tickers
data/logo_domains.json         # ticker → logo domain overrides
output/companies/              # static company pages
output/assets/logos/           # cached company marks
app/                           # Flask app + reactions
deploy.sh / cloudbuild.yaml    # Cloud Run ship
```

## Ops notes

- Content generation is **CLI / scripts**, not the okadmin content pipeline.
- okadmin Work Hub can still manage **SEO · Git · Deploy** for this site (generation disabled).
- Never commit `.env`, `data/raw/`, or `data/facts/` (see `.gitignore`).

## License

Private / all rights reserved unless otherwise noted.
