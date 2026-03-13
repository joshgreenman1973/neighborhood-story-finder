"""
DOB (Department of Buildings) permit filings collector.
Fetches recent building permit filings from NYC Open Data.
Spikes in demolition, new building, or alteration permits signal development activity.
"""

import requests
from datetime import datetime, timedelta
from collections import defaultdict

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SOCRATA_BASE


# DOB NOW: Build - Job Application Filings
DOB_NOW_DATASET_ID = "w9ak-ipjd"

# Job types that signal significant activity
NOTABLE_JOB_TYPES = {
    "NB": "New Building",
    "DM": "Demolition",
    "A1": "Major Alteration",
    "A2": "Minor Alteration",
    "A3": "Minor Alteration",
    "SG": "Sign",
}


def _parse_cd_from_dob(cb_str):
    """Convert DOB community board '104' to our format '104'."""
    if not cb_str or len(cb_str) < 3:
        return None
    try:
        int(cb_str)
        return cb_str
    except ValueError:
        return None


def fetch_dob_permits(days=90):
    """
    Fetch recent DOB permit filings.
    Returns dict of cd_code → {total, by_type: {type: count}, notable: [...]}.
    """
    url = f"{SOCRATA_BASE}/{DOB_NOW_DATASET_ID}.json"
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")

    print(f"[DOB] Fetching permit filings (last {days} days)...")

    all_records = []
    offset = 0
    while True:
        resp = requests.get(url, params={
            "$where": f"filing_date > '{cutoff}' AND commmunity_board IS NOT NULL",
            "$select": "job_filing_number,filing_status,borough,commmunity_board,"
                       "job_type,house_no,street_name,filing_date,"
                       "owner_s_business_name",
            "$order": "filing_date DESC",
            "$limit": 50000,
            "$offset": offset,
        }, timeout=60, headers={"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"})
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        all_records.extend(data)
        if len(data) < 50000:
            break
        offset += 50000

    print(f"[DOB] Got {len(all_records)} permit filings")

    by_district = {}
    for rec in all_records:
        cd = _parse_cd_from_dob(rec.get("commmunity_board"))
        if not cd:
            continue

        if cd not in by_district:
            by_district[cd] = {"total": 0, "by_type": defaultdict(int), "notable": []}

        job_type = rec.get("job_type", "")
        by_district[cd]["total"] += 1
        type_label = NOTABLE_JOB_TYPES.get(job_type, job_type)
        by_district[cd]["by_type"][type_label] += 1

        # Track notable filings (new buildings, demolitions)
        if job_type in ("NB", "DM") and len(by_district[cd]["notable"]) < 10:
            address = f"{rec.get('house_no', '')} {rec.get('street_name', '')}".strip()
            by_district[cd]["notable"].append({
                "type": type_label,
                "address": address,
                "date": (rec.get("filing_date") or "")[:10],
                "owner": (rec.get("owner_s_business_name") or "")[:100],
                "status": rec.get("filing_status", ""),
            })

    # Convert defaultdicts
    for cd in by_district:
        by_district[cd]["by_type"] = dict(by_district[cd]["by_type"])

    print(f"[DOB] Permit filings in {len(by_district)} districts")
    return by_district
