"""
Community Board Budget Requests collector.
Fetches the Register of Community Board Budget Requests from NYC Open Data (OMB).
Shows what districts are repeatedly asking the city to fix or fund.
"""

import requests

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SOCRATA_BASE, CB_BUDGET_DATASET_ID, CATEGORIES


# Map common agency/request keywords to our categories
REQUEST_CATEGORY_HINTS = {
    "housing": ["housing", "HPD", "hpd", "affordable", "tenant", "rent", "shelter"],
    "transit": ["DOT", "traffic", "pedestrian", "bike", "bus", "subway", "MTA", "crosswalk", "signal"],
    "education": ["school", "DOE", "library", "NYPL", "education", "youth"],
    "safety": ["NYPD", "police", "crime", "safety", "lighting", "camera"],
    "environment": ["DEP", "parks", "tree", "flood", "storm", "waterfront", "green"],
    "infrastructure": ["sewer", "water main", "bridge", "road", "sidewalk", "pothole"],
    "health": ["DOHMH", "health", "hospital", "mental", "opioid", "rat"],
    "quality-of-life": ["sanitation", "noise", "DSNY", "litter", "graffiti", "homeless"],
    "development": ["rezone", "development", "construction", "landmark", "zoning"],
}


def _categorize_request(request_text, agency):
    """Categorize a budget request based on text content and agency."""
    combined = f"{request_text} {agency}".lower()
    for cat, keywords in REQUEST_CATEGORY_HINTS.items():
        for kw in keywords:
            if kw.lower() in combined:
                return cat
    return "government"


def _parse_cd_code(boro, board):
    """Convert boro + board to our CD code format (e.g., '1' + '01' → '101')."""
    try:
        return f"{int(boro)}{int(board):02d}"
    except (ValueError, TypeError):
        return None


def fetch_budget_requests():
    """
    Fetch the most recent community board budget requests.
    Returns dict of cd_code → list of request dicts.
    """
    url = f"{SOCRATA_BASE}/{CB_BUDGET_DATASET_ID}.json"

    # Get the most recent publication
    meta_resp = requests.get(url, params={
        "$select": "publication",
        "$group": "publication",
        "$order": "publication DESC",
        "$limit": 1,
    }, timeout=30, headers={"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"})
    meta_resp.raise_for_status()
    meta = meta_resp.json()

    if not meta:
        print("[Budget] No budget request data found")
        return {}

    latest_pub = meta[0]["publication"]
    print(f"[Budget] Fetching budget requests (publication: {latest_pub})...")

    # Fetch all requests from latest publication
    all_requests = []
    offset = 0
    while True:
        resp = requests.get(url, params={
            "$where": f"publication='{latest_pub}'",
            "$limit": 5000,
            "$offset": offset,
        }, timeout=60, headers={"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"})
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        all_requests.extend(data)
        if len(data) < 5000:
            break
        offset += 5000

    print(f"[Budget] Got {len(all_requests)} budget requests")

    # Group by community district
    by_district = {}
    for req in all_requests:
        cd = _parse_cd_code(req.get("boro"), req.get("board"))
        if not cd:
            continue

        if cd not in by_district:
            by_district[cd] = []

        category = _categorize_request(
            req.get("request", ""),
            req.get("responsible_agency", "")
        )

        by_district[cd].append({
            "request": req.get("request", ""),
            "explanation": (req.get("explanation") or "")[:300],
            "priority": req.get("priority", ""),
            "agency": req.get("responsible_agency", ""),
            "response": (req.get("response") or "")[:200],
            "category": category,
        })

    # Sort each district's requests: capital priorities first, then expense
    for cd in by_district:
        by_district[cd].sort(key=lambda r: (
            0 if r["priority"].startswith("C") else 1,
            r["priority"]
        ))

    print(f"[Budget] Processed requests for {len(by_district)} districts")
    return by_district
