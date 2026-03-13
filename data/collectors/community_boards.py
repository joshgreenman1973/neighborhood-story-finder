"""
Community Board meeting collector.
Fetches upcoming and recent meetings from the 59 Community Board WordPress sites.

Each CB runs a site at {borough}cb{n}.cityofnewyork.us using The Events Calendar
plugin, which embeds JSON-LD structured event data and exposes iCal feeds.

We fetch the /events/ page, parse JSON-LD for upcoming meetings, and extract
committee names, meeting types, dates, and agenda links.
"""

import html
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CD_NAMES


def clean_html(text):
    """Strip HTML tags and decode entities from text."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# CB website URLs — WordPress sites with The Events Calendar
CB_SITE_PATTERNS = {
    "1": "https://manhattancb{n}.cityofnewyork.us",
    "2": "https://bronxcb{n}.cityofnewyork.us",
    "3": "https://brooklyncb{n}.cityofnewyork.us",
    "4": "https://queenscb{n}.cityofnewyork.us",
    "5": "https://statenislandcb{n}.cityofnewyork.us",
}

# Fallback: NYC.gov CB pages (older, less structured)
CB_GOV_PATTERNS = {
    "1": "https://www.nyc.gov/site/manhattancb{n}/index.page",
    "2": "https://www.nyc.gov/site/bronxcb{n}/index.page",
    "3": "https://www.nyc.gov/site/brooklyncb{n}/index.page",
    "4": "https://www.nyc.gov/site/queenscb{n}/index.page",
    "5": "https://www.nyc.gov/site/statenislandcb{n}/index.page",
}

HEADERS = {"User-Agent": "NYC-Neighborhood-Story-Finder/1.0"}
TIMEOUT = 12

# Classify meetings by committee type
COMMITTEE_PATTERNS = {
    "full board":      r"full\s*board|general\s*(?:board\s*)?meeting",
    "land use":        r"land\s*use|zoning|ulurp",
    "transportation":  r"transport|traffic|pedestrian",
    "public safety":   r"public\s*safety|police|nypd|safety",
    "housing":         r"housing|tenant|landlord",
    "sanitation":      r"sanitation|environment|clean",
    "parks":           r"parks|recreation|waterfront|open\s*space",
    "health":          r"health|hospital|senior|youth",
    "education":       r"education|school|youth",
    "budget":          r"budget|finance|fiscal",
    "SLA/licensing":   r"sla|liquor|license|licensing|sidewalk\s*caf",
    "executive":       r"executive\s*(?:committee|session|board)",
}


def _classify_meeting(title):
    """Classify a meeting title into a committee type."""
    title_lower = title.lower()
    for committee, pattern in COMMITTEE_PATTERNS.items():
        if re.search(pattern, title_lower):
            return committee
    return "other"


def _parse_json_ld_events(soup):
    """Extract events from JSON-LD script tags (The Events Calendar format)."""
    events = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            # Could be a single event or a list
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Event":
                    events.append({
                        "name": item.get("name", ""),
                        "start": item.get("startDate", ""),
                        "end": item.get("endDate", ""),
                        "description": clean_html(item.get("description") or "")[:300],
                        "location": "",
                        "url": item.get("url", ""),
                    })
                    loc = item.get("location", {})
                    if isinstance(loc, dict):
                        events[-1]["location"] = loc.get("name", "")
        except (json.JSONDecodeError, TypeError):
            continue
    return events


def _parse_event_list(soup):
    """Fallback: extract events from HTML event list elements."""
    events = []
    # The Events Calendar renders events with specific classes
    for article in soup.select(".tribe-events-calendar-list__event, .type-tribe_events, .tribe_events"):
        title_el = article.select_one(
            ".tribe-events-calendar-list__event-title a, "
            ".tribe-events-list-event-title a, "
            ".tribe-event-url, h2 a, h3 a"
        )
        date_el = article.select_one(
            ".tribe-events-calendar-list__event-datetime, "
            "time, .tribe-event-date-start, .tribe-events-schedule"
        )

        if title_el:
            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            events.append({
                "name": title,
                "start": date_str,
                "end": "",
                "description": "",
                "location": "",
                "url": url,
            })
    return events


def fetch_cb_meetings(cd_code):
    """
    Fetch upcoming and recent meetings for a community board.
    Returns structured meeting data with committee classification.
    """
    boro = cd_code[0]
    num = int(cd_code[1:])

    site_pattern = CB_SITE_PATTERNS.get(boro)
    if not site_pattern:
        return None

    base_url = site_pattern.replace("{n}", str(num))
    events_url = f"{base_url}/events/"

    result = {
        "cd_code": cd_code,
        "name": CD_NAMES.get(cd_code, f"CD {cd_code}"),
        "url": base_url,
        "events_url": events_url,
        "meetings": [],
        "committees_active": [],
        "topics": [],
        "next_meeting": None,
        "source": "cb_website",
    }

    try:
        resp = requests.get(events_url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            # Try the main page
            resp = requests.get(base_url, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code != 200:
                return _fetch_cb_fallback(cd_code, result)

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try JSON-LD first (best structured data)
        events = _parse_json_ld_events(soup)

        # Fallback to HTML parsing if no JSON-LD
        if not events:
            events = _parse_event_list(soup)

        # Also try the main page if events page was sparse
        if len(events) < 2 and resp.url != base_url:
            try:
                main_resp = requests.get(base_url, headers=HEADERS, timeout=TIMEOUT)
                if main_resp.status_code == 200:
                    main_soup = BeautifulSoup(main_resp.text, "html.parser")
                    events.extend(_parse_json_ld_events(main_soup))
            except Exception:
                pass

        # Process events
        now = datetime.utcnow()
        seen_names = set()
        for ev in events:
            name = ev["name"].strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            # Parse start date
            start_date = None
            for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"]:
                try:
                    start_date = datetime.strptime(ev["start"][:19], fmt[:19] if "T" in fmt else fmt)
                    break
                except (ValueError, IndexError):
                    continue

            committee = _classify_meeting(name)

            meeting = {
                "title": name,
                "committee": committee,
                "date": start_date.strftime("%Y-%m-%d") if start_date else ev["start"][:10],
                "location": ev.get("location", ""),
                "url": ev.get("url", ""),
                "description": clean_html(ev.get("description", ""))[:200],
            }

            # Determine if upcoming or recent
            if start_date:
                days_away = (start_date.replace(tzinfo=None) - now).days
                meeting["days_away"] = days_away

            result["meetings"].append(meeting)

            if committee != "other" and committee not in result["committees_active"]:
                result["committees_active"].append(committee)

        # Sort: upcoming first (positive days_away), then recent (negative)
        result["meetings"].sort(
            key=lambda m: (0 if m.get("days_away", 0) >= 0 else 1, abs(m.get("days_away", 999)))
        )

        # Cap at 15 meetings
        result["meetings"] = result["meetings"][:15]

        # Set next meeting
        upcoming = [m for m in result["meetings"] if m.get("days_away", -1) >= 0]
        if upcoming:
            result["next_meeting"] = upcoming[0]["date"]

        # Extract topics from meeting titles and descriptions
        topic_keywords = {
            "housing": ["housing", "tenant", "landlord", "rent", "eviction", "affordable", "shelter"],
            "development": ["zoning", "rezoning", "land use", "ulurp", "development", "construction"],
            "safety": ["public safety", "crime", "police", "nypd", "gun", "violence"],
            "noise": ["noise", "nightlife", "club", "bar", "music"],
            "transit": ["transportation", "traffic", "parking", "bike", "bus", "subway", "pedestrian"],
            "sanitation": ["sanitation", "trash", "litter", "rat", "rodent", "clean"],
            "environment": ["parks", "green space", "environment", "tree", "flooding", "waterfront"],
            "infrastructure": ["street", "sidewalk", "pothole", "water main", "sewer"],
            "health": ["health", "hospital", "mental health", "senior", "substance"],
            "education": ["school", "education", "youth", "library"],
        }

        all_text = " ".join(
            f"{m['title']} {m.get('description', '')}" for m in result["meetings"]
        ).lower()

        for topic, keywords in topic_keywords.items():
            for kw in keywords:
                if kw in all_text:
                    result["topics"].append(topic)
                    break

        return result

    except Exception as e:
        print(f"  Warning: CB site error for {cd_code}: {e}")
        return _fetch_cb_fallback(cd_code, result)


def _fetch_cb_fallback(cd_code, result):
    """Fallback: try the NYC.gov page if the CB site is down."""
    boro = cd_code[0]
    num = int(cd_code[1:])

    gov_pattern = CB_GOV_PATTERNS.get(boro)
    if not gov_pattern:
        return result

    url = gov_pattern.replace("{n}", str(num))
    result["url"] = url
    result["source"] = "nyc_gov"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            return result

        text = BeautifulSoup(resp.text, "html.parser").get_text(separator=" ", strip=True)

        # Try to find meeting dates
        for pattern in [
            r"(?:next|upcoming)\s+(?:full\s+board\s+)?meeting[:\s]*(\w+\s+\d{1,2},?\s*\d{4})",
            r"(\w+\s+\d{1,2},?\s*202[5-7])",
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                for fmt in ["%B %d, %Y", "%B %d %Y", "%b %d, %Y"]:
                    try:
                        result["next_meeting"] = datetime.strptime(match.group(1).strip(), fmt).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                if result["next_meeting"]:
                    break

        return result

    except Exception:
        return result


def collect():
    """Main entry point. Returns dict of cd_code → meeting info."""
    print("[CB] Fetching community board meetings...")
    results = {}

    for cd_code in sorted(CD_NAMES.keys()):
        print(f"  CB {cd_code} ({CD_NAMES[cd_code]})...")
        info = fetch_cb_meetings(cd_code)
        if info:
            results[cd_code] = info

    total_meetings = sum(len(r.get("meetings", [])) for r in results.values())
    boards_with_meetings = sum(1 for r in results.values() if r.get("meetings"))
    print(f"[CB] Got {total_meetings} meetings from {boards_with_meetings}/{len(results)} boards")
    return results


if __name__ == "__main__":
    results = collect()
    for cd, info in sorted(results.items()):
        meetings = info.get("meetings", [])
        committees = ", ".join(info.get("committees_active", [])) or "none"
        next_mtg = info.get("next_meeting", "unknown")
        print(f"  CB {cd}: {len(meetings)} meetings, committees=[{committees}], next={next_mtg}")
        for m in meetings[:3]:
            print(f"    {m['date']} | {m['committee']} | {m['title'][:60]}")
