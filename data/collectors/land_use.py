"""
Land use / ULURP collector.
Fetches active zoning applications from the Zoning Application Portal (ZAP) on NYC Open Data.
Surfaces rezonings, shelter sitings, street redesigns, and other land-use fights
before they become neighborhood conflicts.
"""

import requests

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SOCRATA_BASE, ZAP_DATASET_ID, ZAP_BORO_MAP


def _parse_cd_from_zap(community_district):
    """
    Convert ZAP community_district (e.g., 'X10', 'K03') to our CD code (e.g., '210', '303').
    """
    if not community_district or len(community_district) < 2:
        return None
    letter = community_district[0]
    number = community_district[1:]
    boro = ZAP_BORO_MAP.get(letter)
    if not boro:
        return None
    try:
        return f"{boro}{int(number):02d}"
    except ValueError:
        return None


def fetch_land_use():
    """
    Fetch active ULURP and land use applications from ZAP.
    Returns dict of cd_code → list of project dicts.
    """
    url = f"{SOCRATA_BASE}/{ZAP_DATASET_ID}.json"

    print("[Land Use] Fetching active zoning applications...")

    resp = requests.get(url, params={
        "$where": "project_status='Active'",
        "$select": "project_id,project_name,project_brief,ulurp_non,actions,"
                   "primary_applicant,applicant_type,borough,community_district,"
                   "cc_district,current_milestone,current_milestone_date,"
                   "noticed_date,certified_referred,public_status",
        "$order": "current_milestone_date DESC",
        "$limit": 5000,
    }, timeout=60, headers={"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"})
    resp.raise_for_status()
    projects = resp.json()

    print(f"[Land Use] Got {len(projects)} active projects")

    by_district = {}
    for proj in projects:
        cd = _parse_cd_from_zap(proj.get("community_district"))
        if not cd:
            continue

        if cd not in by_district:
            by_district[cd] = []

        by_district[cd].append({
            "name": proj.get("project_name", ""),
            "brief": (proj.get("project_brief") or "")[:400],
            "type": proj.get("ulurp_non", ""),
            "actions": proj.get("actions", ""),
            "applicant": proj.get("primary_applicant", ""),
            "applicant_type": proj.get("applicant_type", ""),
            "status": proj.get("public_status", ""),
            "milestone": proj.get("current_milestone", ""),
            "milestone_date": (proj.get("current_milestone_date") or "")[:10],
            "noticed_date": (proj.get("noticed_date") or "")[:10],
        })

    # Sort by milestone date (most recent first)
    for cd in by_district:
        by_district[cd].sort(key=lambda p: p.get("milestone_date", ""), reverse=True)

    print(f"[Land Use] Active projects in {len(by_district)} districts")
    return by_district
