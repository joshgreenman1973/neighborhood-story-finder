"""
Data compressor.
Takes all collected/processed data and generates optimized static JSON files
for the frontend.
"""

import os
import json
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CD_NAMES, CATEGORIES


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")


def ensure_output_dirs():
    os.makedirs(os.path.join(OUTPUT_DIR, "districts"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "geo"), exist_ok=True)


def generate_districts_json(district_311, spikes, activity_scores, themes, sparklines):
    """
    Generate the master districts.json with summary data for all 59 CDs.
    This is loaded on page init (~200KB).
    """
    districts = {}

    for cd in sorted(CD_NAMES.keys()):
        d311 = district_311.get(cd, {})
        cd_themes = themes.get(cd, [])
        cd_sparklines = sparklines.get(cd, [])
        cd_spikes = spikes.get(cd, [])

        # Compute 2-week total (last 2 weeks = w0 + w1)
        total_2w = 0
        for week_key in ["w0", "w1"]:
            for count in d311.get("weekly", {}).get(week_key, {}).values():
                total_2w += count

        # Get prior 2-week total for comparison (w2 + w3)
        total_prior_2w = 0
        for week_key in ["w2", "w3"]:
            for count in d311.get("weekly", {}).get(week_key, {}).values():
                total_prior_2w += count

        pct_change = None
        if total_prior_2w > 0:
            pct_change = round((total_2w - total_prior_2w) / total_prior_2w * 100, 1)

        # Borough from CD code
        boro_map = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}
        borough = boro_map.get(cd[0], "Unknown")

        # Top 3 themes (summary only)
        summary_themes = []
        for t in cd_themes[:3]:
            summary_themes.append({
                "label": t.get("label", ""),
                "category": t.get("category", "quality-of-life"),
                "intensity": t.get("intensity", "low"),
            })

        # Spike count by severity
        spike_counts = {"high": 0, "medium": 0, "low": 0}
        for s in cd_spikes:
            sev = s.get("severity", "low")
            spike_counts[sev] = spike_counts.get(sev, 0) + 1

        # Story score (best score from themes)
        best_story_score = None
        for t in cd_themes:
            ss = t.get("story_score", {})
            if ss:
                if not best_story_score or _score_rank(ss) > _score_rank(best_story_score):
                    best_story_score = ss

        # All complaint types that appear in this district (for search)
        all_types = list(d311.get("by_type", {}).keys())

        districts[cd] = {
            "name": CD_NAMES.get(cd, f"District {cd}"),
            "borough": borough,
            "activity_score": activity_scores.get(cd, 0),
            "themes": summary_themes,
            "complaint_total": d311.get("total", 0),
            "complaint_total_2w": total_2w,
            "complaint_change_pct": pct_change,
            "top_complaints": [
                {"type": s["type"], "count": s["total"], "sparkline": s["counts"]}
                for s in cd_sparklines[:5]
            ],
            "all_complaint_types": all_types,
            "spike_counts": spike_counts,
            "best_story_score": best_story_score,
        }

    output = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "districts": districts,
    }

    path = os.path.join(OUTPUT_DIR, "districts.json")
    with open(path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_kb = os.path.getsize(path) / 1024
    print(f"  districts.json: {size_kb:.0f} KB")
    return output


def generate_district_detail(cd, district_311, spikes, themes, reddit_posts, news_articles, cb_data,
                             budget_reqs=None, land_use_projects=None, council_info=None, dob_info=None):
    """
    Generate per-district detail JSON (lazy-loaded on click).
    """
    cd_spikes = spikes.get(cd, [])
    cd_themes = themes.get(cd, [])
    cb_info_data = cb_data.get(cd, {})

    detail = {
        "cd_code": cd,
        "name": CD_NAMES.get(cd, f"District {cd}"),
        "themes_detail": cd_themes,
        "complaints": {
            "spikes": cd_spikes,
            "by_category": dict(district_311.get("by_category", {})) if district_311 else {},
            "total": district_311.get("total", 0) if district_311 else 0,
        },
        "reddit_posts": [
            {
                "title": p["title"][:100],
                "url": p["url"],
                "subreddit": p["subreddit"],
                "score": p["score"],
                "num_comments": p["num_comments"],
                "date": p["created_date"],
                "topics": p.get("topics", []),
            }
            for p in reddit_posts[:15]
        ],
        "news": [
            {
                "title": a["title"][:100],
                "outlet": a["outlet"],
                "link": a["link"],
                "date": (a.get("pub_date") or "")[:10],
                "topics": a.get("topics", []),
            }
            for a in news_articles[:10]
        ],
        "community_board": {
            "url": cb_info_data.get("url", ""),
            "events_url": cb_info_data.get("events_url", ""),
            "next_meeting": cb_info_data.get("next_meeting"),
            "topics": cb_info_data.get("topics", []),
            "committees_active": cb_info_data.get("committees_active", []),
            "meetings": [
                {
                    "title": m.get("title", "")[:100],
                    "committee": m.get("committee", "other"),
                    "date": m.get("date", ""),
                    "location": m.get("location", "")[:80],
                    "url": m.get("url", ""),
                    "description": m.get("description", "")[:150],
                    "days_away": m.get("days_away"),
                }
                for m in cb_info_data.get("meetings", [])[:10]
            ],
        },
        "budget_requests": [
            {
                "request": r.get("request", "")[:150],
                "priority": r.get("priority", ""),
                "agency": r.get("agency", ""),
                "category": r.get("category", ""),
                "response": r.get("response", "")[:150],
            }
            for r in (budget_reqs or [])[:15]
        ],
        "land_use": [
            {
                "name": p.get("name", "")[:100],
                "brief": p.get("brief", "")[:200],
                "type": p.get("type", ""),
                "status": p.get("status", ""),
                "milestone": p.get("milestone", ""),
                "milestone_date": p.get("milestone_date", ""),
                "applicant": p.get("applicant", "")[:80],
            }
            for p in (land_use_projects or [])[:10]
        ],
        "council_services": {
            "total": (council_info or {}).get("total", 0),
            "top_types": sorted(
                (council_info or {}).get("complaint_types", {}).items(),
                key=lambda x: -x[1]
            )[:8] if council_info else [],
            "recent": (council_info or {}).get("recent", [])[:5],
        },
        "dob_permits": {
            "total": (dob_info or {}).get("total", 0),
            "by_type": (dob_info or {}).get("by_type", {}),
            "notable": (dob_info or {}).get("notable", [])[:8],
        },
    }

    path = os.path.join(OUTPUT_DIR, "districts", f"{cd}.json")
    with open(path, "w") as f:
        json.dump(detail, f, separators=(",", ":"))


def generate_trends_json(spikes, activity_scores, themes):
    """
    Generate citywide trends.json with hot spots and trending topics.
    """
    # Hot spots: districts with highest activity scores and most high-severity spikes
    hot_spots = []
    for cd in sorted(CD_NAMES.keys()):
        cd_spikes = spikes.get(cd, [])
        high_count = sum(1 for s in cd_spikes if s["severity"] == "high")
        score = activity_scores.get(cd, 0)

        if score >= 40 or high_count >= 2:
            # Find best theme for this hot spot
            cd_themes = themes.get(cd, [])
            top_theme = cd_themes[0] if cd_themes else None

            hot_spots.append({
                "cd": cd,
                "name": CD_NAMES.get(cd, f"District {cd}"),
                "activity_score": score,
                "high_spikes": high_count,
                "top_theme": top_theme.get("label", "") if top_theme else "",
                "top_theme_category": top_theme.get("category", "") if top_theme else "",
                "story_score": top_theme.get("story_score") if top_theme else None,
            })

    hot_spots.sort(key=lambda h: (-h["high_spikes"], -h["activity_score"]))

    # Trending topics: aggregate across all districts
    topic_counts = {}
    for cd_themes in themes.values():
        for t in cd_themes:
            cat = t.get("category", "other")
            topic_counts[cat] = topic_counts.get(cat, 0) + 1

    # Top stories: the most interesting individual leads across all districts
    # Rank by recency first, then story quality score
    recency_rank = {"this week": 0, "last 2 weeks": 1, "last month": 2, "ongoing": 3}
    all_leads = []
    for cd, cd_themes in themes.items():
        for t in cd_themes:
            ss = t.get("story_score", {})
            recency = t.get("recency", "ongoing")
            quality = _score_rank(ss)
            all_leads.append({
                "cd": cd,
                "district_name": CD_NAMES.get(cd, f"District {cd}"),
                "label": t.get("label", ""),
                "summary": t.get("summary", ""),
                "category": t.get("category", ""),
                "intensity": t.get("intensity", ""),
                "recency": recency,
                "story_score": ss,
                "evidence": t.get("evidence", [])[:2],
                "_sort": (recency_rank.get(recency, 3), -quality),
            })

    all_leads.sort(key=lambda x: x["_sort"])
    top_stories = [{k: v for k, v in lead.items() if k != "_sort"} for lead in all_leads[:10]]

    output = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "hot_spots": hot_spots[:20],
        "top_stories": top_stories,
        "trending_topics": sorted(topic_counts.items(), key=lambda x: -x[1]),
    }

    path = os.path.join(OUTPUT_DIR, "trends.json")
    with open(path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    print(f"  trends.json: {os.path.getsize(path) / 1024:.0f} KB")


def _score_rank(story_score):
    """Numeric rank for comparing story scores."""
    rank_map = {"high": 3, "medium": 2, "low": 1, "feature": 3, "short": 2, "brief": 1}
    total = 0
    for k, v in story_score.items():
        total += rank_map.get(v, 0)
    return total


def generate_all(district_311, spikes, activity_scores, themes, sparklines,
                 reddit_posts, news_articles, cb_data,
                 budget_data=None, land_use_data=None, council_data=None, dob_data=None):
    """Main entry point. Generate all output files."""
    budget_data = budget_data or {}
    land_use_data = land_use_data or {}
    council_data = council_data or {}
    dob_data = dob_data or {}

    ensure_output_dirs()
    print("[Output] Generating static JSON files...")

    # Master districts.json
    generate_districts_json(district_311, spikes, activity_scores, themes, sparklines)

    # Per-district detail files
    reddit_by_cd = {}
    for post in reddit_posts:
        for cd in post.get("districts", []):
            reddit_by_cd.setdefault(cd, []).append(post)

    news_by_cd = {}
    for article in news_articles:
        for cd in article.get("districts", []):
            news_by_cd.setdefault(cd, []).append(article)

    for cd in sorted(CD_NAMES.keys()):
        generate_district_detail(
            cd,
            district_311.get(cd, {}),
            spikes,
            themes,
            reddit_by_cd.get(cd, []),
            news_by_cd.get(cd, []),
            cb_data,
            budget_reqs=budget_data.get(cd, []),
            land_use_projects=land_use_data.get(cd, []),
            council_info=council_data.get(cd),
            dob_info=dob_data.get(cd),
        )

    print(f"  Generated {len(CD_NAMES)} district detail files")

    # Citywide trends
    generate_trends_json(spikes, activity_scores, themes)

    # Meta file
    meta = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "data_sources": {
            "311_records": sum(d.get("total", 0) for d in district_311.values()),
            "reddit_posts": len(reddit_posts),
            "news_articles": len(news_articles),
            "community_boards": len(cb_data),
            "budget_requests": sum(len(v) for v in budget_data.values()),
            "land_use_projects": sum(len(v) for v in land_use_data.values()),
            "council_services": sum(v.get("total", 0) for v in council_data.values()),
            "dob_permits": sum(v.get("total", 0) for v in dob_data.values()),
        },
        "districts_count": len(CD_NAMES),
    }
    with open(os.path.join(OUTPUT_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print("[Output] Done!")
