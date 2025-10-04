import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta

# TODO: Add date formatting to datetime (current "1 week ago", "3 days ago", etc.)
# TODO: Add error handling for requests
def linkedin_scraper(title, city, num_jobs):
    """
    Scrape job listings from LinkedIn based on job title and city.

    Parameters:
    title (str): Job title to search for.
    city (str): City to search in.
    num_jobs (int): Number of job listings to scrape.

    Returns:
    pd.DataFrame: DataFrame containing job listings with columns 'Title', 'Company', 'Location', 'Link'.
    """
    
    id_list = []

    while len(id_list) < num_jobs:
        start = len(id_list)
        list_url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={'%20'.join(title.split(' '))}&location=&location={'%20'.join(city.split(' '))}%2C%20Denmark&start={start}"

        response = requests.get(list_url)
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            break

        list_soup = BeautifulSoup(response.text, 'html.parser')
        page_jobs = list_soup.find_all('li')
        for job in page_jobs:
            base_card_div = job.find("div", {"class": "base-card"})
            job_id = base_card_div.get("data-entity-urn").split(":")[3]
            id_list.append(job_id)
    
    print(f"Found {len(id_list)} jobs.")
    
    job_list = []

    for job_id in id_list:
        job_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        job_response = requests.get(job_url)
        job_soup = BeautifulSoup(job_response.text, 'html.parser')
        job_post = {}
        
        job_post["url"] = job_url
        
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
        
        try:
            date_str = job_soup.find("span", {"class": "posted-time-ago__text topcard__flavor--metadata"}).text.strip()
            if "week" in date_str or "month" in date_str or "year" in date_str:
                job_post["time_posted"] = None
            else:
                time_value, time_unit, _ = date_str.split(" ")
                if time_unit.startswith("day"):
                    delta = timedelta(days=int(time_value))
                elif time_unit.startswith("hour"):
                    delta = timedelta(hours=int(time_value))
                else:
                    delta = timedelta(0)
                job_post["time_posted"] = (datetime.now() - delta)
        except:
            job_post["time_posted"] = None
        
        try:
            job_post["num_applicants"] = int(job_soup.find("span", {"class": "num-applicants__caption topcard__flavor--metadata topcard__flavor--bullet"}).text.strip().split(" ")[0])
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
            job_info = dict(zip(info_type, info_value))
            job_post.update(job_info)
        except:
            pass
        
        job_list.append(job_post)
        
    return pd.DataFrame(job_list)
        

def jobnet_scraper(title, city, postal, km_dist, num_jobs):
    payload = {"model":{"Offset":"0","Count":num_jobs,"SearchString":title,"SortValue":"CreationDate","Ids":[],"EarliestPublicationDate":None,"HotJob":None,"Abroad":None,"NearBy":"","OnlyGeoPoints":False,"WorkPlaceNotStatic":None,"WorkHourMin":None,"WorkHourMax":None,"Facets":{"Region":None,"Country":None,"Municipality":None,"PostalCode":None,"OccupationAreas":None,"OccupationGroups":None,"Occupations":None,"EmploymentType":None,"WorkHours":None,"WorkHourPartTime":None,"JobAnnouncementType":None,"WorkPlaceNotStatic":None},"LocatedIn":None,"LocationZip":postal + " " + city,"Location":None,"SearchInGeoDistance":km_dist,"SimilarOccupations":None,"SearchWithSimilarOccupations":False},"url":f"/CV/FindWork?SearchString={'%2520'.join(title.split(' '))}&Offset=0&SortValue=CreationDate&SearchInGeoDistance={km_dist}&LocationZip={'%2520'.join((postal + ' ' + city).split(' '))}"}
    response = requests.post("https://job.jobnet.dk/CV/FindWork/Search", json=payload)
    assert response.status_code == 200, "Failed to retrieve job listings"
    response_dict = response.json()
    job_list = []
    for job_dict in response_dict["JobPositionPostings"]:
        job_id = job_dict["ID"]
        job_url = job_dict["Url"]
        job_post = {}
        
        job_post["title"] = job_dict["Title"]
        job_post["company"] = job_dict["HiringOrgName"]
        job_post["location"] = job_dict["WorkPlaceCity"]
        
        job_post["time_posted"] = job_dict["PostingCreated"]
        job_post["url"] = job_url
        job_post["employment_type"] = job_dict["EmploymentType"]
        job_post["full_or_part_time"] = job_dict["WorkHours"]

        job_post["description"] = None 
        
        if not job_dict["IsExternal"]:
            job_response = requests.get(f"https://job.jobnet.dk/CV/FindWork/JobDetailJson?id={job_id}&previewtoken=")
            if job_response.status_code == 200:
                data = job_response.json()
                formatted_html = data.get("FormattedPurpose") or ""
                job_soup = BeautifulSoup(formatted_html, 'html.parser')
                desc_lines = [line.strip() for line in job_soup.stripped_strings if line.strip()]
                job_post["description"] = "\n".join(desc_lines) or data.get("Description")
        job_list.append(job_post)

    return pd.DataFrame(job_list)


# TODO: Add full time/part time info
def jobindex_scraper(title, city, postal, street, km_dist, num_jobs):
    page = 1
    job_list = []
    while len(job_list) < num_jobs:
        list_url = f"https://www.jobindex.dk/api/jobsearch/v3/?address={street.replace(' ', '+')}%2C+{postal}+{city.replace(' ', '+')}+&q={title.lower().replace(' ', '+')}&radius={km_dist}&sort=date&page={page}&include_html=1&include_skyscraper=1"
        response = requests.get(list_url)
        if response.status_code != 200:
            break
        response_dict = response.json()
        
        for job_dict in response_dict['results']:
            job_id = job_dict["tid"]
            job_url = job_dict["url"]
            job_post = {}
            
            job_post["title"] = job_dict["headline"]
            job_post["company"] = job_dict["company"]["name"]
            try:
                job_post["location"] = job_dict["addresses"][0]["city"]
            except:
                job_post["location"] = None
            job_post["time_posted"] = job_dict["firstdate"]
            
            job_post["url"] = job_url

            job_post["description"] = None
            
            if job_dict["is_local"]:
                job_post["description"] = job_dict["html"]
                job_response = requests.get(f"https://www.jobindex.dk/jobannonce/{job_id}/{job_dict['headline'].lower().replace(' ', '-')}")
                if job_response.status_code == 200:
                    job_soup = BeautifulSoup(job_response.text, 'html.parser')
                    section = job_soup.find("section", {"class": "jobtext-jobad__body"})
                    if section:
                        lines = [l.strip() for l in section.stripped_strings if l.strip()]
                        job_post["description"] = "\n".join(lines)
                    else:
                        job_post["description"] = None

            job_list.append(job_post)
            if len(job_list) >= num_jobs:
                break
        page += 1
    len_before = len(job_list)
    df = pd.DataFrame(job_list)
    df = df.drop_duplicates()
    df = df.reset_index(drop=True)
    assert len(df) == len_before, "Duplicates were found and removed"
    return df

