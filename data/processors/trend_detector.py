"""
Trend detector for 311 complaint data.
Identifies spikes, sustained trends, and anomalies per community district.
Adapted from crime-story-finder's statistical approach.
"""

import math
from collections import defaultdict


def _z_score(value, mean, std):
    """Calculate z-score. Returns 0 if std is 0."""
    if std == 0:
        return 0
    return (value - mean) / std


def _severity(z):
    """Map z-score to severity level."""
    az = abs(z)
    if az >= 2.5:
        return "high"
    if az >= 1.5:
        return "medium"
    return "low"


def _pct_change(current, baseline):
    """Percentage change, returns None if baseline is 0."""
    if baseline == 0:
        return None
    return round((current - baseline) / baseline * 100, 1)


def detect_spikes(district_data):
    """
    For each (district, complaint_type) pair, detect spikes in recent weeks.
    Uses z-score analysis on 12-week rolling window.

    Returns dict of cd → list of spike objects.
    """
    all_spikes = {}

    for cd, data in district_data.items():
        spikes = []
        weekly = data.get("weekly", {})

        # Get unique complaint types across all weeks
        complaint_types = set()
        for week_data in weekly.values():
            complaint_types.update(week_data.keys())

        for complaint_type in complaint_types:
            # Build 12-week time series (oldest to newest)
            series = []
            for w in range(11, -1, -1):
                week_key = f"w{w}"
                count = weekly.get(week_key, {}).get(complaint_type, 0)
                series.append(count)

            if len(series) < 12:
                continue

            # Baseline: weeks 0-7 (older period)
            baseline = series[:8]
            recent = series[8:]  # last 4 weeks

            mean = sum(baseline) / len(baseline) if baseline else 0
            std = math.sqrt(sum((x - mean) ** 2 for x in baseline) / len(baseline)) if baseline else 0

            # Check most recent week for spike
            current_week = series[-1]
            z = _z_score(current_week, mean, std)
            pct = _pct_change(current_week, mean)

            if abs(z) >= 1.8 and current_week >= 3:  # Meaningful spike threshold
                spikes.append({
                    "type": complaint_type,
                    "z_score": round(z, 2),
                    "current_week": current_week,
                    "baseline_avg": round(mean, 1),
                    "pct_change": pct,
                    "severity": _severity(z),
                    "direction": "up" if z > 0 else "down",
                })

            # Check for sustained trend (last 4 weeks all above/below mean)
            if mean > 0 and all(w > mean * 1.2 for w in recent) and sum(recent) >= 8:
                avg_recent = sum(recent) / len(recent)
                sustained_pct = _pct_change(avg_recent, mean)
                if sustained_pct and abs(sustained_pct) >= 20:
                    spikes.append({
                        "type": complaint_type,
                        "z_score": round(_z_score(avg_recent, mean, std), 2),
                        "current_week": current_week,
                        "baseline_avg": round(mean, 1),
                        "pct_change": sustained_pct,
                        "severity": "medium" if abs(sustained_pct) >= 40 else "low",
                        "direction": "up" if sustained_pct > 0 else "down",
                        "sustained_weeks": 4,
                    })

        # Sort by severity then z-score
        severity_order = {"high": 0, "medium": 1, "low": 2}
        spikes.sort(key=lambda s: (severity_order.get(s["severity"], 2), -abs(s["z_score"])))
        all_spikes[cd] = spikes[:10]  # Cap at 10 per district

    return all_spikes


def compute_activity_scores(district_data, spikes):
    """
    Compute an activity score (0-100) for each district based on:
    - Total complaint volume (relative to district average)
    - Number and severity of spikes
    - Variety of complaint types with activity
    """
    scores = {}

    # Get citywide averages
    all_totals = [d["total"] for d in district_data.values()]
    if not all_totals:
        return scores

    city_avg = sum(all_totals) / len(all_totals)
    city_max = max(all_totals) if all_totals else 1

    for cd, data in district_data.items():
        score = 0

        # Volume component (0-40): how does this district compare to average?
        volume_ratio = data["total"] / city_avg if city_avg > 0 else 0
        score += min(40, int(volume_ratio * 20))

        # Spike component (0-40): how many and how severe?
        cd_spikes = spikes.get(cd, [])
        high_spikes = sum(1 for s in cd_spikes if s["severity"] == "high")
        med_spikes = sum(1 for s in cd_spikes if s["severity"] == "medium")
        score += min(40, high_spikes * 15 + med_spikes * 8 + len(cd_spikes) * 2)

        # Diversity component (0-20): how many categories have activity?
        active_categories = len(data.get("by_category", {}))
        score += min(20, active_categories * 3)

        scores[cd] = min(100, max(0, score))

    return scores


def detect_all(district_data):
    """
    Main entry point.
    Returns (spikes_by_district, activity_scores).
    """
    print("[Trends] Detecting 311 spikes and trends...")
    spikes = detect_spikes(district_data)
    total_spikes = sum(len(s) for s in spikes.values())
    high_spikes = sum(1 for s_list in spikes.values() for s in s_list if s["severity"] == "high")
    print(f"[Trends] Found {total_spikes} spikes ({high_spikes} high severity)")

    print("[Trends] Computing activity scores...")
    activity_scores = compute_activity_scores(district_data, spikes)

    return spikes, activity_scores
