from util import linkedin_scraper, jobnet_scraper, jobindex_scraper, auto_reject_jobs
import pandas as pd
import warnings
warnings.filterwarnings(
    "ignore",
    message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated",
    category=FutureWarning,
    module="pandas.core.reshape.concat"
)
import os, json
from pathlib import Path
from datetime import datetime, timezone
from config_loader import get_scrape_params, get_titles_list

STATE_FILE = Path('.last_scrape.json')  # maintained by daily_update.py
cutoff_dt = None
if STATE_FILE.exists():
    try:
        data = json.loads(STATE_FILE.read_text())
        last_date_str = data.get('last_date')
        if last_date_str:
            cutoff_dt = datetime.strptime(last_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"[update] Warning: could not parse last scrape date ({e})")

# Load existing file early for early-termination key set
existing_df = None
if os.path.exists("jobs.csv"):
    try:
        existing_df = pd.read_csv("jobs.csv")
    except Exception as e:
        print(f"[update] Warning: failed reading existing jobs.csv ({e}); proceeding with only new scrape data")
if existing_df is None:
    existing_df = pd.DataFrame(columns=["company","title"])  # minimal schema if first run

existing_keys = set(zip(existing_df.get('company', []), existing_df.get('title', [])))
# Track how many pending (undecided) rows existed before this scrape run
if 'decision' not in existing_df.columns:
    existing_df['decision'] = None
_existing_pending_mask = existing_df['decision'].isna() | (existing_df['decision'] == '')
old_pending_count = int(_existing_pending_mask.sum())
print(f"[update] Pending decisions before scrape: {old_pending_count}")
# Extract existing LinkedIn job ids from URL pattern (heuristic)
existing_linkedin_ids = set()
if 'url' in existing_df.columns:
    for u in existing_df['url'].dropna():
        if 'linkedin.com' in u and '/jobPosting/' in u:
            try:
                existing_linkedin_ids.add(u.rstrip('/').split('/')[-1])
            except Exception:
                pass
title, city, postal, street, num_jobs, km_dist = get_scrape_params()
titles_list = get_titles_list()
print(f"[update] Starting scrape for titles={titles_list} city='{city}' target_per_title={num_jobs} existing_unique_keys={len(existing_keys)} cutoff={(cutoff_dt.isoformat() if cutoff_dt else 'none')}")

all_linkedin = []
all_jobnet = []
all_jobindex = []

for t in titles_list:
    print(f"[update] -- Scraping title variant: {t}")
    # Scrape per title; each scraper returns rows; we deduplicate within its own results later
    ldf = linkedin_scraper(t, city, num_jobs, existing_ids=existing_linkedin_ids)
    all_linkedin.append(ldf)
    jndf = jobnet_scraper(t, city, postal, km_dist, num_jobs, existing_keys=existing_keys, cutoff_dt=cutoff_dt)
    all_jobnet.append(jndf)
    jxdf = jobindex_scraper(t, city, postal, street, km_dist, num_jobs, existing_keys=existing_keys, cutoff_dt=cutoff_dt)
    all_jobindex.append(jxdf)

# Concatenate per-source and drop duplicate (company,title) within each source to avoid repeats across titles
def _dedup_source(frames, source_name):
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    cat = pd.concat(frames, ignore_index=True)
    before = len(cat)
    if 'company' in cat.columns and 'title' in cat.columns:
        cat = cat.drop_duplicates(subset=['company','title'])
    after = len(cat)
    if after < before:
        print(f"[update] {source_name}: removed {before-after} intra-source duplicate rows (company,title) across multiple titles")
    return cat

linkedin_df = _dedup_source(all_linkedin, 'LinkedIn')
jobnet_df = _dedup_source(all_jobnet, 'Jobnet')
jobindex_df = _dedup_source(all_jobindex, 'Jobindex')

print(f"[update] Source counts (post multi-title merge): linkedin={len(linkedin_df)} jobnet={len(jobnet_df)} jobindex={len(jobindex_df)}")

df = pd.concat([linkedin_df, jobnet_df, jobindex_df], ignore_index=True)
# Ensure required decision-related columns are present before auto-reject
for c in ["decision","decision_reason"]:
    if c not in df.columns:
        df[c] = None

# Apply auto-reject only to rows that currently have no decision (so we don't overwrite)
try:
    pre_reject_pending = df['decision'].isna() | (df['decision'] == '')
    # Work on a view of pending subset to avoid touching pre-labeled rows
    pending_idx = df[pre_reject_pending].index
    auto_reject_count = 0  # number auto-rejected this run
    if len(pending_idx) > 0:
        sub = df.loc[pending_idx].copy()
        sub = auto_reject_jobs(sub)
        # Only propagate rows where decision was actually set to 'reject'
        changed = sub[sub['decision'] == 'reject']
        if not changed.empty:
            df.loc[changed.index, 'decision'] = changed['decision']
            df.loc[changed.index, 'decision_reason'] = changed['decision_reason']
            auto_reject_count = len(changed)
            print(f"[update] Auto-reject applied to {auto_reject_count} newly scraped rows")
except Exception as e:
    print(f"[update] Warning: auto-reject step failed ({e})")
    auto_reject_count = 0
for c in ["applied_date","reply","cover_letter","decision","decision_reason","last_updated","cv"]:
    if c not in df.columns:
        df[c] = None
df  # no-op

if not os.path.exists("jobs.csv"):
    # create initial file with full schema
    schema_df = df.copy().iloc[0:0]
    schema_df.to_csv("jobs.csv", index=False)
    existing_df = schema_df
    existing_keys = set()

# Determine new rows (before merging) based on company+title keys
pre_existing_keys = existing_keys
scrape_keys = list(zip(df.get('company', []), df.get('title', [])))
new_scrape_unique = sum(1 for k in scrape_keys if k not in pre_existing_keys)
print(f"[update] Unique new (company,title) pairs before merge: {new_scrape_unique}")
job_df = existing_df

df = pd.concat([df, job_df], ignore_index=True)

# --- Custom Deduplication Logic (approved rules) ---
# Rules:
# 1. If company+title+time_posted (non-null) identical, keep the existing (oldest) row only.
# 2. If time_posted is null for BOTH duplicates: keep all distinct (company,title,url) combos; only drop if URL also identical.
# 3. If one row has time_posted and the other doesn't: keep both.
# 4. If time_posted differs (both non-null): keep both (different snapshots / postings).

# Ensure required columns exist
for col in ['time_posted', 'url']:
    if col not in df.columns:
        df[col] = None
    if col not in job_df.columns:
        job_df[col] = None

# Tag provenance so existing rows (older) win on identical keys
df['__is_new'] = 1
job_df['__is_new'] = 0
merged_all = pd.concat([job_df, df[df['__is_new'] == 1]], ignore_index=True)

# Split by time_posted presence
non_null_tp = merged_all[merged_all['time_posted'].notna()].copy()
null_tp = merged_all[merged_all['time_posted'].isna()].copy()

# 1) Deduplicate non-null time_posted exact matches keeping existing first
non_null_tp.sort_values(by=['company','title','time_posted','__is_new'], ascending=[True,True,True,True], inplace=True)
non_null_tp = non_null_tp.drop_duplicates(subset=['company','title','time_posted'], keep='first')

# 2) For null time_posted rows: dedupe only if (company,title,url) identical (existing first)
null_tp.sort_values(by=['company','title','__is_new'], ascending=[True,True,True], inplace=True)
null_tp = null_tp.drop_duplicates(subset=['company','title','url'], keep='first')

# 3) Combine
deduped = pd.concat([non_null_tp, null_tp], ignore_index=True)
deduped.drop(columns=['__is_new'], inplace=True, errors='ignore')
df = deduped
# --- End Custom Deduplication Logic ---

after_keys = set(zip(df.get('company', []), df.get('title', [])))
final_unique_added = len(after_keys) - len(set(zip(job_df.get('company', []), job_df.get('title', []))))
print(f"[update] Final unique company/title count: {len(after_keys)} (added {final_unique_added} new unique pairs)")
# Pending delta reporting (after dedup & auto-reject)
try:
    if 'decision' not in df.columns:
        df['decision'] = None
    _new_pending_mask = df['decision'].isna() | (df['decision'] == '')
    new_pending_count = int(_new_pending_mask.sum())
    delta_pending = new_pending_count - old_pending_count
    delta_sign = '+' if delta_pending >= 0 else ''
    print(f"[update] Pending decisions after merge: {new_pending_count} (delta {delta_sign}{delta_pending})")
    # Provide a concise summary line for downstream tooling / logs
    print(f"[update] Summary: auto_rejected={auto_reject_count} newly_pending_added={max(delta_pending,0)}")
except Exception as e:
    print(f"[update] Warning: failed computing pending delta ({e})")
# Normalize date-like columns to YYYY-MM-DD (currently only time_posted from scrapers)
if 'time_posted' in df.columns:
    try:
        _dt_series = pd.to_datetime(df['time_posted'], errors='coerce', utc=True)
        df['time_posted'] = _dt_series.dt.strftime('%Y-%m-%d')
        # Replace NaT-derived 'NaT' strings with None
        df.loc[_dt_series.isna(), 'time_posted'] = None
    except Exception as e:
        print(f"[update] Warning: failed normalizing time_posted column ({e})")
print(f"[update] Writing jobs.csv with {len(df)} total rows (deduped).")
df.to_csv("jobs.csv", index=False)
print("[update] Done.")