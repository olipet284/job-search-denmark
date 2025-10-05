# Job Search Denmark

Single‑user Flask + pandas application for efficiently scraping, reviewing, annotating, filtering and tracking job postings in a CSV. Includes lightweight scrapers for LinkedIn, Jobnet, and Jobindex plus a streamlined review UI optimized for fast triage.

## Key Features

- CSV‑backed data store with two rotating backups (session + previous save).
- Inline editing of job metadata (company, title, url, location, etc.).
- Decision workflow: `apply`, `reject`, `delete` (or pending = empty). `delete` rows hidden everywhere except `all`.
- Fast triage: “Reject »” button in `pending` sets decision to reject and navigates to the next row.
- Permanent Delete button (with confirmation) to remove a row completely.
- Smart filters: `pending`, `missing_desc`, `reject`, `to_apply`, `applied`, `all`.
- Conditional fields (`cover_letter`, `cv`) only in `to_apply` / `applied`.
- Debounced auto-save (in-memory) + explicit Save CSV with unsaved indicator.
- Fullscreen sortable list modal (dynamic columns, truncated previews, tooltips).
- One‑click 📅 set `applied_date` to today (in `to_apply`).
- Scraper progress bars (tqdm) & early termination heuristics (Jobnet/Jobindex), safe LinkedIn pagination.
- LinkedIn only fetches details for new IDs; skips existing.
- `job_board` column for source identification.
- Normalized `time_posted` to `YYYY-MM-DD` during merge.
- Daily scrape guard ensures scraping at most once per day.
- Adaptive dark/light theme.

## Project Layout

```text
review_app.py      # Flask application + API endpoints
util.py            # Scraper functions
main.ipynb         # Sandbox notebook
templates/
  index.html       # Single-page UI shell
static/
  theme.css        # Custom adaptive theme
install.sh         # One-time environment setup (venv + requirements)
run_review.sh      # Launch / stop / status helper
requirements.txt   # Python dependencies
_backups/          # Two rotating backups (session + previous save)
daily_update.py    # Once-per-day scrape orchestrator
update.py          # Aggregates scrapes & merges/dedups with existing CSV
job_config.py      # Central scrape parameter config
```

## Prerequisites

- Python 3.11+ (pandas + Flask tested under 3.12)
- Bash shell (for helper scripts)

## Installation

Run once to create a virtual environment and install dependencies:

```bash
./install.sh
```

This will create `.venv/` locally. Re-run only if you change `requirements.txt`.

## Running

Start the web UI (auto-selects a free port):

```bash
./run_review.sh
```

You’ll see output like:

```
[auto] Selected free port 51287
[start] PID 70823 (port 51287)
Visit: http://127.0.0.1:51287
```

Then open the displayed URL (auto-open may occur on some systems).

### Stop / Status

```bash
./run_review.sh status
./run_review.sh stop
```

Stopping sends a signal to the stored PID; stale PID files are cleaned automatically.

## Data Model (Columns)

| Column | Purpose |
|--------|---------|
| company | Employer / organization name |
| title | Role title |
| url | Original posting link |
| location | Location text |
| description | Raw or edited job description text |
| time_posted | Original site’s posted date/time text |
| num_applicants | Parsed applicant count if available |
| seniority_level | Classification text |
| job_function | Job function(s) |
| industries | Industry tags |
| employment_type | (e.g., Contract / Permanent) |
| full_or_part_time | Full-time / Part-time indicator |
| applied_date | Date you applied (YYYY-MM-DD) |
| decision | apply / reject / delete / (empty pending) |
| job_board | Source (linkedin / jobnet / jobindex) |
| decision_reason | Optional short rationale |
| cover_letter | Draft or tailored cover letter (only visible in certain filters) |
| cv | Notes or modified CV content |
| last_updated | Auto ISO timestamp of last edit |
| __row_id | Internal stable row identifier (not written back to CSV) |

Additional columns are preserved automatically. `__row_id` is internal only (not written back).

## Filters Explained

- `pending`: decision empty (not apply/reject/delete)
- `missing_desc`: description empty or null
- `reject`: decision=reject
- `to_apply`: decision=apply & no `applied_date`
- `applied`: has `applied_date`
- `all`: every row (includes `delete`)

Rows with `delete` are excluded from all filters except `all`.

## Editing & Saving Lifecycle

1. Debounced in-memory updates as you type.
2. "Save CSV" writes atomically and updates the single previous-save backup.
3. Session startup creates (or refreshes) a session backup.
4. Unsaved indicator shown until persisted.

### Backup Strategy

| Type | When | Filename Pattern | Kept |
|------|------|------------------|------|
| Session | App start | `jobs_session_backup_YYYYMMDD_HHMMSS.csv` | 1 |
| Previous save | Each manual save | `jobs_prev_backup_YYYYMMDD_HHMMSS.csv` | 1 |

Old backups of the same type are removed; at most two backup files exist.

## List (Table) Modal

Open with the “List” button. Features:

- Fullscreen responsive overlay.
- Click a row to load it and close the modal.
- Column sorting (click sort icon: ↕ → ▲ → ▼).
- Long text columns truncated to 60 chars with full content in tooltip.

## Application Docs Section

Visible only under `to_apply` and `applied` filters. Use this space to tailor / capture application materials side by side with the job description.

## Theming

- Dark theme by default; auto-switches to light if system preference indicates.
- Manual override hooks available: add `body.light` or `body.dark` if you later implement a toggle.
- The theming is minimal and MVP as most of this repo.

## API Endpoints (Internal)

| Method | Path | Description |
|--------|------|-------------|
| GET | / | Main UI |
| GET | /api/filters | List filter names |
| GET | /api/stats | Aggregated counts |
| GET | /api/nav?dir=next&filter=... | Navigate (next/prev) within a filter set |
| GET | /api/job/\<id\> | Retrieve job row |
| POST | /api/job/\<id\> | Update (partial) row fields |
| POST | /api/decision/\<id\> | Shortcut decision update |
| POST | /api/save | Persist CSV + backup |
| GET | /api/list?filter=...&sort_col=..&sort_dir=asc\|desc | Full list snapshot for modal |
| POST | /api/shutdown | Graceful dev server shutdown |

### Scraper Utilities (`util.py`)

The file `util.py` contains three focused scraping helpers returning pandas DataFrames you can merge into `jobs.csv`:

| Function | Source | Key Parameters | Notes |
|----------|--------|----------------|-------|
| `linkedin_scraper(title, city, num_jobs, existing_ids)` | LinkedIn | title, city, num_jobs | Skips known IDs, paginates until target or no new IDs |
| `jobnet_scraper(title, city, postal, km_dist, num_jobs, existing_keys, cutoff_dt)` | Jobnet | title, city, postal, km_dist | Early stop on existing key or older than last scrape |
| `jobindex_scraper(title, city, postal, street, km_dist, num_jobs, existing_keys, cutoff_dt)` | Jobindex | title, city, postal, street, km_dist | Early stop + HTML detail parsing for local postings |

All inject `job_board`; dates normalized later in `update.py`.

All scrapers are MVPs and thus should be further extended to ensure all relevant information is gathered.

**Note**: Scrapers may break if site structures change.

### Sandbox Notebook (`main.ipynb`)

Used as an experimental workspace to:
 
1. Run one or more scrapers with chosen parameters.
2. Concatenate results and align columns with existing `jobs.csv` (or create if non-existing)
3. Append or merge into the current CSV (preserving existing decisions / notes by joining on URL or title+company heuristic).
 
Then launch the review UI to process the new inflow.

## Daily Scrape Guard

`daily_update.py` ensures `update.py` runs at most once per UTC day before launching the review server (`run_review.sh`).
