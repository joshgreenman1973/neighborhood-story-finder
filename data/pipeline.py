#!/usr/bin/env python3
"""
NYC Neighborhood Story Finder — Data Pipeline
Orchestrates all collectors and processors to generate static JSON output.

Usage:
    python pipeline.py                   # Full run (all sources + Claude synthesis)
    python pipeline.py --no-claude       # Skip Claude API (use fallback themes)
    python pipeline.py --311-only        # Only fetch 311 data (fastest)
    python pipeline.py --no-cb           # Skip community board scraping (slow)
"""

import sys
import os
import time
import json
import argparse

# Add data/ to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collectors import three11, reddit, news_rss, community_boards
from collectors import budget_requests, land_use, council_services, dob_permits
from processors import trend_detector, theme_extractor, data_compressor
from config import CD_GEOJSON_URL, CD_NAMES


def download_geojson():
    """Download community district boundaries if not already present."""
    import requests

    geo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "geo")
    os.makedirs(geo_dir, exist_ok=True)
    geo_path = os.path.join(geo_dir, "community_districts.geojson")

    if os.path.exists(geo_path):
        size = os.path.getsize(geo_path)
        if size > 1000:
            print(f"[GeoJSON] Already have community_districts.geojson ({size / 1024:.0f} KB)")
            return

    print("[GeoJSON] Downloading community district boundaries...")
    resp = requests.get(CD_GEOJSON_URL, timeout=60,
                        headers={"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"})
    resp.raise_for_status()

    geojson = resp.json()

    # Normalize the CD code property for consistent frontend usage
    # ArcGIS uses "BoroCD", DCP uses "boro_cd"
    valid_features = []
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        boro_cd = props.get("BoroCD") or props.get("boro_cd") or ""
        boro_cd = str(int(boro_cd)) if boro_cd else ""
        if boro_cd and boro_cd in CD_NAMES:
            feature["properties"]["cd_code"] = boro_cd
            feature["properties"]["name"] = CD_NAMES.get(boro_cd, f"District {boro_cd}")
            valid_features.append(feature)
    geojson["features"] = valid_features
    print(f"[GeoJSON] {len(valid_features)} valid community district polygons")

    with open(geo_path, "w") as f:
        json.dump(geojson, f)

    print(f"[GeoJSON] Saved ({os.path.getsize(geo_path) / 1024:.0f} KB)")


def main():
    parser = argparse.ArgumentParser(description="NYC Neighborhood Story Finder pipeline")
    parser.add_argument("--no-claude", action="store_true", help="Skip Claude API synthesis")
    parser.add_argument("--311-only", action="store_true", help="Only fetch 311 data")
    parser.add_argument("--no-cb", action="store_true", help="Skip community board scraping")
    args = parser.parse_args()

    start = time.time()
    print("=" * 60)
    print("NYC NEIGHBORHOOD STORY FINDER — DATA PIPELINE")
    print("=" * 60)
    print()

    # Phase 0: Ensure GeoJSON exists
    download_geojson()
    print()

    # Phase 1: Collect 311 data
    records, district_311, sparklines = three11.collect()
    print()

    # Phase 2: Collect other sources
    reddit_posts = []
    news_articles = []
    cb_data = {}
    budget_data = {}
    land_use_data = {}
    council_data = {}
    dob_data = {}

    if not args.__dict__.get("311_only"):
        try:
            reddit_posts = reddit.collect()
        except Exception as e:
            print(f"[Reddit] Error: {e}")
        print()

        try:
            news_articles = news_rss.collect()
        except Exception as e:
            print(f"[News] Error: {e}")
        print()

        if not args.no_cb:
            try:
                cb_data = community_boards.collect()
            except Exception as e:
                print(f"[CB] Error: {e}")
            print()

        # Phase 2b: Government/development sources
        try:
            budget_data = budget_requests.fetch_budget_requests()
        except Exception as e:
            print(f"[Budget] Error: {e}")
        print()

        try:
            land_use_data = land_use.fetch_land_use()
        except Exception as e:
            print(f"[Land Use] Error: {e}")
        print()

        try:
            council_data = council_services.fetch_council_services()
        except Exception as e:
            print(f"[CouncilStat] Error: {e}")
        print()

        try:
            dob_data = dob_permits.fetch_dob_permits()
        except Exception as e:
            print(f"[DOB] Error: {e}")
        print()

    # Phase 3: Detect trends
    spikes, activity_scores = trend_detector.detect_all(district_311)
    print()

    # Phase 4: Synthesize themes
    if args.no_claude:
        os.environ.pop("ANTHROPIC_API_KEY", None)

    themes = theme_extractor.synthesize_all(
        district_311, spikes, reddit_posts, news_articles, cb_data,
        budget_data, land_use_data, council_data, dob_data
    )
    print()

    # Phase 5: Generate output
    data_compressor.generate_all(
        district_311, spikes, activity_scores, themes, sparklines,
        reddit_posts, news_articles, cb_data,
        budget_data, land_use_data, council_data, dob_data
    )

    elapsed = time.time() - start
    print()
    print(f"Pipeline complete in {elapsed:.0f} seconds")
    print(f"Output in: {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')}")


if __name__ == "__main__":
    main()
