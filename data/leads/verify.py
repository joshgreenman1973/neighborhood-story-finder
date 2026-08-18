"""
Independent re-check of what leads.json publishes. Re-queries the APIs with
simple, separately written SoQL (no shared code paths with the pipeline beyond
the HTTP fetch) and diffs every headline number for the top leads.

    LEADS_AS_OF=2026-08-17 python data/leads/verify.py [--n 25]

Exit code 1 if any check fails. Reads data/output/leads.json.
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "output")
NYC = "https://data.cityofnewyork.us/resource"
BORO = {"1": "MANHATTAN", "2": "BRONX", "3": "BROOKLYN", "4": "QUEENS", "5": "STATEN ISLAND"}


def q(ds, **params):
    p = {"$" + k: v for k, v in params.items()}
    r = requests.get(f"{NYC}/{ds}.json", params=p, timeout=120, headers={"User-Agent": "leads-verify/1.0"})
    r.raise_for_status()
    return r.json()


def count(ds, where):
    rows = q(ds, select="count(*) as n", where=where)
    return int(rows[0]["n"]) if rows else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25)
    args = ap.parse_args()
    d = json.load(open(os.path.join(OUT, "leads.json")))
    end = date.fromisoformat(d["as_of"])
    e14 = end + timedelta(days=1)
    s14 = e14 - timedelta(days=14)
    s30 = e14 - timedelta(days=30)
    s60 = e14 - timedelta(days=60)
    s28 = e14 - timedelta(days=28)
    s56 = e14 - timedelta(days=56)
    ok = fail = 0
    results = []

    def check(label, published, actual, tol=0):
        nonlocal ok, fail
        good = abs(int(published) - int(actual)) <= tol
        ok += good
        fail += (not good)
        results.append((label, published, actual, good))
        print(("PASS" if good else "FAIL"), label, "published", published, "actual", actual)

    for l in d["leads"][:args.n]:
        if l["kind"] == "place" and l.get("bbl"):
            b = l["bbl"]
            src = l["sources"]
            if "311" in src:
                n = count("erm2-nwe9", f"bbl='{b}' AND created_date >= '{s14}' AND created_date < '{e14}'")
                check(f"311 n14 {l['address']}", src["311"]["n14"], n)
            if "hpd_violations" in src:
                n = count("wvxf-dwi5", f"boroid='{b[0]}' AND block='{int(b[1:6])}' AND lot='{int(b[6:])}' AND novissueddate >= '{s30}' AND novissueddate < '{e14}'")
                check(f"HPD viol n30 {l['address']}", src["hpd_violations"]["n30"], n)
                n = count("wvxf-dwi5", f"boroid='{b[0]}' AND block='{int(b[1:6])}' AND lot='{int(b[6:])}' AND class='C' AND novissueddate >= '{s30}' AND novissueddate < '{e14}'")
                check(f"HPD class C {l['address']}", src["hpd_violations"]["class_c"], n)
            if "evictions" in src:
                n = count("6z8x-wfk4", f"bbl='{b}' AND executed_date >= '{s60}' AND executed_date < '{e14}'")
                check(f"evictions n60 {l['address']}", src["evictions"]["n60"], n)
            if "vacate_orders" in src:
                n = count("tb8q-a3ar", f"bbl='{b}' AND vacate_effective_date >= '{s60}' AND vacate_effective_date < '{e14}'")
                check(f"vacates {l['address']}", len(src["vacate_orders"]["orders"]), n)
        elif l["kind"] == "district":
            a = l["stats"]
            cb = f"{int(a['cd'][1:]):02d} {BORO[a['cd'][0]]}"
            t = a["complaint_type"].replace("'", "''")
            n = count("erm2-nwe9", f"community_board='{cb}' AND complaint_type='{t}' AND created_date >= '{s28}' AND created_date < '{e14}'")
            check(f"district cur28 {a['district']} / {a['complaint_type']}", a["cur28"], n)
            # seasonal comparator: same window one year earlier, raw (unscaled) count must be below observed/ratio bound
            n1 = count("erm2-nwe9", f"community_board='{cb}' AND complaint_type='{t}' AND created_date >= '{s28 - timedelta(days=364)}' AND created_date < '{e14 - timedelta(days=364)}'")
            print(f"     context: same window last year raw = {n1}; pipeline seasonal expectation = {a['exp_seasonal']}")
        elif l["kind"] == "novelty":
            m = l["id"].split(":", 2)
            t, desc = m[1].replace("'", "''"), m[2].replace("'", "''")
            n = count("erm2-nwe9", f"complaint_type='{t}' AND descriptor='{desc}' AND created_date >= '{s56}' AND created_date < '{e14}'")
            pub = int(l["why"][0].split()[0])
            check(f"novelty cur56 {m[1]} / {m[2]}", pub, n)

    print(f"\n{ok} passed, {fail} failed")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
