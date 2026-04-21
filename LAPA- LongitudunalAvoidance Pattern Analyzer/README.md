# LAPA — Longitudinal Avoidance Pattern Analyzer

LAPA analyzes journal entries over time to surface **topic suppression**, **emotional flattening**, and an overall **avoidance score** for mental health decision support. This repository ships a Python analytics core, a Flask API, and an integrated mobile-style web shell.

## Features

- RoBERTa-based multilabel emotion modeling (GoEmotions mapping to six categories)
- BERTopic + UMAP + HDBSCAN topic discovery with six clinical domains
- Per-user baselines with exponential moving averages after the warm-up window
- Indicators: **Avoidance Score (AS)**, **Topic Suppression Index (TSI)**, **Emotional Variability Score (EVS)**
- Flask JSON API consumed by `frontend/lapa_mobile_app.html`
- Bootstrap clinical dashboard at `/dashboard/<user_id>`

## Requirements

- Python 3.9+
- Windows, macOS, or Linux
- GPU optional (CUDA used automatically when available)

## Setup

```bash
cd mental
python -m venv .venv
.\.venv\Scripts\activate        # Windows PowerShell
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

**Windows (Python 3.12):** older `hdbscan==0.8.33` builds from source and requires *Microsoft C++ Build Tools*. This repo pins `hdbscan==0.8.41` instead, which installs from a pre-built wheel. If you still see compile errors, upgrade pip: `python -m pip install -U pip`.

The first run downloads transformer weights (RoBERTa, optional `SamLowe/roberta-base-go_emotions` fallback) and sentence-transformers embeddings for BERTopic.

### Storage and authentication

- By default `storage.backend` is **sqlite** and all journal rows, weekly analytics, baselines, and accounts live in `data/processed/lapa.sqlite` (configurable).
- Set `storage.backend: json` to restore the earlier per-user JSON / JSONL files (no accounts API).
- Set `dashboard.require_auth: true` to require a **Bearer** token from `/api/v1/auth/login` for journal, insights, and chat routes (SQLite must be enabled).

### Optional remote chat (OpenAI-compatible)

Set environment variables before `python main.py --mode dashboard`:

- `LAPA_OPENAI_API_KEY` — API key (name overridden by `chat.api_key_env` in `config.yaml`).
- `LAPA_CHAT_API_BASE` — optional override, e.g. `https://api.openai.com/v1` or your proxy.

If the key or base URL is missing, `/api/v1/chat` returns supportive **local** fallback lines (no network call).

## Running

| Command | Purpose |
| --- | --- |
| `python main.py --mode train` | Fine-tune emotion head on GoEmotions (subset) and train/save BERTopic |
| `python main.py --mode evaluate` | DAIC-style sanity evaluation, baseline comparisons, plots under `evaluation/plots` |
| `python main.py --mode demo` | Terminal demo that ingests weekly text for a user |
| `python main.py --mode dashboard` | Starts Flask on `127.0.0.1:5000` (see `config/config.yaml`) |

### Web UI

1. Start the dashboard: `python main.py --mode dashboard`
2. Open `http://127.0.0.1:5000/` for the mobile shell (API injected automatically).
3. Open `http://127.0.0.1:5000/dashboard/demo_user` for the clinician dashboard.

### JSON API

- `POST /api/v1/entries` — body: `{ "user_id", "text", "date", "mood?", "topics?" }`
- `GET /api/v1/insights/<user_id>` — latest indicators + 8-week AS history
- `GET /api/v1/history/<user_id>` — longitudinal rows

Legacy route: `POST /submit_entry` (same payload).

## Tests

```bash
pytest -q
```

Heavy models are stubbed in `tests/test_pipeline.py` so CI machines are not required to download full checkpoints.

## Project layout

- `config/config.yaml` — all tunable parameters and filesystem roots
- `modules/` — preprocessing, emotion, topics, baselines, deviations, indicators
- `pipeline/` — orchestration + reporting
- `evaluation/` — benchmarks and plotting helpers
- `dashboard/` — Flask app + Bootstrap templates
- `frontend/lapa_mobile_app.html` — integrated mobile UI

## Disclaimer

LAPA outputs are **decision-support signals**, not diagnoses. Always interpret longitudinally and alongside qualified clinical judgment.
