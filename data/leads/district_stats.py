"""
Non-311 trends by community district: current window vs the window before it,
for the feeds that are timely enough to say something about this month.

  HPD violations issued ....... wvxf-dwi5   30d vs prior 30d   (boroid + communityboard)
  HPD complaints received ..... ygpa-z7cr   28d vs prior 28d   (borough + community_board)
  DOB complaints .............. eabe-havv   30d vs prior 30d   (community_board '202'; text dates)
  Marshal evictions ........... 6z8x-wfk4   60d vs prior 60d   (borough + community_board)
  HPD vacate orders ........... tb8q-a3ar   60d vs prior 60d   (boro_short_name + community_board)
  OATH/ECB violations ......... 6bgk-3dad   30d vs prior 30d   (no district field: joined via BBL -> CD map from HPD/311)

Each entry: {cur, prior, ratio}. Ratio is cur/prior (None if prior < 5).
"""

from collections import defaultdict
from datetime import date, timedelta

from common import (cd_from_3digit, cd_from_num, data_end, iso, soql_all, where_between, window, CD_NAMES)


def _pair(fetch_fn, end, days):
    s, e = window(end, days)
    ps, pe = s - timedelta(days=days), s
    return fetch_fn(s, e), fetch_fn(ps, pe)


def _pack(cur, prior):
    out = {}
    for cd in CD_NAMES:
        c, p = cur.get(cd, 0), prior.get(cd, 0)
        out[cd] = {"cur": c, "prior": p, "ratio": round(c / p, 2) if p >= 5 else None}
    return out


def hpd_violations(end):
    def f(s, e):
        rows = soql_all("wvxf-dwi5", select="boroid, communityboard, count(*) as n",
                        where=where_between("novissueddate", s, e), group="boroid, communityboard", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_num(r.get("boroid"), r.get("communityboard"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 30))


def hpd_complaints(end):
    def f(s, e):
        rows = soql_all("ygpa-z7cr", select="borough, community_board, count(*) as n",
                        where=where_between("received_date", s, e), group="borough, community_board", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_num(r.get("borough"), r.get("community_board"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 28))


def dob_complaints(end):
    # text dates 'MM/DD/YYYY': pull the months touching both windows, bucket client-side
    s, e = window(end, 30)
    ps = s - timedelta(days=30)
    months = sorted({(ps + timedelta(days=i)).strftime("%m/%%/%Y") for i in range(61)})
    like = " OR ".join(f"date_entered like '{m}'" for m in months)
    rows = soql_all("eabe-havv", select="community_board, date_entered", where=f"({like})", page=50000, max_rows=200000)
    cur, prior = defaultdict(int), defaultdict(int)
    for r in rows:
        try:
            m, d, y = r["date_entered"].split("/")
            dt = date(int(y), int(m), int(d))
        except Exception:
            continue
        cd = cd_from_3digit(r.get("community_board"))
        if not cd:
            continue
        if s <= dt < e:
            cur[cd] += 1
        elif ps <= dt < s:
            prior[cd] += 1
    return _pack(cur, prior)


def evictions(end):
    def f(s, e):
        rows = soql_all("6z8x-wfk4", select="borough, community_board, count(*) as n",
                        where=f"{where_between('executed_date', s, e)} AND residential_commercial_ind='Residential'",
                        group="borough, community_board", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_num(r.get("borough"), r.get("community_board"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 60))


def vacates(end):
    def f(s, e):
        rows = soql_all("tb8q-a3ar", select="boro_short_name, community_board, count(*) as n",
                        where=where_between("vacate_effective_date", s, e), group="boro_short_name, community_board", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_num(r.get("boro_short_name"), r.get("community_board"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 60))


def collect_district_stats(end=None):
    end = end or data_end()
    out = {"as_of": iso(end)}
    out["hpd_violations"] = {"label": "HPD violations issued", "days": 30, "by_cd": hpd_violations(end)}
    print("[district_stats] HPD violations done")
    out["hpd_complaints"] = {"label": "HPD complaints received", "days": 28, "by_cd": hpd_complaints(end)}
    print("[district_stats] HPD complaints done")
    out["dob_complaints"] = {"label": "DOB complaints", "days": 30, "by_cd": dob_complaints(end)}
    print("[district_stats] DOB complaints done")
    out["evictions"] = {"label": "Residential marshal evictions", "days": 60, "by_cd": evictions(end)}
    print("[district_stats] evictions done")
    out["vacates"] = {"label": "HPD vacate orders", "days": 60, "by_cd": vacates(end)}
    print("[district_stats] vacates done")
    return out


if __name__ == "__main__":
    import json
    r = collect_district_stats()
    for k in ("hpd_violations", "evictions"):
        top = sorted(r[k]["by_cd"].items(), key=lambda kv: -(kv[1]["ratio"] or 0))[:5]
        print(k, top)
