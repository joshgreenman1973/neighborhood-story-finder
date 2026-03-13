"""
CouncilStat constituent services collector.
Fetches council member constituent complaints from NYC Open Data.
Shows what is politically sticky — issues residents escalate to elected officials.

Note: This dataset may lag in updates. The collector handles sparse data gracefully.
"""

import requests
from datetime import datetime, timedelta
from collections import defaultdict

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SOCRATA_BASE, COUNCILSTAT_DATASET_ID


BORO_CODE = {
    "Manhattan": "1", "Bronx": "2", "Brooklyn": "3",
    "Queens": "4", "Staten Island": "5",
}


def _parse_community_board(cb_str):
    """Convert '05 Brooklyn' to CD code '305'."""
    if not cb_str or " " not in cb_str:
        return None
    parts = cb_str.split(" ", 1)
    try:
        num = int(parts[0])
    except ValueError:
        return None
    boro = BORO_CODE.get(parts[1])
    if not boro:
        return None
    return f"{boro}{num:02d}"


def fetch_council_services(days=365):
    """
    Fetch constituent service complaints from CouncilStat.
    Uses a longer window (1 year) since data updates may be infrequent.
    Returns dict of cd_code → {complaint_types: {type: count}, total: int, recent: [...]}.
    """
    url = f"{SOCRATA_BASE}/{COUNCILSTAT_DATASET_ID}.json"
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")

    print(f"[CouncilStat] Fetching constituent services (last {days} days)...")

    all_records = []
    offset = 0
    while True:
        resp = requests.get(url, params={
            "$where": f"opendate > '{cutoff}' AND community_board IS NOT NULL",
            "$select": "opendate,complaint_type,descriptor,community_board,borough,council_dist",
            "$order": "opendate DESC",
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

    print(f"[CouncilStat] Got {len(all_records)} constituent cases")

    if not all_records:
        return {}

    by_district = {}
    for rec in all_records:
        cd = _parse_community_board(rec.get("community_board"))
        if not cd:
            continue

        if cd not in by_district:
            by_district[cd] = {"complaint_types": defaultdict(int), "total": 0, "recent": []}

        complaint_type = rec.get("complaint_type", "Other")
        by_district[cd]["complaint_types"][complaint_type] += 1
        by_district[cd]["total"] += 1

        # Keep most recent cases for display
        if len(by_district[cd]["recent"]) < 10:
            by_district[cd]["recent"].append({
                "type": complaint_type,
                "descriptor": rec.get("descriptor", ""),
                "date": (rec.get("opendate") or "")[:10],
                "council_dist": rec.get("council_dist", ""),
            })

    # Convert defaultdicts to regular dicts for JSON
    for cd in by_district:
        by_district[cd]["complaint_types"] = dict(by_district[cd]["complaint_types"])

    print(f"[CouncilStat] Processed cases for {len(by_district)} districts")
    return by_district
