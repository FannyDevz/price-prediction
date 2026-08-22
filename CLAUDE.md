# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Pipeline for collecting, storing, analyzing, and forecasting **rice (beras) prices** across cities in East Java (Jawa Timur), Indonesia. Data is scraped from the public SISKAPERBAPO API, stored in MySQL, aggregated to monthly series, forecasted with SES/DES exponential smoothing, and visualized in a Streamlit dashboard. Codebase comments, docstrings, and UI are primarily in **Indonesian**; match that language when editing user-facing strings and logs.

## Setup & Commands

Requires a running MySQL server. Configuration is read from a `.env` file at the repo root (loaded by `config/settings.py`):

```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=data_beras
DB_PORT=3308      # note: MAMP/XAMPP-style non-default ports are used here
APP_ENV=development
```

```bash
pip install -r requirements.txt          # deps (no venv is committed)
python -m database.migrations            # create DB + tables (idempotent)
python -m etl.run_etl                    # fetch/transform/load (defaults to today)
python -m streamlit run app/Home.py      # launch dashboard
python main.py                           # interactive text menu wrapping the steps above
```

`main.py` is a CLI menu that chains migration → fetch → monthly aggregation → CSV export.

### Running the forecast

```bash
python forcasting.py          # forecast+save ALL (kode_kota, tipe) combos to DB
python forcasting_single.py   # one hardcoded city/type, shows matplotlib plots (no DB write)
```

Note the filename is misspelled `forcasting` (not `forecasting`) — keep it when referencing.

### Tests

There is **no pytest suite wired up** (`tests/test_queries.py` is empty). `tests/testing/*.py` are standalone throwaway scripts that inline-copy functions (e.g. `_clean_harga`) rather than importing them — they are experiments, not a regression suite. `TEST & RUN.md` documents ad-hoc smoke-test one-liners, e.g.:

```bash
python -c "from etl.extract import extract_range; print(extract_range('2026-01-04','2026-01-04').head())"
python -c "from config.settings import debug; debug()"
```

Run any module-level entrypoint as a module (`python -m etl.run_etl`), not by path, so package imports resolve.

## Architecture

Data flows through three MySQL tables (defined in `database/migrations.py`), each with a UNIQUE key enabling idempotent upserts:

1. **`history_data_beras`** — raw daily prices per `(kode_kota, tipe, tanggal)`.
2. **`history_data_beras_monthly`** — monthly avg/min/max, aggregated by SQL `GROUP BY` in `etl/aggregate.py`.
3. **`forecast_harga_beras`** — SES/DES predictions + MAE/MAPE/RMSE per `(kode_kota, tipe, model, tanggal)`.

`tipe` is always `"premium"` or `"medium"` (mapped to API commodity codes 2 and 4 in `etl/extract.py`). `kode_kota` is the API's city code string (e.g. `"sampangkab"`).

### Pipeline stages

- **ETL** (`etl/`): `extract.py` scrapes `siskaperbapo.jatimprov.go.id` per date × tipe → `transform.py` cleans prices (`_clean_harga` strips `Rp`/dots, fills NaN with per-group daily mean) → `load.py` upserts via `ON DUPLICATE KEY UPDATE`. `run_etl.py` orchestrates (`run()` for a date range, `run_daily()` for one day); `aggregate.py` rolls daily → monthly entirely in SQL.
- **Forecast** (`forecast/`): `dataset.load_monthly_series()` pulls a monthly `pd.Series` (hardcoded window Jan 2023–Jun 2025) → `split.train_test_split_ts()` → `normalize.minmax_scale()` (**fit on train only**, transform test with train min/max) → `ses.py`/`des.py` wrap statsmodels `SimpleExpSmoothing`/`Holt` → `evaluate.py` computes MAE/MAPE/RMSE → `save.save_forecast_to_db()`. `auto_select.py` picks SES vs DES by lowest metric (default MAPE).
- **App** (`app/`): Streamlit multipage. `app/Home.py` is the entry; `app/pages/` are numbered pages (daily analytics, monthly aggregation, forecast, city comparison). `app/services/` and `app/components/` hold data access and UI helpers.
- **Analytics** (`analytics/`): read-only reporting split into `daily/` and `monthly/` submodules (`dataset`, `stats`, `change`, `plot`, `outlier`); `compare.py` for multi-city comparison.

### Cross-cutting conventions

- **DB access is uniform**: every module calls `database.connection.get_engine(DB_NAME)` (SQLAlchemy, `pool_pre_ping`). `get_engine()` with no arg connects without a database (used only to `CREATE DATABASE`). Queries use `sqlalchemy.text()` with **bound params** — follow this; do not string-format user values into SQL. `forecast/dataset.py` is the one place that concatenates a column name into SQL, and it guards with an `ALLOWED_COLS` whitelist — preserve that pattern for any dynamic column.
- **Logging**: use `from utils.logger import logger`; ETL steps log `... sukses/gagal | ...` lines to `logs/etl.log` (gitignored).
- **Normalization discipline**: scaling parameters must be fit on train data only, then reused for test and inverse-transform — the forecast scripts and the Streamlit forecast page all follow this, and metrics are reported in **scaled space**.
- Note `forcasting.py`, `forcasting_single.py`, and `app/pages/3_Forecast.py` duplicate much of the forecast flow. When changing forecast logic, check whether all three need the same edit.
