"""
311 Service Request collector.
Fetches complaint data from NYC Open Data (Socrata), aggregates by community district.
"""

import time
import requests
from datetime import datetime, timedelta
from collections import defaultdict

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SOCRATA_BASE, THREE11_DATASET_ID, COMPLAINT_CATEGORY_MAP


def fetch_311(days=90, batch_size=50000):
    """
    Fetch 311 complaints from the last N days.
    Returns list of complaint dicts.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    url = f"{SOCRATA_BASE}/{THREE11_DATASET_ID}.json"

    all_records = []
    offset = 0

    while True:
        params = {
            "$select": "created_date,complaint_type,descriptor,community_board,borough,latitude,longitude,status",
            "$where": f"created_date > '{cutoff}' AND community_board IS NOT NULL",
            "$order": "created_date DESC",
            "$limit": batch_size,
            "$offset": offset,
        }

        print(f"  Fetching 311 records (offset={offset})...")
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=120,
                                    headers={"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"})
                resp.raise_for_status()
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < 2:
                    wait = 10 * (attempt + 1)
                    print(f"  Retry {attempt+1}/2 after {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
        data = resp.json()

        if not data:
            break

        all_records.extend(data)
        print(f"  ... got {len(data)} records (total: {len(all_records)})")

        if len(data) < batch_size:
            break

        offset += batch_size
        time.sleep(0.5)  # Be polite to the API

    return all_records


def parse_community_board(cb_string):
    """
    Parse '01 MANHATTAN' → '101', '03 BROOKLYN' → '303', etc.
    """
    if not cb_string:
        return None

    parts = cb_string.strip().split(" ", 1)
    if len(parts) < 2:
        return None

    try:
        num = int(parts[0])
    except ValueError:
        return None

    borough = parts[1].upper().strip()
    boro_map = {
        "MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3",
        "QUEENS": "4", "STATEN ISLAND": "5",
    }

    boro_code = boro_map.get(borough)
    if not boro_code:
        return None

    return f"{boro_code}{num:02d}"


def categorize_complaint(complaint_type):
    """Map a 311 complaint type to our category taxonomy."""
    ct_lower = (complaint_type or "").lower()
    for category, keywords in COMPLAINT_CATEGORY_MAP.items():
        for kw in keywords:
            if kw in ct_lower:
                return category
    return "quality-of-life"  # default bucket


def aggregate_311(records):
    """
    Aggregate 311 records by community district.
    Returns dict keyed by CD code with complaint counts, types, and weekly timeseries.
    """
    by_district = defaultdict(lambda: {
        "total": 0,
        "by_type": defaultdict(int),
        "by_category": defaultdict(int),
        "weekly": defaultdict(lambda: defaultdict(int)),  # week_key → type → count
        "recent_descriptors": [],
    })

    now = datetime.now()

    for r in records:
        cd = parse_community_board(r.get("community_board", ""))
        if not cd:
            continue

        complaint_type = (r.get("complaint_type") or "Unknown").strip()
        category = categorize_complaint(complaint_type)
        descriptor = (r.get("descriptor") or "").strip()

        district = by_district[cd]
        district["total"] += 1
        district["by_type"][complaint_type] += 1
        district["by_category"][category] += 1

        # Weekly bucketing
        try:
            created = datetime.fromisoformat(r["created_date"].replace("Z", "+00:00").split("+")[0])
            week_num = (now - created).days // 7
            if week_num < 12:
                week_key = f"w{week_num}"
                district["weekly"][week_key][complaint_type] += 1
        except (ValueError, KeyError):
            pass

        # Collect recent descriptors for context
        if descriptor and district["total"] <= 200:
            district["recent_descriptors"].append({
                "type": complaint_type,
                "descriptor": descriptor,
                "date": r.get("created_date", "")[:10],
            })

    return dict(by_district)


def compute_sparklines(district_data):
    """
    For each district's top complaint types, compute 12-week sparkline data.
    Returns dict of cd → [{type, counts: [w11, w10, ..., w0], total}]
    """
    sparklines = {}

    for cd, data in district_data.items():
        # Get top 8 complaint types
        top_types = sorted(data["by_type"].items(), key=lambda x: -x[1])[:8]

        cd_sparklines = []
        for complaint_type, total in top_types:
            counts = []
            for w in range(11, -1, -1):  # oldest to newest
                week_key = f"w{w}"
                count = data["weekly"].get(week_key, {}).get(complaint_type, 0)
                counts.append(count)
            cd_sparklines.append({
                "type": complaint_type,
                "counts": counts,
                "total": total,
            })

        sparklines[cd] = cd_sparklines

    return sparklines


def collect():
    """Main entry point. Returns (records, aggregated, sparklines)."""
    print("[311] Fetching 311 complaint data...")
    records = fetch_311(days=90)
    print(f"[311] Got {len(records)} records")

    print("[311] Aggregating by community district...")
    aggregated = aggregate_311(records)
    print(f"[311] Aggregated across {len(aggregated)} districts")

    print("[311] Computing sparklines...")
    sparklines = compute_sparklines(aggregated)

    return records, aggregated, sparklines


if __name__ == "__main__":
    records, aggregated, sparklines = collect()
    # Print summary
    for cd in sorted(aggregated.keys()):
        d = aggregated[cd]
        top = sorted(d["by_type"].items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{t}({c})" for t, c in top)
        print(f"  CD {cd}: {d['total']} complaints — {top_str}")
