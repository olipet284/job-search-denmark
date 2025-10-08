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
    if len(pending_idx) > 0:
        sub = df.loc[pending_idx].copy()
        sub = auto_reject_jobs(sub)
        # Only propagate rows where decision was actually set to 'reject'
        changed = sub[sub['decision'] == 'reject']
        if not changed.empty:
            df.loc[changed.index, 'decision'] = changed['decision']
            df.loc[changed.index, 'decision_reason'] = changed['decision_reason']
            print(f"[update] Auto-reject applied to {len(changed)} newly scraped rows")
except Exception as e:
    print(f"[update] Warning: auto-reject step failed ({e})")
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
len_before = len(df)
df_dups = df[df.duplicated(subset=['company', 'title'], keep=False)].sort_values(by=['company', 'title'])
# when dropping duplicates, some of the information might be lost, e.g. if one row has a non-null description but the other has null
# we want to keep the non-null description
# so we can use groupby with agg to keep the first non-null value for each column
dedup_keys = ['company', 'title']
agg_funcs = {col: 'first' for col in df.columns if col not in dedup_keys}
if 'cover_letter' in df.columns:
    agg_funcs['cover_letter'] = lambda s: s.dropna().iloc[0] if s.notna().any() else None
if dedup_keys and agg_funcs:
    df = (
        df.groupby(dedup_keys, as_index=False)
        .agg(agg_funcs))
elif dedup_keys: # fallback if no agg_funcs defined
    df = df.groupby(dedup_keys, as_index=False).first()
len_after = len(df)
#if len_before != len_after:
#    print(f"Removed {len_before-len_after} duplicate rows, {len_before} -> {len_after}")
    
# Print out any duplicates that were found to double check that they were handled correctly
#df_dups

# Show the resulting rows that will be kept from the duplicates
df_dups_new = []
if len(df_dups) > 0:
    df_dups_list = df_dups[['company', 'title']].drop_duplicates().values.tolist()
    for company, title in df_dups_list:
        df_dups_new.append(df[(df['company'] == company) & (df['title'] == title)])
    # Only concat if we actually accumulated frames
    if df_dups_new:
        _preview_dups = pd.concat(df_dups_new, ignore_index=True)
        # Optionally could print(_preview_dups.head()) for debugging

after_keys = set(zip(df.get('company', []), df.get('title', [])))
final_unique_added = len(after_keys) - len(set(zip(job_df.get('company', []), job_df.get('title', []))))
print(f"[update] Final unique company/title count: {len(after_keys)} (added {final_unique_added} new unique pairs)")
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