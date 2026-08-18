"""
A. Coverage-gap check.

For each candidate lead, ask: has anyone written this yet? Two passes —
  1. Google News RSS search scoped to the last six weeks (place address, or
     neighborhood names + topic keywords), which reaches every outlet Google
     indexes including the Post, Daily News, NY1, PIX11, Patch and the weeklies.
  2. The local-outlet RSS feeds this project already reads (THE CITY, Gothamist,
     Hell Gate, City Limits, Streetsblog, ...), keyword-matched.

A lead's final rank is signal x (1 - 0.75 * coverage): a strong signal nobody
has covered outranks a stronger one that already made the papers. When the
search backend is unreachable the lead is marked coverage=unknown and ranked on
signal alone — the pipeline never invents a "no coverage" verdict.
"""

import html
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from common import DATA_DIR, UA, cd_search_names
sys.path.insert(0, DATA_DIR)
from config import NEWS_FEEDS  # noqa: E402

GNEWS = "https://news.google.com/rss/search"
LOOKBACK_DAYS = 42
SLEEP = 2.0

# complaint type -> search keywords (lowercase). Fallback is the type itself.
TOPIC_KEYWORDS = {
    "Noise - Residential": ["noise"], "Noise - Street/Sidewalk": ["noise"], "Noise - Commercial": ["noise", "bar"],
    "Noise - Vehicle": ["noise", "cars"], "Noise": ["noise"], "Noise - Park": ["noise", "park"],
    "HEAT/HOT WATER": ["heat", "hot water"], "Heat/Hot Water": ["heat", "hot water"],
    "Illegal Parking": ["parking"], "Blocked Driveway": ["parking"], "Abandoned Vehicle": ["abandoned cars"],
    "Rodent": ["rats"], "UNSANITARY CONDITION": ["conditions", "landlord"], "Unsanitary Condition": ["landlord"],
    "Street Condition": ["potholes", "street"], "Sidewalk Condition": ["sidewalk"], "Sewer": ["sewer", "flooding"],
    "Sewer Maintenance": ["sewer", "flooding"], "Water System": ["water main"], "Water Maintenance": ["water main"],
    "Homeless Person Assistance": ["homeless"], "Encampment": ["encampment", "homeless"],
    "Drug Activity": ["drugs"], "Illegal Fireworks": ["fireworks"], "Dirty Condition": ["trash", "sanitation"],
    "Missed Collection": ["trash", "sanitation"], "Illegal Dumping": ["dumping"], "Graffiti": ["graffiti"],
    "Building/Use": ["illegal", "construction"], "General Construction/Plumbing": ["construction"],
    "Derelict Vehicles": ["abandoned cars"], "Traffic Signal Condition": ["traffic light"],
    "Street Light Condition": ["street lights"], "Dead/Dying Tree": ["trees"], "Damaged Tree": ["tree"],
    "Non-Emergency Police Matter": ["police"], "Panhandling": ["panhandling"], "Smoking": ["smoking", "cannabis"],
    "Elevator": ["elevator"], "PLUMBING": ["plumbing"], "Plumbing": ["plumbing"], "Mold": ["mold"],
    "Air Quality": ["air quality", "smoke"], "Indoor Air Quality": ["air quality"], "Asbestos": ["asbestos"],
    "Consumer Complaint": ["store"], "Food Establishment": ["restaurant"], "Bike/Roller/Skate Chronic": ["e-bikes"],
    "Animal-Abuse": ["animal"], "Unsanitary Animal Pvt Property": ["animals"], "Taxi Complaint": ["taxi"],
    "For Hire Vehicle Complaint": ["uber"], "Bus Stop Shelter Complaint": ["bus"], "Outdoor Dining": ["outdoor dining"],
    "Scaffold Safety": ["scaffolding"], "Sidewalk Shed": ["sidewalk shed"], "Lead": ["lead paint"],
    "Water Quality": ["water"], "Green Taxi Complaint": ["taxi"], "Highway Condition": ["highway"],
    "Street Sign - Missing": ["street sign"], "Curb Condition": ["curb"], "Root/Sewer/Sidewalk Condition": ["sidewalk"],
    "New Tree Request": ["trees"], "Overgrown Tree/Branches": ["trees"], "Maintenance or Facility": ["park"],
    "Violation of Park Rules": ["park"], "Obstruction": ["sidewalk"], "Vending": ["vendors"], "Illegal Posting": ["posters"],
    "Standing Water": ["standing water", "mosquito"], "Mosquitoes": ["mosquito"], "Water Leak": ["leak"],
    "ELECTRIC": ["electric"], "GENERAL": ["landlord"], "PAINT/PLASTER": ["landlord"], "DOOR/WINDOW": ["landlord"],
    "FLOORING/STAIRS": ["landlord"], "APPLIANCE": ["landlord"], "SAFETY": ["landlord"], "OUTSIDE BUILDING": ["landlord"],
    "Special Enforcement": ["airbnb", "illegal hotel"], "Emergency Response Team (ERT)": ["building"],
    "Real Time Enforcement": ["construction"], "Boilers": ["boiler"], "Electrical": ["electrical"],
    "Cranes and Derricks": ["crane"], "Investigations and Discipline (IAD)": ["DOB"], "Plumbing": ["plumbing"],
    "Illegal Tree Damage": ["tree"], "Broken Parking Meter": ["parking meter"], "Broken Muni Meter": ["parking meter"],
    "Dead Animal": ["dead animal"], "Litter Basket Complaint": ["litter"], "Overflowing Litter Baskets": ["litter", "trash"],
    "Residential Disposal Complaint": ["trash"], "Commercial Disposal Complaint": ["trash"], "Snow or Ice": ["snow"],
    "Sanitation Worker or Vehicle Complaint": ["sanitation"], "Electronics Waste Appointment": ["e-waste"],
    "Street Sweeping Complaint": ["street sweeping"], "Institution Disposal Complaint": ["trash"],
    "Lost Property": ["police"], "Traffic": ["traffic"], "Homeless Encampment": ["encampment"],
    "Urinating in Public": ["public urination"], "Drinking": ["drinking"], "Disorderly Youth": ["teens"],
    "Illegal Animal Kept as Pet": ["animals"], "Harboring Bees/Wasps": ["bees"], "Rodent": ["rats"],
    "Cannabis": ["cannabis", "smoke shop"], "Tobacco": ["smoke shop"], "Illegal Cannabis Sales": ["cannabis", "smoke shop"],
    "Poison Ivy": ["poison ivy"], "Beach/Pool/Sauna Complaint": ["pool"], "Public Toilet": ["public toilet"],
    "Construction Safety Enforcement": ["construction"], "Building Marshals office": ["construction"],
    "DEP Sidewalk Condition": ["sidewalk"], "DEP Highway Condition": ["highway"], "Sewer Backup": ["sewer backup", "flooding"],
    "Catch Basin": ["catch basin", "flooding"], "Bridge Condition": ["bridge"], "Ferry Inquiry": ["ferry"],
    "Bike Rack Condition": ["bike"], "E-Scooter": ["e-scooter"], "Abandoned Bike": ["bike"], "Bike Lane": ["bike lane"],
    "Mobile Food Vendor": ["food vendors"], "Food Poisoning": ["food poisoning"], "Trans Fat": ["restaurant"],
    "Smoking or Vaping": ["vaping"], "Day Care": ["day care"], "School Maintenance": ["school"], "Sweeping/Missed": ["street sweeping"],
    "Sweeping/Inadequate": ["street sweeping"], "Missed Collection (All Materials)": ["trash pickup"],
    "Dumpster Complaint": ["dumpster"], "Derelict Bicycle": ["bikes"], "Derelict Vehicle": ["abandoned cars"],
    "Illegal Fireworks": ["fireworks"], "Drug Activity": ["drug dealing"], "Squeegee": ["squeegee"],
    "Homeless Street Condition": ["homeless"], "Posting Advertisement": ["posters"], "Fire Alarm - Addition": ["fire"],
    "Radioactive Material": ["radiation"], "Hazardous Materials": ["hazmat"], "Cooling Tower": ["legionella"],
    "Legionella": ["legionella"], "Window Guard": ["window guard"], "Building Drinking Water Tank": ["water tank"],
}


def _q(s):
    return '"' + s.replace('"', "") + '"'


def query_for_place(address, borough, cd):
    """'1220 RANDALL AVENUE', 'Bronx' -> a couple of address spellings."""
    if not address:
        return None
    a = address.title()
    a = re.sub(r"\b(\d+)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), a)
    variants = {a}
    variants.add(re.sub(r"\bAvenue\b", "Ave", a))
    variants.add(re.sub(r"\bStreet\b", "St", a))
    variants.add(re.sub(r"\bBoulevard\b", "Blvd", a))
    q = " OR ".join(_q(v) for v in sorted(variants))
    return f"({q}) {borough}"


def query_for_topic(cd, complaint_type=None, keywords=None):
    names = cd_search_names(cd)
    kws = keywords or TOPIC_KEYWORDS.get(complaint_type) or [w.lower() for w in re.split(r"[/\-]", complaint_type or "") if len(w) > 3][:2]
    place = " OR ".join(_q(n) for n in names[:3])
    topic = " OR ".join(_q(k) for k in kws[:3]) if kws else ""
    return f"({place})" + (f" ({topic})" if topic else "") + " NYC"


def _gnews(query):
    params = {"q": f"{query} when:{LOOKBACK_DAYS}d", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    r = requests.get(GNEWS, params=params, headers=UA, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("Google News rate limit (429)")
    for wait in (6, 15, 30):            # Google News 503s under bursty use; back off
        if r.status_code < 500:
            break
        time.sleep(wait)
        r = requests.get(GNEWS, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title") or "")
        link = it.findtext("link") or ""
        pub = it.findtext("pubDate")
        src = it.find("source")
        outlet = src.text if src is not None else ""
        try:
            dt = parsedate_to_datetime(pub) if pub else None
        except Exception:
            dt = None
        if dt and dt < cutoff:
            continue
        items.append({"title": title, "url": link, "outlet": outlet, "date": dt.date().isoformat() if dt else None})
    return items


class LocalNews:
    """Local outlet RSS, fetched once, keyword-matched per lead."""

    def __init__(self):
        self.items = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
        for f in NEWS_FEEDS:
            try:
                r = requests.get(f["url"], headers=UA, timeout=30)
                r.raise_for_status()
                root = ET.fromstring(r.content)
            except Exception as e:
                print(f"  [coverage] {f['name']} feed failed: {type(e).__name__}", file=sys.stderr)
                continue
            n = 0
            for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
                title = html.unescape(it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or "")
                desc = html.unescape(re.sub(r"<[^>]+>", " ", it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or ""))
                link = it.findtext("link") or ""
                if not link:
                    l = it.find("{http://www.w3.org/2005/Atom}link")
                    link = l.get("href") if l is not None else ""
                pub = it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}published")
                try:
                    dt = parsedate_to_datetime(pub) if pub and "," in pub else (datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None)
                except Exception:
                    dt = None
                if dt and dt < cutoff:
                    continue
                self.items.append({"title": title, "text": (title + " " + desc).lower(), "url": link, "outlet": f["name"],
                                   "date": dt.date().isoformat() if dt else None})
                n += 1
        print(f"[coverage] local RSS: {len(self.items)} recent items from {len(NEWS_FEEDS)} feeds")

    def match(self, place_terms, topic_terms):
        out = []
        pt = [t.lower() for t in place_terms if t]
        tt = [t.lower() for t in topic_terms if t]
        for it in self.items:
            if pt and not any(t in it["text"] for t in pt):
                continue
            if tt and not any(t in it["text"] for t in tt):
                continue
            out.append({k: it[k] for k in ("title", "url", "outlet", "date")})
        return out


class CoverageChecker:
    def __init__(self):
        self.local = LocalNews()
        self.backend_ok = True
        self.calls = 0
        self.consecutive_failures = 0

    def check(self, query, place_terms=(), topic_terms=(), must_match=()):
        """Returns {score 0..1, hits, articles[], status}. Google matches loosely, so
        `must_match` terms are required in the headline for a hit to count."""
        arts = []
        status = "ok"
        if self.backend_ok and query:
            try:
                arts = _gnews(query)
                self.consecutive_failures = 0
                if must_match:
                    mm = [t.lower() for t in must_match if t]
                    arts = [a for a in arts if any(t in (a.get("title") or "").lower() for t in mm)]
                self.calls += 1
                time.sleep(SLEEP)
            except Exception as e:
                print(f"  [coverage] gnews failed ({e}); continuing without", file=sys.stderr)
                self.consecutive_failures += 1
                if "429" in str(e) or self.consecutive_failures >= 4:
                    # throttled: stop hammering; remaining leads are marked coverage=unknown
                    print("  [coverage] Google News unavailable; skipping remaining searches", file=sys.stderr)
                    self.backend_ok = False
                status = "unknown"
        local = self.local.match(place_terms, topic_terms)
        seen = set()
        merged = []
        for a in local + arts:
            k = (a.get("title") or "")[:60].lower()
            if k in seen:
                continue
            seen.add(k)
            merged.append(a)
        weight = len(local) * 1.0 + len(arts) * 0.7
        score = min(1.0, weight / 3.0)
        if status == "unknown" and not local:
            return {"score": None, "hits": 0, "articles": [], "status": "unknown", "query": query}
        return {"score": round(score, 2), "hits": len(merged), "articles": merged[:4], "status": status, "query": query}


if __name__ == "__main__":
    c = CoverageChecker()
    print(c.check(query_for_topic("112", "Noise - Residential"), ["washington heights", "inwood"], ["noise"]))
    print(c.check(query_for_place("1220 RANDALL AVENUE", "Bronx", "202"), ["1220 randall"], []))
