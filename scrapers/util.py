import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Set, Tuple
from config_loader import get_title_keywords
title_keywords = get_title_keywords()


# Progress bar support (tqdm) with graceful fallback if not installed yet.
try:
    from tqdm import tqdm  # type: ignore
except Exception:  # pragma: no cover - fallback
    def tqdm(iterable=None, total=None, desc=None, unit=None):
        # Minimal no-op shim so code still runs without tqdm
        if iterable is None:
            class _Dummy:
                def update(self, n=1):
                    pass
                def close(self):
                    pass
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc, tb):
                    pass
            return _Dummy()
        return iterable

def linkedin_scraper(title, city, num_jobs, existing_ids: Optional[Set[str]] = None):
    """Scrape LinkedIn job listings with early termination.

    Only fetch details for newly discovered job ids (sorted newest-first fetch assumed).
    """
    print(f"[scrape] LinkedIn: starting collection for title='{title}' city='{city}' target={num_jobs}")
    if existing_ids is None:
        existing_ids = set()
    id_list: list[str] = []  # only NEW ids collected
    raw_offset = 0            # tracks how many listings we've paged through (new + existing)
    with tqdm(total=num_jobs, desc="LinkedIn ids", unit="job") as pbar:
        while len(id_list) < num_jobs:
            list_url = (
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
                f"keywords={'%20'.join(title.split(' '))}&location=&location={'%20'.join(city.split(' '))}%2C%20Denmark&start={raw_offset}"
            )
            response = requests.get(list_url)
            if response.status_code != 200:
                print(f"[scrape] LinkedIn: HTTP {response.status_code}; stopping pagination")
                break
            list_soup = BeautifulSoup(response.text, 'html.parser')
            page_jobs = list_soup.find_all('li')
            if not page_jobs:
                # No further pages
                break
            new_this_page = 0
            for job in page_jobs:
                base_card_div = job.find("div", {"class": "base-card"})
                if not base_card_div:
                    continue
                job_id = base_card_div.get("data-entity-urn", "::0").split(":")[-1]
                if not job_id:
                    continue
                if job_id in existing_ids or job_id in id_list:
                    # Skip known/existing ids but keep scanning
                    continue
                id_list.append(job_id)
                new_this_page += 1
                if len(id_list) <= num_jobs:
                    pbar.update(1)
                if len(id_list) >= num_jobs:
                    break
            raw_offset += len(page_jobs)  # advance offset by total seen on this page
            # Removed early stopping heuristic to allow deeper pagination even if a page yields no new ids
    print(f"[scrape] LinkedIn: collected {len(id_list)} new ids (target {num_jobs}).")
    job_list = []
    fetch_ids = [i for i in id_list if i not in existing_ids]
    if fetch_ids:
        for job_id in tqdm(fetch_ids, desc="LinkedIn details", unit="job"):
            job_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
            job_response = requests.get(job_url)
            job_soup = BeautifulSoup(job_response.text, 'html.parser')
            job_post = {"url": job_url}
            try:
                job_post["title"] = job_soup.find("h2", {"class": "top-card-layout__title font-sans text-lg papabear:text-xl font-bold leading-open text-color-text mb-0 topcard__title"}).text.strip()
            except:
                job_post["title"] = None
            try:
                job_post["company"] = job_soup.find("a", {"class": "topcard__org-name-link topcard__flavor--black-link"}).text.strip()
            except:
                job_post["company"] = None
            try:
                job_post["location"] = job_soup.find("span", {"class": "topcard__flavor topcard__flavor--bullet"}).text.strip()
            except:
                job_post["location"] = None
            try:
                desc_div = job_soup.find("div", {"class": "show-more-less-html__markup show-more-less-html__markup--clamp-after-5 relative overflow-hidden"})
                job_post["description"] = desc_div.get_text("\n", strip=True)
            except:
                job_post["description"] = None
            job_post["deadline"] = None  # LinkedIn does not provide application deadlines, could be scraped from description if needed
            try:
                date_str = job_soup.find("span", {"class": "posted-time-ago__text topcard__flavor--metadata"}).text.strip()
                if any(k in date_str for k in ("week","month","year")):
                    job_post["time_posted"] = None
                else:
                    parts = date_str.split()
                    if len(parts) >= 2:
                        time_value, time_unit = parts[0], parts[1]
                        if time_unit.startswith("day"):
                            delta = timedelta(days=int(time_value))
                        elif time_unit.startswith("hour"):
                            delta = timedelta(hours=int(time_value))
                        else:
                            delta = timedelta(0)
                        job_post["time_posted"] = datetime.now() - delta
                    else:
                        job_post["time_posted"] = None
            except:
                job_post["time_posted"] = None
            try:
                job_post["num_applicants"] = int(job_soup.find("span", {"class": "num-applicants__caption topcard__flavor--metadata topcard__flavor--bullet"}).text.strip().split()[0])
            except:
                job_post["num_applicants"] = None
            try:
                job_post["seniority_level"] = job_soup.find("span", {"class": "description__job-criteria-text description__job-criteria-text--criteria"}).text.strip()
            except:
                job_post["seniority_level"] = None
            try:
                info_type = job_soup.findAll("h3", {"class": "description__job-criteria-subheader"})
                info_type = [info.text.strip().lower().replace(' ', '_') for info in info_type]
                info_value = job_soup.findAll("span", {"class": "description__job-criteria-text description__job-criteria-text--criteria"})
                info_value = [info.text.strip() for info in info_value]
                job_post.update(dict(zip(info_type, info_value)))
            except:
                pass
            job_list.append(job_post)
    else:
        print("[scrape] LinkedIn: no new ids to fetch details for.")
    df = pd.DataFrame(job_list)
    if not df.empty:
        df['job_board'] = 'linkedin'
    else:
        # Ensure column exists even if empty
        df = pd.DataFrame(columns=['job_board'])
    print(f"[scrape] LinkedIn: built dataframe with {len(df)} rows.")
    return df
        

def jobnet_scraper(title, postal, km_dist, num_jobs, existing_keys: Optional[Set[Tuple[str,str]]] = None, cutoff_dt: Optional[datetime] = None):
    list_url = f"https://jobnet.dk/bff/FindJob/Search?resultsPerPage={num_jobs}&pageNumber=1&orderType=PublicationDate&kmRadius={km_dist}&searchString={title.replace(' ', '+')}&postalCode={postal}"
    response = requests.get(list_url)   
    if response.status_code != 200:
        print(f"[scrape] Jobnet: failed to fetch job listings (status code: {response.status_code})")
        return pd.DataFrame(columns=['job_board'])
    response_dict = response.json()
    print(f"[scrape] Jobnet: fetching up to {num_jobs} jobs for '{title}' near {postal} (r={km_dist}km)")
    if existing_keys is None:
        existing_keys = set()
    job_list = []
    postings = response_dict.get("jobAds", [])
    early_reason = None
    for job_dict in tqdm(postings, desc="Jobnet jobs", unit="job"):
        job_id = job_dict["jobAdId"]
        job_url = job_dict["jobAdUrl"]
        if len(job_url) == 0:
            job_url = f"https://jobnet.dk/find-job/{job_id}"
        job_post = {}
        
        job_post["title"] = job_dict["title"]
        job_post["company"] = job_dict["hiringOrgName"]
        job_post["location"] = job_dict["postalDistrictName"]
        
        deadline = job_dict.get("applicationDeadline")
        if deadline:
            job_post["deadline"] = deadline[:10]
        else:
            job_post["deadline"] = None
        job_post["time_posted"] = job_dict["publicationDate"]
        job_post["url"] = job_url
        job_post["employment_type"] = None
        if job_dict["workHourPartTime"]:
            job_post["full_or_part_time"] = "Part-time"
        else:
            job_post["full_or_part_time"] = "Full-time"

        job_soup = BeautifulSoup(job_dict["description"], 'html.parser')
        desc_lines = [line.strip() for line in job_soup.stripped_strings if line.strip()]
        job_post["description"] = "\n".join(desc_lines)
        
        key = (job_post.get("company"), job_post.get("title"))
        # Early termination checks
        # Parse posted time if possible (ISO expected)
        posted_raw = job_post.get("time_posted")
        posted_dt = None
        if posted_raw:
            try:
                posted_dt = pd.to_datetime(posted_raw, utc=True, errors='coerce')
            except Exception:
                posted_dt = None
        if key in existing_keys:
            early_reason = "first existing key encountered (sorted list)"
            break
        if cutoff_dt and posted_dt is not None and posted_dt.to_pydatetime() < cutoff_dt:
            early_reason = "job older than last scrape timestamp"
            break
        job_list.append(job_post)

    df = pd.DataFrame(job_list)
    if not df.empty:
        df['job_board'] = 'jobnet'
    else:
        df = pd.DataFrame(columns=['job_board'])
    if early_reason:
        print(f"[scrape] Jobnet: early termination - {early_reason}; collected {len(job_list)} new rows")
    print(f"[scrape] Jobnet: dataframe rows={len(df)}")
    return df


def jobindex_scraper(title, city, postal, street, km_dist, num_jobs, existing_keys: Optional[Set[Tuple[str,str]]] = None, cutoff_dt: Optional[datetime] = None):
    page = 1
    job_list = []
    print(f"[scrape] Jobindex: collecting up to {num_jobs} jobs for '{title}' around {postal} {city} (r={km_dist}km)")

    if existing_keys is None:
        existing_keys = set()
    early_reason = None
    with tqdm(total=num_jobs, desc="Jobindex jobs", unit="job") as pbar:
        while len(job_list) < num_jobs and early_reason is None:
            list_url = (
                "https://www.jobindex.dk/api/jobsearch/v3/?address="
                f"{street.replace(' ', '+')}%2C+{postal}+{city.replace(' ', '+')}+&q={title.lower().replace(' ', '+')}"
                f"&radius={km_dist}&sort=date&page={page}&include_html=1&include_skyscraper=1"
            )
            response = requests.get(list_url)
            if response.status_code != 200:
                break
            response_dict = response.json()

            for job_dict in response_dict.get('results', []):
                job_id = job_dict.get("tid")
                job_url = job_dict.get("url")
                job_post = {}

                job_post["title"] = job_dict.get("headline")
                company_obj = job_dict.get("company") or {}
                job_post["company"] = company_obj.get("name")
                try:
                    job_post["location"] = job_dict.get("addresses", [{}])[0].get("city")
                except Exception:
                    job_post["location"] = None
                job_post["time_posted"] = job_dict.get("firstdate")
                deadline = job_dict.get("apply_deadline")
                if deadline:
                    job_post["deadline"] = deadline[:10]
                else:
                    job_post["deadline"] = None
                job_post["url"] = job_url
                job_post["description"] = None

                if job_dict.get("is_local"):
                    job_post["description"] = job_dict.get("html")
                    if job_id and job_post["title"]:
                        safe_slug = (job_post["title"] or "").lower().replace(' ', '-')
                        job_response = requests.get(f"https://www.jobindex.dk/jobannonce/{job_id}/{safe_slug}")
                        if job_response.status_code == 200:
                            job_soup = BeautifulSoup(job_response.text, 'html.parser')
                            section = job_soup.find("section", {"class": "jobtext-jobad__body"})
                            if section:
                                lines = [l.strip() for l in section.stripped_strings if l.strip()]
                                job_post["description"] = "\n".join(lines)
                            else:
                                job_post["description"] = None

                key = (job_post.get("company"), job_post.get("title"))
                # Parse posting date (ISO-like) for early termination
                posted_raw = job_post.get("time_posted")
                posted_dt = None
                if posted_raw:
                    try:
                        posted_dt = pd.to_datetime(posted_raw, utc=True, errors='coerce')
                    except Exception:
                        posted_dt = None
                if key in existing_keys:
                    early_reason = "first existing key encountered (sorted list)"
                    break
                if cutoff_dt and posted_dt is not None and posted_dt.to_pydatetime() < cutoff_dt:
                    early_reason = "job older than last scrape timestamp"
                    break
                job_list.append(job_post)
                pbar.update(1)
                if len(job_list) >= num_jobs:
                    break
            page += 1
    len_before = len(job_list)
    df = pd.DataFrame(job_list)
    df = df.drop_duplicates()
    df = df.reset_index(drop=True)
    if not df.empty:
        df['job_board'] = 'jobindex'
    else:
        df = pd.DataFrame(columns=['job_board'])
    assert len(df) == len_before, "Duplicates were found and removed"
    if early_reason:
        print(f"[scrape] Jobindex: early termination - {early_reason}; collected {len(df)} new rows")
    print(f"[scrape] Jobindex: dataframe rows={len(df)} (requested {num_jobs})")
    return df


def auto_reject_jobs(df):
    # Reject based on title keywords
    for keyword in title_keywords:
        df.loc[df['title'].str.contains(keyword, case=False, na=False), 'decision'] = 'reject'
        df.loc[df['title'].str.contains(keyword, case=False, na=False), 'decision_reason'] = f"Title contains '{keyword}'"
    return df