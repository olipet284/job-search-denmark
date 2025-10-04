# Job Search Denmark

A minimal, single-user Flask + pand./run_review.sh
```

You'll see output like:

```text
[auto] Selected free port 51287
[start] PID 70823 (port 51287)
Visit: http://127.0.0.1:51287
```

Then open the displayed URL (auto-open may occur on some systems).cation for efficiently reviewing, annotating, filtering and tracking job postings stored in a CSV. Includes simple web scraping utilities for LinkedIn, Jobnet, and JobIndex (Denmark-specific).

## Key Features

- CSV‑backed data store with automatic timestamped backups (`_backups/`).
- Inline editing of core job metadata (company, title, url, location, etc.).
- Unified decision workflow: `apply`, `reject`, `later`, or pending (empty).
- Smart filters: `pending`, `missing_desc`, `reject`, `to_apply` (apply but no applied_date), `applied`, `all`.
- Conditional application workspace fields (only in `to_apply` / `applied`): `cover_letter`, `cv`.
- Debounced auto-save of edits (in-memory) + explicit “Save CSV” to persist to disk.
- Safe shutdown trigger when closing the browser tab if no unsaved edits.
- Fullscreen list / table modal with:
  - Dynamic columns (all fields) and 60‑character previews for large text: `description`, `cover_letter`, `cv`, `decision_reason`, `url`.
  - Sorting on any column (toggle ascending / descending via header icon).
  - Row selection to jump directly to a record.
- Quick-set 📅 button (in `to_apply` filter) to insert today’s date into `applied_date`.
- Automatic port selection + start/stop/status helper script.
- Dark / Light adaptive theme (follows system preference) with minimalistic styling.

## Project Layout

```text
review_app.py      # Flask application + API endpoints
util.py            # Scraper functions (LinkedIn / Jobnet / Jobindex)
main.ipynb         # Sandbox notebook for running scrapers + merging results
templates/
  index.html       # Single-page UI shell
static/
  theme.css        # Custom adaptive theme
install.sh         # One-time environment setup (venv + requirements)
run_review.sh      # Launch / stop / status helper
requirements.txt   # Python dependencies
_backups/          # Timestamped CSV snapshots (auto-created)
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
| decision | apply / reject / later / (empty) |
| decision_reason | Optional short rationale |
| cover_letter | Draft or tailored cover letter (only visible in certain filters) |
| cv | Notes or modified CV content |
| last_updated | Auto ISO timestamp of last edit |
| __row_id | Internal stable row identifier (not written back to CSV) |

Additional columns present in `jobs.csv` are preserved and surfaced automatically in the list view.

## Filters Explained

- `pending`: undecided or `later` items.
- `missing_desc`: description empty or null.
- `reject`: explicitly rejected.
- `to_apply`: decision == apply but `applied_date` empty.
- `applied`: rows with a non-empty `applied_date`.
- `all`: everything.

Changing a filter automatically attempts to load the first matching row; if no rows, it reverts to the previous filter.

## Editing & Saving Lifecycle

1. Editing fields triggers a debounced in-memory save via `/api/job/<id>` (not persisted to disk immediately).
2. “Save CSV” (or server shutdown with no unsaved edits) calls `/api/save` to write an atomic CSV and create a timestamped backup.
3. Unsaved state is reflected in the status bar: `(unsaved edits)`.

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
| `linkedin_scraper(title, city, num_jobs)` | LinkedIn (guest endpoints) | title, city, num_jobs | Iteratively fetches job IDs then details; populates company, title, location, description (clamped), applicants, seniority. Time parsing omits weeks/months for now. |
| `jobnet_scraper(title, city, postal, km_dist, num_jobs)` | jobnet.dk | title, city, postal, km_dist, num_jobs | Uses JSON search API; pulls employment type and full/part time; fetches description for internal postings. |
| `jobindex_scraper(title, city, postal, street, km_dist, num_jobs)` | jobindex.dk | title, city, postal, street, km_dist, num_jobs | Paginates via API; fetches HTML for local listings; deduplicates via DataFrame drop_duplicates. |

All scrapers are MVPs and thus should be further extended to ensure all relevant information is gathered.

**Note**: Scrapers may break if site structures change.

### Sandbox Notebook (`main.ipynb`)

Used as an experimental workspace to:
 
1. Run one or more scrapers with chosen parameters.
2. Concatenate results and align columns with existing `jobs.csv` (or create if non-existing)
3. Append or merge into the current CSV (preserving existing decisions / notes by joining on URL or title+company heuristic).
 
Then launch the review UI to process the new inflow.

## Roadmap

1. Pruning backups
2. Improving scrapers
3. Improve UI
