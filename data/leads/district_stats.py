"""
Non-311 trends by community district: current window vs the window before it,
for the feeds that are timely enough to say something about this month.

  HPD violations issued ....... wvxf-dwi5   30d vs prior 30d   (boroid + communityboard)
  HPD complaints received ..... ygpa-z7cr   28d vs prior 28d   (borough + community_board)
  DOB complaints .............. eabe-havv   30d vs prior 30d   (community_board '202'; text dates)
  Marshal evictions ........... 6z8x-wfk4   60d vs prior 60d   (borough + community_board)
  HPD vacate orders ........... tb8q-a3ar   60d vs prior 60d   (boro_short_name + community_board)
  HPD litigation opened ....... 59kj-x8nc   30d vs prior 30d   (boroid + community_district)
  DOB job filings ............. w9ak-ipjd   30d vs prior 30d   (commmunity_board '318'); new buildings + full demolitions
  DOB safety violations ....... 855j-jady   30d vs prior 30d   (community_board '204')
  Restaurant closures ......... 43nn-pn8j   30d vs prior 30d   (community_board '103'; action contains 'Closed')
  Deeds recorded (ACRIS) ...... bnx9-e6tj + 8h5j-fqxa + 636b-3b5g + PLUTO 64uk-42ks
                                latest 30 recorded days vs prior 30 (ACRIS runs ~2-3 weeks behind; labelled)
  Major felonies (CompStat) ... joshgreenman1973/nypd-compstat-scraper latest_compstat.json,
                                28-day vs prior year, precincts area-weighted onto districts

Each entry: {cur, prior, ratio}. Ratio is cur/prior (None if prior < 5).
"""

import json
from collections import Counter, defaultdict
from datetime import date, timedelta

from common import (OUTPUT_DIR, cd_from_3digit, cd_from_num, data_end, fetch, iso, soql, soql_all,
                    where_between, window, CD_NAMES)


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


def hpd_litigation(end):
    def f(s, e):
        rows = soql_all("59kj-x8nc", select="boroid, community_district, count(*) as n",
                        where=where_between("caseopendate", s, e), group="boroid, community_district", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_num(r.get("boroid"), r.get("community_district"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 30))


def dob_filings(end):
    """New buildings + full demolitions filed (development pressure)."""
    def f(s, e):
        rows = soql_all("w9ak-ipjd", select="commmunity_board, count(*) as n",
                        where=f"{where_between('filing_date', s, e)} AND job_type in('New Building','Full Demolition')",
                        group="commmunity_board", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_3digit(r.get("commmunity_board"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 30))


def dob_safety_violations(end):
    def f(s, e):
        rows = soql_all("855j-jady", select="community_board, count(*) as n",
                        where=where_between("violation_issue_date", s, e), group="community_board", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_3digit(r.get("community_board"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 30))


def restaurant_closures(end):
    def f(s, e):
        rows = soql_all("43nn-pn8j", select="community_board, count(distinct camis) as n",
                        where=f"{where_between('inspection_date', s, e)} AND action like '%Closed%'",
                        group="community_board", page=5000)
        d = defaultdict(int)
        for r in rows:
            cd = cd_from_3digit(r.get("community_board"))
            if cd:
                d[cd] += int(r["n"])
        return d
    return _pack(*_pair(f, end, 30))


def acris_deeds(end):
    """Deeds recorded per district: latest 30 recorded days vs the 30 before,
    dollar volume, and the buyer names that show up most. ACRIS publishes
    2-3 weeks behind, so windows end at good_through_date, not today."""
    gt = soql("bnx9-e6tj", select="max(good_through_date) as g")[0].get("g")
    if not gt:
        return None
    last = date.fromisoformat(gt[:10])
    s, e = window(last, 30)
    ps = s - timedelta(days=30)
    docs = soql_all("bnx9-e6tj", select="document_id, recorded_datetime, document_amt",
                    where=f"doc_type='DEED' AND {where_between('recorded_datetime', ps, e)}", page=5000, max_rows=50000)
    print(f"[district_stats] ACRIS: {len(docs)} deeds recorded {iso(ps)}..{iso(last)}")
    meta = {d["document_id"]: d for d in docs}
    ids = list(meta.keys())
    # document -> BBL (first legal), BBL -> CD via PLUTO
    doc_bbl = {}
    for i in range(0, len(ids), 120):
        batch = ids[i:i + 120]
        rows = soql("8h5j-fqxa", select="document_id, borough, block, lot",
                    where="document_id in(" + ",".join(f"'{x}'" for x in batch) + ")", limit=5000)
        for r in rows:
            try:
                b = f"{int(r['borough'])}{int(r['block']):05d}{int(r['lot']):04d}"
            except (TypeError, ValueError, KeyError):
                continue
            doc_bbl.setdefault(r["document_id"], b)
    bbls = sorted(set(doc_bbl.values()))
    bbl_cd = {}
    for i in range(0, len(bbls), 150):
        batch = bbls[i:i + 150]
        rows = soql("64uk-42ks", select="bbl, cd", where="bbl in(" + ",".join(f"'{b}.00000000'" for b in batch) + ")", limit=5000)
        for r in rows:
            b = str(r.get("bbl", "")).split(".")[0]
            cd = cd_from_3digit(r.get("cd"))
            if cd:
                bbl_cd[b] = cd
    # condo unit lots are not in PLUTO (only the billing lot is): fall back to block level
    missing = sorted({b for b in bbls if b not in bbl_cd})
    by_boro = defaultdict(set)
    for b in missing:
        by_boro[b[0]].add(int(b[1:6]))
    for boro, blocks in by_boro.items():
        blocks = sorted(blocks)
        for i in range(0, len(blocks), 200):
            batch = blocks[i:i + 200]
            rows = soql("64uk-42ks", select="block, cd, count(*) as n",
                        where=f"borocode='{boro}' AND block in(" + ",".join(f"'{x}'" for x in batch) + ")",
                        group="block, cd", limit=5000)
            best = {}
            for r in rows:
                blk = str(r.get("block"))
                n = int(r.get("n") or 0)
                if n > best.get(blk, (0, None))[0]:
                    best[blk] = (n, cd_from_3digit(r.get("cd")))
            for b in missing:
                if b[0] == boro and b not in bbl_cd:
                    got = best.get(str(int(b[1:6])))
                    if got and got[1]:
                        bbl_cd[b] = got[1]
    # buyers (party_type 2)
    doc_buyer = {}
    for i in range(0, len(ids), 120):
        batch = ids[i:i + 120]
        rows = soql("636b-3b5g", select="document_id, name",
                    where="party_type='2' AND document_id in(" + ",".join(f"'{x}'" for x in batch) + ")", limit=5000)
        for r in rows:
            doc_buyer.setdefault(r["document_id"], (r.get("name") or "").strip())
    cur, prior, amt, buyers = defaultdict(int), defaultdict(int), defaultdict(float), defaultdict(Counter)
    for did, d in meta.items():
        b = doc_bbl.get(did)
        cd = bbl_cd.get(b) if b else None
        if not cd:
            continue
        rd = date.fromisoformat(d["recorded_datetime"][:10])
        if s <= rd < e:
            cur[cd] += 1
            amt[cd] += float(d.get("document_amt") or 0)
            nm = doc_buyer.get(did)
            if nm:
                buyers[cd][nm] += 1
        elif ps <= rd < s:
            prior[cd] += 1
    out = _pack(cur, prior)
    for cd in out:
        out[cd]["dollar_volume"] = round(amt.get(cd, 0.0))
        out[cd]["top_buyers"] = [{"name": n, "deeds": c} for n, c in buyers[cd].most_common(3) if c >= 2]
    unmapped = sum(1 for did in meta if not bbl_cd.get(doc_bbl.get(did) or ""))
    print(f"[district_stats] ACRIS: {len(meta) - unmapped} deeds mapped to districts, {unmapped} unmapped")
    return {"by_cd": out, "window": {"start": iso(s), "end": iso(last)}, "lag_note": f"ACRIS good through {iso(last)}"}


COMPSTAT_URL = "https://raw.githubusercontent.com/joshgreenman1973/nypd-compstat-scraper/main/data/latest_compstat.json"


def compstat(end):
    """Seven major felonies, 28-day current vs prior year, precincts area-weighted onto districts."""
    import os
    try:
        data = fetch(COMPSTAT_URL, attempts=2)
        xw = json.load(open(os.path.join(OUTPUT_DIR, "geo", "precinct_cd_crosswalk.json")))["cd_to_precincts"]
    except Exception as e:
        print(f"[district_stats] CompStat unavailable: {e}")
        return None
    period = None
    by_p = {}
    for k, v in data.items():
        if not k.endswith("Precinct") or not isinstance(v, dict):
            continue
        num = k.split()[0].rstrip("stndrh")
        num = "".join(ch for ch in num if ch.isdigit())
        felonies = v.get("seven_major_felonies", {})
        c = p = 0
        for name, m in felonies.items():
            t = m.get("twenty_eight_day", {})
            c += t.get("current_year") or 0
            p += t.get("prior_year") or 0
        by_p[num] = {"cur": c, "prior": p, "detail": {name: m.get("twenty_eight_day", {}) for name, m in felonies.items()}}
        period = period or v.get("report_period", {})
    out = {}
    for cd in CD_NAMES:
        parts = xw.get(cd, [])
        c = sum(by_p.get(pn, {}).get("cur", 0) * w for pn, w in parts)
        pr = sum(by_p.get(pn, {}).get("prior", 0) * w for pn, w in parts)
        out[cd] = {"cur": round(c), "prior": round(pr), "ratio": round(c / pr, 2) if pr >= 5 else None,
                   "precincts": [{"precinct": pn, "share": w, "cur": by_p.get(pn, {}).get("cur"), "prior": by_p.get(pn, {}).get("prior")} for pn, w in parts]}
    print(f"[district_stats] CompStat: {len(by_p)} precincts, period {period}")
    return {"by_cd": out, "period": period, "note": "precinct 28-day counts, area-weighted onto community districts (approximate)"}


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
    out["hpd_litigation"] = {"label": "HPD litigation opened", "days": 30, "by_cd": hpd_litigation(end)}
    print("[district_stats] HPD litigation done")
    out["dob_filings"] = {"label": "New buildings + demolitions filed", "days": 30, "by_cd": dob_filings(end)}
    print("[district_stats] DOB filings done")
    out["dob_safety"] = {"label": "DOB safety violations", "days": 30, "by_cd": dob_safety_violations(end)}
    print("[district_stats] DOB safety done")
    out["restaurant_closures"] = {"label": "Restaurants closed by DOHMH", "days": 30, "by_cd": restaurant_closures(end)}
    print("[district_stats] restaurant closures done")
    ac = acris_deeds(end)
    if ac:
        out["deeds"] = {"label": "Deeds recorded", "days": 30, "by_cd": ac["by_cd"], "window": ac["window"], "note": ac["lag_note"]}
    cs = compstat(end)
    if cs:
        out["crime"] = {"label": "Major felonies (CompStat, 28d vs prior yr)", "days": 28, "by_cd": cs["by_cd"], "period": cs["period"], "note": cs["note"]}
    return out


if __name__ == "__main__":
    import json
    r = collect_district_stats()
    for k in ("hpd_violations", "evictions"):
        top = sorted(r[k]["by_cd"].items(), key=lambda kv: -(kv[1]["ratio"] or 0))[:5]
        print(k, top)
