"""
News attention by district: how many Google News headlines named one of the
district's neighborhoods in the last 7 days, and the top few. The inverse of
the coverage gap — which districts are being written about right now.

One Google News RSS query per district (59). If Google throttles, districts
after the breaker trips are marked null, never zero.
"""

import sys
import time

from common import CD_NAMES, cd_search_names
from coverage import _gnews


def collect_attention(days=7):
    out = {}
    fails = 0
    for cd in CD_NAMES:
        names = cd_search_names(cd)[:3]
        q = "(" + " OR ".join(f'"{n}"' for n in names) + ") (NYC OR \"New York\")"
        try:
            arts = _gnews(q.replace("when:42d", ""))  # _gnews appends its own lookback; override below
        except Exception as e:
            fails += 1
            print(f"  [attention] {cd}: {e}", file=sys.stderr)
            out[cd] = None
            if fails >= 4:
                print("  [attention] Google News unavailable; remaining districts marked null", file=sys.stderr)
                for rest in CD_NAMES:
                    out.setdefault(rest, None)
                break
            continue
        fails = 0
        # keep only headlines that actually contain a neighborhood name, last `days` days
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        keep = [a for a in arts if (a.get("date") or "9999") >= cutoff and any(n.lower() in (a.get("title") or "").lower() for n in names)]
        out[cd] = {"n7": len(keep), "top": [{"title": a["title"], "url": a["url"], "outlet": a["outlet"], "date": a["date"]} for a in keep[:4]],
                   "query": q}
        time.sleep(2.0)
    done = sum(1 for v in out.values() if v)
    print(f"[attention] {done}/{len(CD_NAMES)} districts searched")
    return out


if __name__ == "__main__":
    import json
    r = collect_attention()
    top = sorted([(cd, v["n7"]) for cd, v in r.items() if v], key=lambda x: -x[1])[:8]
    print(top)
