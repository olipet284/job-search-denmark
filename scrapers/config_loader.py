import configparser
from pathlib import Path
from functools import lru_cache
from typing import List, Tuple

# config.ini should be in the project root (parent of scrapers/ folder)
_CONFIG_PATH = Path(__file__).parent.parent / "config.ini"

@lru_cache(maxsize=1)
def _load() -> configparser.ConfigParser:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {_CONFIG_PATH}")
    
    parser = configparser.ConfigParser()
    try:
        parser.read(_CONFIG_PATH, encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to read config file {_CONFIG_PATH}: {e}")
    
    # Validate required sections exist
    if 'scrape' not in parser:
        raise ValueError(f"Missing [scrape] section in {_CONFIG_PATH}")
    if 'auto_reject' not in parser:
        raise ValueError(f"Missing [auto_reject] section in {_CONFIG_PATH}")
    
    return parser

@lru_cache(maxsize=1)
def get_scrape_params() -> Tuple[str,str,str,str,int,int]:
    cfg = _load()
    s = cfg["scrape"]
    
    # Validate required fields exist
    required_fields = ["city", "postal", "street", "num_jobs", "km_dist"]
    for field in required_fields:
        if field not in s:
            raise ValueError(f"Missing required field '{field}' in [scrape] section")
    
    try:
        num_jobs = int(s["num_jobs"])
    except ValueError:
        raise ValueError(f"Invalid num_jobs value: {s['num_jobs']} (must be integer)")
    
    try:
        km_dist = int(s["km_dist"])
    except ValueError:
        raise ValueError(f"Invalid km_dist value: {s['km_dist']} (must be integer)")
    
    return (
        s.get("title", ""),  # singular (legacy, optional)
        s["city"],
        s["postal"],
        s["street"],
        num_jobs,
        km_dist,
    )

@lru_cache(maxsize=1)
def get_titles_list() -> List[str]:
    cfg = _load()
    s = cfg["scrape"]
    
    # Check for titles field (preferred)
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
    
    # Fallback to single title (legacy)
    single = s.get("title", "").strip()
    if single:
        return [single]
    
    # No titles configured
    raise ValueError("No job titles configured. Set 'titles' or 'title' in [scrape] section")

@lru_cache(maxsize=1)
def get_title_keywords() -> List[str]:
    cfg = _load()
    
    # Require keywords field to exist
    if "keywords" not in cfg["auto_reject"]:
        raise ValueError("Missing required field 'keywords' in [auto_reject] section")
    
    raw = cfg["auto_reject"]["keywords"] or ""
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

@lru_cache(maxsize=1)
def get_notion_config() -> Tuple[str, str]:
    cfg = _load()
    
    # Require notion section and fields
    if 'notion' not in cfg:
        raise ValueError("Missing [notion] section in config")
    notion_cfg = cfg['notion']
    
    if 'notion_token' not in notion_cfg or 'notion_database_id' not in notion_cfg:
        raise ValueError("Missing 'notion_token' or 'notion_database_id' in [notion] section")
    
    notion_token = notion_cfg['notion_token'].strip()
    notion_database_id = notion_cfg['notion_database_id'].strip()
    
    if not notion_token or not notion_database_id:
        raise ValueError("'notion_token' and 'notion_database_id' must be non-empty in [notion] section")
    
    return notion_token, notion_database_id