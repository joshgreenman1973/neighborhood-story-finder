"""
C. Seasonal-baseline anomaly detection and new-kind-of-complaint (novelty) detection
on 311, at community district x complaint type resolution.

Why: the old detector compared each week with the previous 8 weeks, so every
October produced a "heat spike" and every June a "noise spike". Here the
expected count for a district/type is the SAME 28-day window in each of the
prior three years (weekday-aligned, scaled for citywide volume drift), and a
pair is only flagged when it beats BOTH the seasonal norm and the recent
8-week trend. All aggregation is server-side (SoQL group by).

Novelty: descriptors that barely existed over the prior two years but are
now arriving in volume — cannabis, e-bikes, lithium batteries and shelters all
showed up in 311 text before they showed up in print.
"""

import math
from collections import defaultdict
from datetime import timedelta

from common import (cd_from_311, data_end, iso, soql_all, where_between, window, CD_NAMES)

DS = "erm2-nwe9"
CUR_DAYS = 28
RECENT_DAYS = 56          # the 8 weeks before the current window
SEASONAL_YEARS = (1, 2, 3)
MIN_OBS = 20
MIN_OBS_HAZARD = 10
MIN_RATIO = 1.5
MIN_Z = 3.0

# Types where even modest counts matter (life-safety / habitability)
HAZARD_TYPES = {
    "HEAT/HOT WATER", "HEATING", "ELEVATOR", "STRUCTURAL", "GAS", "ELECTRIC", "WATER LEAK",
    "LEAD", "ASBESTOS", "MOLD", "UNSANITARY CONDITION", "SEWER", "WATER SYSTEM",
    "Building/Use", "Emergency Response Team (ERT)", "Scaffold Safety", "Boilers",
    "Plumbing", "Non-Emergency Police Matter", "Drug Activity", "Homeless Person Assistance",
    "Encampment", "Rodent", "Food Poisoning", "Lead", "Asbestos", "Mold", "Sewer",
    "Water Quality", "Indoor Air Quality", "Hazardous Materials", "Radioactive Material",
    "Unsanitary Animal Pvt Property", "Illegal Fireworks", "Fire Safety Director - F58",
}

# Complaint types that are agency-internal or too noisy to be useful leads
IGNORE_TYPES = {"Request Large Bulky Item Collection", "Special Projects Inspection Team (SPIT)",
                "DOF Literature Request", "Ferry Complaint", "Vaccine Mandate Non-Compliance",
                "Benefit Card Replacement", "SNW", "DPR Internal", "DEP Street Condition",
                "DHS Advantage - Third Party", "Housing - Low Income Senior"}


def _grouped(start, end_excl):
    rows = soql_all(DS, select="community_board, complaint_type, count(*) as n",
                    where=where_between("created_date", start, end_excl),
                    group="community_board, complaint_type", page=50000, max_rows=100000)
    out = defaultdict(int)
    for r in rows:
        cd = cd_from_311(r.get("community_board"))
        t = r.get("complaint_type")
        if not cd or not t or t in IGNORE_TYPES:
            continue
        out[(cd, t)] += int(r["n"])
    return out


WEEKS = 12


def detect_seasonal(end=None):
    """Returns anomalies plus per-district 311 tables (top types by volume with
    seasonal ratio, weekly series for the last 12 weeks, rising types)."""
    end = end or data_end()
    cur_s, cur_e = window(end, CUR_DAYS)
    rec_s = cur_s - timedelta(days=RECENT_DAYS)
    print(f"[seasonal] current window {iso(cur_s)}..{iso(end)}; recent {iso(rec_s)}..{iso(cur_s - timedelta(days=1))}")

    # 12 weekly buckets, newest first: week 0 = last 7 days
    weekly = []
    for w in range(WEEKS):
        we = cur_e - timedelta(days=7 * w)
        ws = we - timedelta(days=7)
        weekly.append(_grouped(ws, we))
    cur = defaultdict(int)
    for g in weekly[:4]:
        for k, v in g.items():
            cur[k] += v
    recent = defaultdict(int)
    for g in weekly[4:12]:
        for k, v in g.items():
            recent[k] += v
    last7 = weekly[0]
    prior3 = defaultdict(int)
    for g in weekly[1:4]:
        for k, v in g.items():
            prior3[k] += v

    seasonal = []
    for y in SEASONAL_YEARS:
        s = cur_s - timedelta(days=364 * y)
        e = cur_e - timedelta(days=364 * y)
        seasonal.append((y, _grouped(s, e), (iso(s), iso(e - timedelta(days=1)))))

    tot_cur = sum(cur.values())
    scales = {}
    for y, g, _ in seasonal:
        tot = sum(g.values())
        scales[y] = (tot_cur / tot) if tot else None
    print(f"[seasonal] citywide 28d total {tot_cur:,}; drift scales {scales}")

    city_hist = defaultdict(int)
    for _, g, _ in seasonal:
        for (cd, t), v in g.items():
            city_hist[t] += v
    taxonomy_new = {t for t in {k[1] for k in cur} if city_hist[t] < 30}
    if taxonomy_new:
        print(f"[seasonal] skipping types with no citywide history (renames/new): {sorted(taxonomy_new)[:12]}")

    def expectations(cd, t):
        seas_vals = []
        for y, g, _ in seasonal:
            if scales[y] is None:
                continue
            v = g.get((cd, t))
            if v is not None:
                seas_vals.append(v * scales[y])
        exp_seasonal = (sum(seas_vals) / len(seas_vals)) if seas_vals else None
        exp_recent = recent.get((cd, t), 0) / (RECENT_DAYS / CUR_DAYS)
        candidates = [v for v in (exp_seasonal, exp_recent) if v is not None]
        expected = max(max(candidates) if candidates else 0.0, 1.0)
        return exp_seasonal, len(seas_vals), exp_recent, expected

    anomalies = []
    per_cd = defaultdict(list)          # cd -> rows for every (cd, type) with cur28 >= 5
    for (cd, t), obs in cur.items():
        exp_seasonal, ny, exp_recent, expected = expectations(cd, t)
        ratio = obs / expected
        z = (obs - expected) / math.sqrt(expected + 1)
        l7 = last7.get((cd, t), 0)
        p3 = prior3.get((cd, t), 0) / 3.0
        row = {
            "cd": cd, "district": CD_NAMES[cd], "complaint_type": t,
            "cur28": obs, "expected": round(expected, 1),
            "exp_seasonal": round(exp_seasonal, 1) if exp_seasonal is not None else None,
            "seasonal_years": ny, "exp_recent": round(exp_recent, 1),
            "ratio": round(ratio, 2),
            "vs_seasonal": round(obs / exp_seasonal, 2) if exp_seasonal else None,
            "vs_recent": round(obs / exp_recent, 2) if exp_recent else None,
            "z": round(z, 1), "last7": l7, "prior3wk_avg": round(p3, 1),
            "accelerating": bool(l7 >= max(3, 1.3 * p3)),
            "hazard": t in HAZARD_TYPES, "taxonomy_new": t in taxonomy_new,
            "weeks": [weekly[w].get((cd, t), 0) for w in range(WEEKS)][::-1],   # oldest -> newest
        }
        if obs >= 5:
            per_cd[cd].append(row)
        min_obs = MIN_OBS_HAZARD if t in HAZARD_TYPES else MIN_OBS
        if obs < min_obs or t in taxonomy_new or ratio < MIN_RATIO or z < MIN_Z:
            continue
        anomalies.append(row)
    anomalies.sort(key=lambda a: (-a["z"] * (1.5 if a["accelerating"] else 1.0)))
    print(f"[seasonal] {len(anomalies)} district/type anomalies flagged")

    # district totals (all types) vs seasonal + recent
    cd_tot = defaultdict(int)
    for (cd, t), v in cur.items():
        cd_tot[cd] += v
    cd_seas = defaultdict(list)
    for y, g, _ in seasonal:
        if scales[y] is None:
            continue
        agg = defaultdict(int)
        for (cd, t), v in g.items():
            agg[cd] += v
        for cd, v in agg.items():
            cd_seas[cd].append(v * scales[y])
    cd_rec = defaultdict(int)
    for (cd, t), v in recent.items():
        cd_rec[cd] += v
    cd_weeks = defaultdict(lambda: [0] * WEEKS)
    for w, g in enumerate(weekly):
        for (cd, t), v in g.items():
            cd_weeks[cd][WEEKS - 1 - w] += v
    district_311 = {}
    for cd in CD_NAMES:
        rows = per_cd.get(cd, [])
        seas = cd_seas.get(cd, [])
        district_311[cd] = {
            "cur28": cd_tot.get(cd, 0),
            "exp_seasonal": round(sum(seas) / len(seas), 1) if seas else None,
            "exp_recent": round(cd_rec.get(cd, 0) / (RECENT_DAYS / CUR_DAYS), 1),
            "weeks": cd_weeks[cd],
            "top_by_volume": sorted(rows, key=lambda r: -r["cur28"])[:15],
            "rising": sorted([r for r in rows if r["last7"] >= 5 and r["prior3wk_avg"] > 0 and r["last7"] >= 1.5 * r["prior3wk_avg"]],
                             key=lambda r: -(r["last7"] - r["prior3wk_avg"]))[:10],
        }

    return {
        "as_of": iso(end),
        "window": {"start": iso(cur_s), "end": iso(end), "days": CUR_DAYS},
        "week_labels": [iso(cur_e - timedelta(days=7 * w + 7)) for w in range(WEEKS)][::-1],
        "seasonal_windows": [w for _, _, w in seasonal],
        "drift_scales": {str(k): (round(v, 3) if v else None) for k, v in scales.items()},
        "anomalies": anomalies,
        "district_311": district_311,
    }


# --- novelty ---------------------------------------------------------------

NOV_CUR_DAYS = 56
NOV_MIN = 25
NOV_RATIO = 4.0
NOV_YEARS = (1, 2)


def _sq(s):
    return "'" + s.replace("'", "''") + "'"


def detect_novelty(end=None):
    """Descriptors arriving in volume now that were absent from the SAME 56-day
    window in the prior two years. Comparing like-with-like keeps summer hydrants
    and July fireworks out; a rename filter keeps 311's taxonomy churn out."""
    end = end or data_end()
    cur_s, cur_e = window(end, NOV_CUR_DAYS)
    print(f"[novelty] current {iso(cur_s)}..{iso(end)} vs same window {NOV_YEARS} years earlier")

    def grouped(s, e):
        rows = soql_all(DS, select="complaint_type, descriptor, count(*) as n",
                        where=where_between("created_date", s, e),
                        group="complaint_type, descriptor", page=50000, max_rows=100000)
        return {(r.get("complaint_type") or "", r.get("descriptor") or ""): int(r["n"]) for r in rows}

    cur = grouped(cur_s, cur_e)
    priors = []
    for y in NOV_YEARS:
        priors.append(grouped(cur_s - timedelta(days=364 * y), cur_e - timedelta(days=364 * y)))
    tot_cur = sum(cur.values())
    scales = [(tot_cur / sum(p.values())) if p else 1.0 for p in priors]

    def prior_mean(k):
        vals = [p.get(k, 0) * sc for p, sc in zip(priors, scales)]
        return sum(vals) / len(vals)

    # type-level totals to detect renames
    type_cur = defaultdict(int)
    for (t, d), n in cur.items():
        type_cur[t] += n
    type_prior = defaultdict(float)
    for p, sc in zip(priors, scales):
        for (t, d), n in p.items():
            type_prior[t] += n * sc / len(priors)

    # First pass: which (type, descriptor) pairs are new or 4x rarer before?
    fresh = []
    for (t, d), n in cur.items():
        if n < NOV_MIN or t in IGNORE_TYPES or d.strip().upper() in ("", "N/A", "NA", "OTHER", "OTHER (COMPLAINT DETAILS)"):
            continue
        base = prior_mean((t, d))
        if base > 0 and n / base < NOV_RATIO:
            continue
        fresh.append((t, d, n, base))
    fresh_per_type = defaultdict(int)
    for t, d, n, base in fresh:
        fresh_per_type[t] += 1
    # Volume that disappeared: descriptors present in the prior windows and gone
    # now. A new descriptor whose volume is matched by a vanished sibling is a
    # rename, whatever the type total does.
    vanished = defaultdict(float)
    for (t, d) in {k for p in priors for k in p}:
        if cur.get((t, d), 0) == 0:
            vanished[t] += prior_mean((t, d))

    # Second pass: rename filters. 311 periodically re-labels the descriptors
    # under a type (Noise, Air Quality, Water System...). The tell is a type
    # whose total volume is flat while several "new" descriptors appear at once,
    # or a brand-new type carrying volume that used to be filed elsewhere.
    novel, taxonomy = [], []
    for t, d, n, base in fresh:
        type_new = type_prior[t] < 30
        share = n / max(type_cur[t], 1)
        type_ratio = type_cur[t] / max(type_prior[t], 1.0)
        note = None
        if type_new and type_cur[t] >= 100:
            note = "new complaint type carrying volume that used to be filed elsewhere"
        elif not type_new and type_ratio < 1.5 and (share >= 0.4 or fresh_per_type[t] >= 2):
            note = "descriptor relabelled within a type whose total is flat"
        elif not type_new and vanished[t] >= 0.5 * n:
            note = f"descriptor replaced one that vanished (about {int(vanished[t])} reports/window moved)"
        if note:
            taxonomy.append({"complaint_type": t, "descriptor": d, "cur56": n, "note": note})
            continue
        novel.append({"complaint_type": t, "descriptor": d, "cur56": n, "base_same_window": round(base, 1),
                      "rate_ratio": round(n / base, 1) if base else None,
                      "type_ratio": round(type_ratio, 2)})
    novel.sort(key=lambda r: -r["cur56"])
    novel = novel[:20]
    print(f"[novelty] {len(novel)} novel descriptors; {len(taxonomy)} taxonomy changes set aside")

    if novel:
        conds = " OR ".join(
            f"(complaint_type = {_sq(r['complaint_type'])} AND descriptor = {_sq(r['descriptor'])})" for r in novel)
        rows = soql_all(DS, select="complaint_type, descriptor, community_board, count(*) as n",
                        where=f"{where_between('created_date', cur_s, cur_e)} AND ({conds})",
                        group="complaint_type, descriptor, community_board", page=50000)
        by = defaultdict(list)
        for r in rows:
            cd = cd_from_311(r.get("community_board"))
            if cd:
                by[(r["complaint_type"], r.get("descriptor") or "")].append({"cd": cd, "district": CD_NAMES[cd], "n": int(r["n"])})
        for r in novel:
            lst = sorted(by.get((r["complaint_type"], r["descriptor"]), []), key=lambda x: -x["n"])
            r["by_cd"] = lst[:8]
            tot = sum(x["n"] for x in lst) or 1
            r["top_cd_share"] = round(lst[0]["n"] / tot, 2) if lst else None
    return {"as_of": iso(end), "window": {"start": iso(cur_s), "end": iso(end), "days": NOV_CUR_DAYS},
            "prior_years": list(NOV_YEARS), "novel": novel, "taxonomy_changes": sorted(taxonomy, key=lambda r: -r["cur56"])[:15]}


if __name__ == "__main__":
    import json
    s = detect_seasonal()
    print(json.dumps(s["anomalies"][:15], indent=1))
    n = detect_novelty()
    print(json.dumps(n["novel"][:10], indent=1))
