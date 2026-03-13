"""
Community Board meeting collector.
Fetches meeting info from NYC.gov community board pages.
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CD_NAMES


# NYC.gov CB page URLs follow different patterns by borough
CB_URL_PATTERNS = {
    "1": "https://www.nyc.gov/site/manhattancb{n}/index.page",
    "2": "https://www.nyc.gov/site/bronxcb{n}/index.page",
    "3": "https://www.nyc.gov/site/brooklyncb{n}/index.page",
    "4": "https://www.nyc.gov/site/queenscb{n}/index.page",
    "5": "https://www.nyc.gov/site/statenislandcb{n}/index.page",
}

HEADERS = {"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"}


def fetch_cb_page(cd_code):
    """Fetch a community board's NYC.gov page and extract meeting info."""
    boro = cd_code[0]
    num = int(cd_code[1:])

    url_pattern = CB_URL_PATTERNS.get(boro)
    if not url_pattern:
        return None

    url = url_pattern.replace("{n}", str(num))

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract text content for topic analysis
        page_text = soup.get_text(separator=" ", strip=True)

        # Look for meeting-related content
        meeting_info = {
            "cd_code": cd_code,
            "name": CD_NAMES.get(cd_code, f"CD {cd_code}"),
            "url": url,
            "topics": [],
            "next_meeting": None,
        }

        # Extract meeting dates (common patterns on NYC.gov CB pages)
        date_patterns = [
            r"(?:next|upcoming)\s+(?:full\s+board\s+)?meeting[:\s]*(\w+\s+\d{1,2},?\s*\d{4})",
            r"(?:meeting|agenda)\s+(?:date|for)[:\s]*(\w+\s+\d{1,2},?\s*\d{4})",
            r"(\w+\s+\d{1,2},?\s*202[5-7])",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                try:
                    date_str = match.group(1).strip()
                    # Try various date formats
                    for fmt in ["%B %d, %Y", "%B %d %Y", "%b %d, %Y"]:
                        try:
                            meeting_info["next_meeting"] = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
                if meeting_info["next_meeting"]:
                    break

        # Extract topics from page text (look for common CB agenda items)
        topic_keywords = {
            "housing": ["housing", "tenant", "landlord", "rent", "eviction", "affordable"],
            "development": ["zoning", "rezoning", "land use", "ulurp", "development", "construction", "building permit"],
            "safety": ["public safety", "crime", "police", "nypd", "safety"],
            "transit": ["transportation", "traffic", "parking", "bike", "bus", "subway"],
            "quality-of-life": ["sanitation", "noise", "quality of life", "rat", "litter"],
            "environment": ["parks", "green space", "environment", "tree", "flooding"],
            "infrastructure": ["street", "sidewalk", "pothole", "water", "sewer"],
        }

        text_lower = page_text.lower()
        for topic, keywords in topic_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    meeting_info["topics"].append(topic)
                    break

        return meeting_info

    except Exception as e:
        print(f"  Warning: Could not fetch CB page for {cd_code}: {e}")
        return None


def collect():
    """Main entry point. Returns dict of cd_code → meeting info."""
    print("[CB] Fetching community board pages...")
    results = {}

    for cd_code in sorted(CD_NAMES.keys()):
        print(f"  CB {cd_code} ({CD_NAMES[cd_code]})...")
        info = fetch_cb_page(cd_code)
        if info:
            results[cd_code] = info

    print(f"[CB] Got info for {len(results)} community boards")
    return results


if __name__ == "__main__":
    results = collect()
    for cd, info in sorted(results.items()):
        topics = ", ".join(info["topics"][:3]) if info["topics"] else "none detected"
        meeting = info.get("next_meeting", "unknown")
        print(f"  CB {cd}: topics=[{topics}] next_meeting={meeting}")
