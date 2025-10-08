import configparser
from pathlib import Path
from functools import lru_cache
from typing import List, Tuple

_CONFIG_PATH = Path(__file__).parent / "config.ini"

DEFAULT_SCRAPE = {
    "title": "Data Scientist",
    "titles": "",
    "city": "Aarhus C",
    "postal": "8000",
    "street": "Ryesgade 1",
    "num_jobs": "50",
    "km_dist": "70",
}

DEFAULT_AUTO_REJECT = {
    "keywords": (
        "intern, internship, senior, sr., frontend, front-end, .net, pædagog, praktikant, "
        "vikar, android, postdoc, fullstack, full-stack, maternity"
    )
}

@lru_cache(maxsize=1)
def _load() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    # Preserve case where meaningful (although keys are usually lowercased); we keep defaults first
    parser.read_dict({"scrape": DEFAULT_SCRAPE, "auto_reject": DEFAULT_AUTO_REJECT})
    if _CONFIG_PATH.exists():
        try:
            parser.read(_CONFIG_PATH, encoding="utf-8")
        except Exception as e:
            print(f"[config] Warning: failed reading {_CONFIG_PATH}: {e}")
    else:
        print(f"[config] Info: config file {_CONFIG_PATH} not found; using defaults")
    return parser

@lru_cache(maxsize=1)
def get_scrape_params() -> Tuple[str,str,str,str,int,int]:
    cfg = _load()
    s = cfg["scrape"]
    try:
        num_jobs = int(s.get("num_jobs", DEFAULT_SCRAPE["num_jobs"]))
    except ValueError:
        num_jobs = int(DEFAULT_SCRAPE["num_jobs"])
    try:
        km_dist = int(s.get("km_dist", DEFAULT_SCRAPE["km_dist"]))
    except ValueError:
        km_dist = int(DEFAULT_SCRAPE["km_dist"])
    return (
        s.get("title", DEFAULT_SCRAPE["title"]),  # singular (legacy)
        s.get("city", DEFAULT_SCRAPE["city"]),
        s.get("postal", DEFAULT_SCRAPE["postal"]),
        s.get("street", DEFAULT_SCRAPE["street"]),
        num_jobs,
        km_dist,
    )

@lru_cache(maxsize=1)
def get_titles_list() -> List[str]:
    cfg = _load()
    s = cfg["scrape"]
    raw_multi = s.get("titles", "").strip()
    if raw_multi:
        parts = [p.strip() for p in raw_multi.split(',') if p.strip()]
        # Deduplicate while preserving order
        seen = set()
        uniq = []
        for t in parts:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                uniq.append(t)
        return uniq
    # Fallback to single title
    single = s.get("title", DEFAULT_SCRAPE["title"]).strip()
    return [single] if single else []

@lru_cache(maxsize=1)
def get_title_keywords() -> List[str]:
    cfg = _load()
    raw = cfg["auto_reject"].get("keywords", DEFAULT_AUTO_REJECT["keywords"]) or ""
    # Split on commas, strip whitespace, keep non-empty
    kws = [k.strip() for k in raw.split(',') if k.strip()]
    # Deduplicate preserving order
    seen = set()
    uniq = []
    for k in kws:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            uniq.append(k)
    return uniq
