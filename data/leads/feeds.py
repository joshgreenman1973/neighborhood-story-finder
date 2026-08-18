"""
D. District-level feeds that are timely enough to matter, plus fusion of the
signals already maintained across Josh's other trackers.

  Land use (ZAP) ............ hgx4-8ukb  active applications with a milestone in 60 days
  City Record notices ....... joshgreenman1973/experiments city-record-daily (public hearings etc.
                              matched to districts by neighborhood name), 14 days
  Sidewalk sheds ............ joshgreenman1973/nyc-sidewalk-sheds cd.json (context)

Dead-by-design feeds are excluded on purpose: NYPD shootings and 911 calls
have no current data (quarterly / none since Dec 2025); collisions lag 6-10
weeks and their fatality counts fill in later still; DOB stalled-site complaints
stopped in Dec 2024; CouncilStat's constituent log stopped updating; the CB
WordPress scrape returns nothing from CI.
"""

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from common import (DistrictLocator, cd_from_3digit, data_end, fetch, iso, neighborhoods_for, soql,
                    soql_all, where_between, window, CD_NAMES, BORO_NAME)

RAW_EXPERIMENTS = "https://raw.githubusercontent.com/joshgreenman1973/experiments/main"
RAW_SHEDS = "https://raw.githubusercontent.com/joshgreenman1973/nyc-sidewalk-sheds/main/data/cd.json"


def crashes(end, locator):
    """Collisions publish 6-10 weeks late. Use the newest 28 days that exist and
    say so, instead of reporting a fake zero for 'this week'."""
    latest = soql("h9gi-nx95", select="max(crash_date) as d")[0].get("d")
    if not latest:
        return None
    last = date.fromisoformat(latest[:10]) - timedelta(days=3)   # trailing days are still filling in
    s, e = window(last, 28)
    ys, ye = s - timedelta(days=364), e - timedelta(days=364)
    sel = "crash_date, latitude, longitude, number_of_persons_injured, number_of_persons_killed, number_of_pedestrians_injured, number_of_pedestrians_killed, number_of_cyclist_injured, number_of_cyclist_killed, on_street_name, cross_street_name, borough"
    cur = soql_all("h9gi-nx95", select=sel, where=f"{where_between('crash_date', s, e)} AND latitude IS NOT NULL", page=50000)
    prev = soql_all("h9gi-nx95", select=sel, where=f"{where_between('crash_date', ys, ye)} AND latitude IS NOT NULL", page=50000)

    def agg(rows):
        d = defaultdict(lambda: {"crashes": 0, "injured": 0, "killed": 0, "ped_inj": 0, "cyc_inj": 0})
        deaths = []
        for r in rows:
            cd = locator.locate(r.get("longitude"), r.get("latitude"))
            if not cd:
                continue
            a = d[cd]
            a["crashes"] += 1
            k = int(r.get("number_of_persons_killed") or 0)
            a["injured"] += int(r.get("number_of_persons_injured") or 0)
            a["killed"] += k
            a["ped_inj"] += int(r.get("number_of_pedestrians_injured") or 0)
            a["cyc_inj"] += int(r.get("number_of_cyclist_injured") or 0)
            if k:
                deaths.append({"cd": cd, "date": (r.get("crash_date") or "")[:10], "killed": k,
                               "where": " & ".join(x for x in [r.get("on_street_name"), r.get("cross_street_name")] if x).strip() or None,
                               "ped": int(r.get("number_of_pedestrians_killed") or 0), "cyc": int(r.get("number_of_cyclist_killed") or 0)})
        return d, deaths

    c, deaths = agg(cur)
    p, _ = agg(prev)
    by_cd = {}
    for cd in CD_NAMES:
        a, b = c.get(cd, {}), p.get(cd, {})
        by_cd[cd] = {"crashes": a.get("crashes", 0), "injured": a.get("injured", 0), "killed": a.get("killed", 0),
                     "ped_inj": a.get("ped_inj", 0), "cyc_inj": a.get("cyc_inj", 0),
                     "prev_injured": b.get("injured", 0), "prev_crashes": b.get("crashes", 0),
                     "injured_ratio": round(a.get("injured", 0) / max(b.get("injured", 0), 1), 2)}
    print(f"[feeds] crashes: window {iso(s)}..{iso(last)} ({len(cur)} crashes; prior-year {len(prev)}); {len(deaths)} fatal")
    return {"window": {"start": iso(s), "end": iso(last)}, "lag_note": f"Collision data publishes 6-10 weeks late; newest usable date {latest[:10]}.",
            "by_cd": by_cd, "deaths": deaths}


def stalled_sites(end):
    s, e = window(end, 90)
    rows = soql_all("i296-73x5", select="community_board, house_number, street_name, borough_name, date_complaint_received, complaint_number",
                    where=where_between("date_complaint_received", s, e), page=5000)
    by = defaultdict(list)
    for r in rows:
        cd = cd_from_3digit(r.get("community_board"))
        if cd:
            by[cd].append({"address": f"{r.get('house_number', '')} {r.get('street_name', '')}".strip(),
                           "date": (r.get("date_complaint_received") or "")[:10]})
    print(f"[feeds] stalled sites: {len(rows)} new in 90d")
    return {k: sorted(v, key=lambda x: x["date"], reverse=True) for k, v in by.items()}


def land_use(end):
    s, e = window(end, 60)
    rows = soql_all("hgx4-8ukb", select="project_id, project_name, project_brief, ulurp_non, community_district, current_milestone, current_milestone_date, project_status, borough",
                    where=f"project_status='Active' AND {where_between('current_milestone_date', s, e)}",
                    order="current_milestone_date DESC", page=5000)
    by = defaultdict(list)
    for r in rows:
        for tok in re.split(r"[;,]\s*", r.get("community_district") or ""):
            m = re.match(r"([MXKQR])(\d{2})", tok.strip())
            if not m:
                continue
            cd = {"M": "1", "X": "2", "K": "3", "Q": "4", "R": "5"}[m.group(1)] + m.group(2)
            if cd in CD_NAMES:
                by[cd].append({"name": r.get("project_name"), "brief": (r.get("project_brief") or "")[:240],
                               "milestone": r.get("current_milestone"), "date": (r.get("current_milestone_date") or "")[:10],
                               "ulurp": r.get("ulurp_non"), "url": f"https://zap.planning.nyc.gov/projects/{r.get('project_id')}"})
    print(f"[feeds] land use: {len(rows)} active projects with milestone in 60d")
    return dict(by)


_CB_PAT = re.compile(r"\b(manhattan|bronx|brooklyn|queens|staten island)\b.*?\bcommunity (?:board|district)\s*#?\s*(\d{1,2})\b|\bcommunity (?:board|district)\s*#?\s*(\d{1,2})\b.*?\b(manhattan|bronx|brooklyn|queens|staten island)\b", re.I)
_BORO = {"manhattan": "1", "bronx": "2", "brooklyn": "3", "queens": "4", "staten island": "5"}


def _name_index():
    idx = []
    for cd in CD_NAMES:
        for n in neighborhoods_for(cd):
            if len(n) >= 5 and n not in ("clinton", "midtown", "downtown", "chelsea"):
                idx.append((re.compile(r"\b" + re.escape(n) + r"\b", re.I), cd, n))
    return idx


def city_record(end):
    """Notices from the last 14 days, matched to districts by explicit CB mention or neighborhood name."""
    idx = _name_index()
    by = defaultdict(list)
    seen = set()
    n_days = 0
    for i in range(14):
        d = end - timedelta(days=i)
        try:
            j = fetch(f"{RAW_EXPERIMENTS}/city-record-daily/data/{iso(d)}.json", attempts=1)
        except Exception:
            continue
        n_days += 1
        for n in j.get("notices", []):
            title = n.get("short_title") or ""
            text = f"{title} {n.get('description') or ''}"
            key = n.get("request_id") or title
            if key in seen:
                continue
            cds = set()
            for m in _CB_PAT.finditer(text):
                boro = (m.group(1) or m.group(4) or "").lower()
                num = m.group(2) or m.group(3)
                if boro and num:
                    cd = _BORO[boro] + f"{int(num):02d}"
                    if cd in CD_NAMES:
                        cds.add(cd)
            if not cds:
                for pat, cd, _ in idx:
                    if pat.search(text):
                        cds.add(cd)
            if not cds or len(cds) > 4:
                continue
            seen.add(key)
            for cd in cds:
                by[cd].append({"date": (n.get("start_date") or "")[:10], "agency": n.get("agency_name"),
                               "type": n.get("type_of_notice_description"), "title": title[:200],
                               "event_date": (n.get("event_date") or "")[:10] or None})
    print(f"[feeds] city record: {n_days} days read, {sum(len(v) for v in by.values())} district-matched notices")
    return dict(by)


def sheds():
    try:
        rows = fetch(RAW_SHEDS, attempts=2)
    except Exception as e:
        print(f"[feeds] sheds unavailable: {e}")
        return {}
    return {r["cd"]: {"sheds": r.get("sheds"), "zombies": r.get("zombies")} for r in rows if r.get("cd") in CD_NAMES}


def collect_feeds(end=None):
    end = end or data_end()
    locator = DistrictLocator()
    out = {"as_of": iso(end)}
    # crashes() and stalled_sites() are kept for reference but not run: the
    # collisions file lags 6-10 weeks and its fatality field fills in even later
    # (zero deaths in the newest four weeks when the true figure is ~20), and
    # DOB stalled-site complaints stopped in Dec 2024. Neither can support an
    # early-warning claim, so neither is published.
    out["land_use"] = land_use(end)
    out["city_record"] = city_record(end)
    out["sheds"] = sheds()
    return out


if __name__ == "__main__":
    import json
    r = collect_feeds()
    json.dump(r, open("/tmp/feeds_dev.json", "w"), indent=1)
    print({k: (len(v) if isinstance(v, dict) else v) for k, v in r.items() if k != "crashes"})
