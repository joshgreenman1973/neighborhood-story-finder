#!/usr/bin/env python3
"""
NYC Open Data Weekly Scanner
Fetches recently updated datasets and key metrics from NYC Open Data (Socrata API).
Run weekly to generate a consolidated insights report + append to trend CSV.
"""

import csv
import json
import os
import requests
from datetime import datetime, timedelta
from collections import Counter

BASE = "https://data.cityofnewyork.us/resource"
CATALOG = "https://api.us.socrata.com/api/catalog/v1"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")

CSV_COLUMNS = [
    "week_ending", "crashes", "persons_injured", "persons_killed",
    "pedestrians_injured", "pedestrians_killed", "cyclists_injured",
    "shooting_incidents", "shooting_victims", "shooting_murders",
    "hpd_complaints", "hpd_heat_hot_water", "hpd_heat_pct",
    "hpd_bronx_pct", "hpd_open_pct", "hpd_immediate_emergency",
    "vacate_orders_new", "vacate_orders_active",
    "restaurant_inspections", "critical_violations", "restaurant_closures",
    "dob_filings", "dob_large_projects_over_1m",
]


def fetch_json(url, params=None):
    r = requests.get(url, params=params, timeout=60,
                     headers={"User-Agent": "NYC-Open-Data-Weekly/1.0"})
    r.raise_for_status()
    return r.json()


def get_updated_datasets(days=7, limit=200):
    """Get all datasets updated in the past N days."""
    data = fetch_json(CATALOG, {
        "domains": "data.cityofnewyork.us",
        "order": "updatedAt DESC",
        "limit": limit,
        "only": "datasets",
        "provenance": "official"
    })
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent = []
    for r in data.get("results", []):
        updated = r["resource"].get("updatedAt", "")
        if updated:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00")).replace(tzinfo=None)
            if dt > cutoff:
                agency = ""
                for m in r.get("classification", {}).get("domain_metadata", []):
                    if m.get("key") == "Dataset-Information_Agency":
                        agency = m["value"]
                recent.append({
                    "name": r["resource"]["name"],
                    "id": r["resource"]["id"],
                    "updated": updated,
                    "category": r.get("classification", {}).get("domain_category", ""),
                    "agency": agency,
                    "description": r["resource"].get("description", "")[:120],
                    "views_last_week": r["resource"].get("page_views", {}).get("page_views_last_week", 0),
                })
    return recent


# --- Individual dataset scanners ---

def scan_collisions(days=7):
    """NYPD Motor Vehicle Collisions - Crashes (h9gi-nx95)"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = fetch_json(f"{BASE}/h9gi-nx95.json", {
        "$where": f"crash_date>='{since}'",
        "$limit": 5000
    })
    if not rows:
        return None
    return {
        "total_crashes": len(rows),
        "persons_injured": sum(int(r.get("number_of_persons_injured", 0)) for r in rows),
        "persons_killed": sum(int(r.get("number_of_persons_killed", 0)) for r in rows),
        "pedestrians_injured": sum(int(r.get("number_of_pedestrians_injured", 0)) for r in rows),
        "pedestrians_killed": sum(int(r.get("number_of_pedestrians_killed", 0)) for r in rows),
        "cyclists_injured": sum(int(r.get("number_of_cyclist_injured", 0)) for r in rows),
        "borough_breakdown": dict(Counter(r.get("borough", "UNSPECIFIED") for r in rows).most_common()),
        "top_factors": dict(Counter(r.get("contributing_factor_vehicle_1", "Unspecified") for r in rows).most_common(10)),
    }


def scan_hpd_complaints(days=7):
    """HPD Housing Maintenance Complaints (ygpa-z7cr)"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = fetch_json(f"{BASE}/ygpa-z7cr.json", {
        "$where": f"receiveddate>='{since}'",
        "$select": "count(*) as total",
    })
    total = int(rows[0]["total"]) if rows else 0
    types = fetch_json(f"{BASE}/ygpa-z7cr.json", {
        "$where": f"receiveddate>='{since}'",
        "$select": "majorcategory, count(*) as cnt",
        "$group": "majorcategory",
        "$order": "cnt DESC",
        "$limit": 10,
    })
    boroughs = fetch_json(f"{BASE}/ygpa-z7cr.json", {
        "$where": f"receiveddate>='{since}'",
        "$select": "borough, count(*) as cnt",
        "$group": "borough",
        "$order": "cnt DESC",
    })
    # Status breakdown
    statuses = fetch_json(f"{BASE}/ygpa-z7cr.json", {
        "$where": f"receiveddate>='{since}'",
        "$select": "status, count(*) as cnt",
        "$group": "status",
        "$order": "cnt DESC",
    })
    return {
        "total_complaints": total,
        "top_categories": {r["majorcategory"]: int(r["cnt"]) for r in types},
        "borough_breakdown": {r["borough"]: int(r["cnt"]) for r in boroughs},
        "status_breakdown": {r["status"]: int(r["cnt"]) for r in statuses},
    }


def scan_hpd_vacates(days=7):
    """HPD Order to Repair/Vacate (tb8q-a3ar)"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = fetch_json(f"{BASE}/tb8q-a3ar.json", {
        "$where": f"vacate_effective_date>='{since}'",
        "$order": "vacate_effective_date DESC",
        "$limit": 200,
    })
    active = [r for r in rows if not r.get("actual_rescind_date")]
    return {
        "new_orders": len(rows),
        "still_active": len(active),
        "reasons": dict(Counter(r.get("primary_vacate_reason", "") for r in rows).most_common()),
        "boroughs": dict(Counter(r.get("boro_short_name", "") for r in rows).most_common()),
    }


def scan_restaurant_inspections(days=7):
    """DOHMH Restaurant Inspections (43nn-pn8j)"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = fetch_json(f"{BASE}/43nn-pn8j.json", {
        "$where": f"inspection_date>='{since}'",
        "$limit": 5000,
    })
    grades = Counter(r.get("grade", "No Grade") for r in rows)
    critical = [r for r in rows if r.get("critical_flag") == "Critical"]
    # Count closures (grade P or action includes closure)
    closures = [r for r in rows if r.get("action", "").startswith("Establishment Closed")]
    return {
        "total_inspections": len(rows),
        "grade_distribution": dict(grades.most_common()),
        "critical_violations": len(critical),
        "closures": len(set(r.get("camis", "") for r in closures)),
    }


def scan_shootings(days=7):
    """NYPD Shooting Incidents (5ucz-vwe8), Victims (pztn-9bne)"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    incidents = fetch_json(f"{BASE}/5ucz-vwe8.json", {
        "$where": f"occur_date>='{since}'",
        "$limit": 5000,
    })
    if not incidents:
        return {"total_incidents": 0, "total_victims": 0, "murders": 0}
    keys = [r["incident_key"] for r in incidents if "incident_key" in r]
    victims = []
    if keys:
        victims = fetch_json(f"{BASE}/pztn-9bne.json", {
            "$where": f"incident_key in({','.join(repr(k) for k in keys[:200])})",
            "$limit": 5000,
        })
    murders = sum(1 for v in victims if v.get("stat_murder_flg") == "Y")
    return {
        "total_incidents": len(incidents),
        "total_victims": len(victims),
        "murders": murders,
        "borough_breakdown": dict(Counter(r.get("boro", "UNKNOWN") for r in incidents).most_common()),
    }


def scan_dob_filings(days=7):
    """DOB NOW Job Application Filings (w9ak-ipjd)"""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = fetch_json(f"{BASE}/w9ak-ipjd.json", {
        "$where": f"filing_date>='{since}'",
        "$limit": 2000,
    })
    big_projects = [r for r in rows if float(r.get("initial_cost", 0) or 0) > 1_000_000]
    return {
        "total_filings": len(rows),
        "large_projects_over_1m": len(big_projects),
    }


# --- CSV + JSON output ---

def build_week_row(week_ending, collisions, hpd, vacates, restaurants, shootings, dob):
    """Build a single row dict for the weekly trends CSV."""
    heat_hw = hpd["top_categories"].get("HEAT/HOT WATER", 0) if hpd else 0
    hpd_total = hpd["total_complaints"] if hpd else 0
    bronx = hpd["borough_breakdown"].get("BRONX", 0) if hpd else 0
    open_count = hpd["status_breakdown"].get("Open", 0) if hpd else 0
    emergency = hpd["top_categories"].get("GENERAL", 0) if hpd else 0  # approximate

    # For immediate emergency, try to get "EMERGENCY" category
    imm_emergency = hpd["top_categories"].get("EMERGENCY", 0) if hpd else 0

    return {
        "week_ending": week_ending,
        "crashes": collisions["total_crashes"] if collisions else 0,
        "persons_injured": collisions["persons_injured"] if collisions else 0,
        "persons_killed": collisions["persons_killed"] if collisions else 0,
        "pedestrians_injured": collisions["pedestrians_injured"] if collisions else 0,
        "pedestrians_killed": collisions["pedestrians_killed"] if collisions else 0,
        "cyclists_injured": collisions["cyclists_injured"] if collisions else 0,
        "shooting_incidents": shootings["total_incidents"] if shootings else 0,
        "shooting_victims": shootings["total_victims"] if shootings else 0,
        "shooting_murders": shootings["murders"] if shootings else 0,
        "hpd_complaints": hpd_total,
        "hpd_heat_hot_water": heat_hw,
        "hpd_heat_pct": round(heat_hw / hpd_total * 100, 1) if hpd_total else 0,
        "hpd_bronx_pct": round(bronx / hpd_total * 100, 1) if hpd_total else 0,
        "hpd_open_pct": round(open_count / hpd_total * 100, 1) if hpd_total else 0,
        "hpd_immediate_emergency": imm_emergency,
        "vacate_orders_new": vacates["new_orders"] if vacates else 0,
        "vacate_orders_active": vacates["still_active"] if vacates else 0,
        "restaurant_inspections": restaurants["total_inspections"] if restaurants else 0,
        "critical_violations": restaurants["critical_violations"] if restaurants else 0,
        "restaurant_closures": restaurants["closures"] if restaurants else 0,
        "dob_filings": dob["total_filings"] if dob else 0,
        "dob_large_projects_over_1m": dob["large_projects_over_1m"] if dob else 0,
    }


def load_existing_csv():
    """Load existing weekly trends CSV."""
    csv_path = os.path.join(OUTPUT_DIR, "weekly-trends.csv")
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, "r") as f:
        return list(csv.DictReader(f))


def save_csv(rows):
    """Save weekly trends CSV."""
    csv_path = os.path.join(OUTPUT_DIR, "weekly-trends.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Saved {len(rows)} weeks to {csv_path}")


def compute_aggregates(rows):
    """Compute monthly and YTD aggregates from weekly rows."""
    if not rows:
        return {"monthly": {}, "ytd": {}}

    numeric_cols = [c for c in CSV_COLUMNS if c != "week_ending"]

    # Group by month
    monthly = {}
    for row in rows:
        month_key = row["week_ending"][:7]  # YYYY-MM
        if month_key not in monthly:
            monthly[month_key] = {c: 0 for c in numeric_cols}
            monthly[month_key]["weeks"] = 0
        monthly[month_key]["weeks"] += 1
        for c in numeric_cols:
            val = float(row.get(c, 0) or 0)
            # For percentages, we'll average rather than sum
            if c.endswith("_pct"):
                monthly[month_key][c] += val
            else:
                monthly[month_key][c] += val

    # Average the percentages
    for month_key, data in monthly.items():
        weeks = data["weeks"]
        for c in numeric_cols:
            if c.endswith("_pct") and weeks > 0:
                data[c] = round(data[c] / weeks, 1)

    # YTD: current year
    current_year = datetime.now().strftime("%Y")
    ytd_rows = [r for r in rows if r["week_ending"].startswith(current_year)]
    ytd = {c: 0 for c in numeric_cols}
    ytd["weeks"] = len(ytd_rows)
    for row in ytd_rows:
        for c in numeric_cols:
            val = float(row.get(c, 0) or 0)
            if c.endswith("_pct"):
                ytd[c] += val
            else:
                ytd[c] += val
    # Average percentages
    if ytd["weeks"] > 0:
        for c in numeric_cols:
            if c.endswith("_pct"):
                ytd[c] = round(ytd[c] / ytd["weeks"], 1)

    return {"monthly": monthly, "ytd": ytd}


def save_dashboard_json(rows, aggregates):
    """Save JSON for the dashboard to consume."""
    json_path = os.path.join(OUTPUT_DIR, "weekly-trends.json")
    with open(json_path, "w") as f:
        json.dump({
            "weekly": rows,
            "monthly": aggregates["monthly"],
            "ytd": aggregates["ytd"],
            "generated": datetime.now().isoformat(),
        }, f)
    print(f"  Saved dashboard JSON to {json_path}")


def run_scan():
    """Run the full weekly scan, append to CSV, and generate dashboard data."""
    week_ending = datetime.now().strftime("%Y-%m-%d")
    print(f"NYC Open Data Weekly Scan — week ending {week_ending}")
    print("=" * 60)

    print("\n[Collisions] Scanning motor vehicle crashes...")
    collisions = scan_collisions()
    if collisions:
        print(f"  {collisions['total_crashes']} crashes, {collisions['persons_killed']} killed")

    print("\n[Shootings] Scanning shooting incidents...")
    shootings = scan_shootings()
    print(f"  {shootings['total_incidents']} incidents, {shootings['murders']} murders")

    print("\n[HPD] Scanning housing complaints...")
    hpd = scan_hpd_complaints()
    print(f"  {hpd['total_complaints']} complaints")

    print("\n[HPD Vacates] Scanning vacate orders...")
    vacates = scan_hpd_vacates()
    print(f"  {vacates['new_orders']} new, {vacates['still_active']} active")

    print("\n[Restaurants] Scanning restaurant inspections...")
    restaurants = scan_restaurant_inspections()
    print(f"  {restaurants['total_inspections']} inspections, {restaurants['critical_violations']} critical")

    print("\n[DOB] Scanning job filings...")
    dob = scan_dob_filings()
    print(f"  {dob['total_filings']} filings")

    print("\n[Catalog] Scanning recently updated datasets...")
    datasets = get_updated_datasets()
    by_agency = Counter(d["agency"] for d in datasets)
    print(f"  {len(datasets)} datasets updated in past 7 days")

    # Build this week's row
    row = build_week_row(week_ending, collisions, hpd, vacates, restaurants, shootings, dob)

    # Load existing data and append (avoid duplicates)
    existing = load_existing_csv()
    existing_weeks = {r["week_ending"] for r in existing}
    if week_ending in existing_weeks:
        # Replace this week's data
        existing = [r for r in existing if r["week_ending"] != week_ending]
    existing.append(row)
    existing.sort(key=lambda r: r["week_ending"])

    # Save
    print("\n[Output] Writing trend data...")
    save_csv(existing)

    aggregates = compute_aggregates(existing)
    save_dashboard_json(existing, aggregates)

    # Save updated datasets list
    datasets_path = os.path.join(OUTPUT_DIR, "updated-datasets.json")
    with open(datasets_path, "w") as f:
        json.dump({"datasets": datasets, "by_agency": dict(by_agency.most_common()),
                    "scanned": datetime.now().isoformat()}, f)
    print(f"  Saved {len(datasets)} datasets to {datasets_path}")

    print("\n" + "=" * 60)
    print("Weekly scan complete.")


if __name__ == "__main__":
    run_scan()
