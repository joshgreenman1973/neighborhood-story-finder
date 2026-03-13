"""
Reddit collector.
Fetches recent posts from NYC-related subreddits via the public JSON API.
"""

import re
import time
import requests
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SUBREDDITS, NEIGHBORHOOD_TO_CD


HEADERS = {
    "User-Agent": "NYC-Neighborhood-Story-Finder/1.0 (educational research tool)",
}


def fetch_subreddit(subreddit, limit=100):
    """Fetch posts from a subreddit using both /hot and /top (week) for coverage."""
    all_posts = {}

    for sort in ["hot", "top"]:
        params = f"limit={limit}"
        if sort == "top":
            params += "&t=week"
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?{params}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  Warning: Could not fetch r/{subreddit}/{sort}: {e}")
            continue

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied"):
                continue

            post_id = post.get("id", "")
            if post_id in all_posts:
                continue

            all_posts[post_id] = {
                "subreddit": subreddit,
                "title": post.get("title", ""),
                "selftext": (post.get("selftext") or "")[:500],
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "created_utc": post.get("created_utc", 0),
                "created_date": datetime.fromtimestamp(
                    post.get("created_utc", 0)
                ).strftime("%Y-%m-%d"),
                "flair": post.get("link_flair_text") or "",
            }

        time.sleep(1)  # Rate limit between sort types

    return list(all_posts.values())


def extract_neighborhoods(text):
    """
    Scan text for neighborhood name mentions.
    Returns list of (cd_code, neighborhood_name, confidence) tuples.
    """
    matches = []
    text_lower = text.lower()

    for neighborhood, cds in NEIGHBORHOOD_TO_CD.items():
        # Word boundary check to avoid partial matches
        pattern = r'\b' + re.escape(neighborhood) + r'\b'
        if re.search(pattern, text_lower):
            for cd in cds:
                matches.append((cd, neighborhood, 0.8))

    return matches


def geo_map_posts(posts):
    """
    Assign community districts to Reddit posts.
    Uses text matching first, then subreddit-level fallback.
    """
    for post in posts:
        combined_text = f"{post['title']} {post['selftext']} {post['flair']}"
        matches = extract_neighborhoods(combined_text)

        if matches:
            # Use text-matched districts
            post["districts"] = list(set(m[0] for m in matches))
            post["matched_neighborhoods"] = list(set(m[1] for m in matches))
            post["geo_confidence"] = "high"
        else:
            # Fall back to subreddit-level mapping
            sub_info = SUBREDDITS.get(post["subreddit"], {})
            if sub_info.get("cds"):
                post["districts"] = sub_info["cds"]
                post["geo_confidence"] = "medium"
            elif sub_info.get("borough"):
                post["districts"] = []  # borough-wide, no specific CD
                post["borough"] = sub_info["borough"]
                post["geo_confidence"] = "low"
            else:
                post["districts"] = []
                post["geo_confidence"] = "none"

    return posts


def classify_topic(post):
    """Classify a Reddit post into topic categories."""
    from config import TOPIC_RULES
    text = f"{post['title']} {post['selftext']}".lower()
    topics = []

    for topic, keywords in TOPIC_RULES.items():
        for kw in keywords:
            if kw in text:
                topics.append(topic)
                break

    return topics[:3] if topics else ["quality-of-life"]


def collect():
    """Main entry point. Returns list of geo-mapped, classified posts."""
    print("[Reddit] Fetching posts from NYC subreddits...")
    all_posts = []

    for subreddit in SUBREDDITS:
        print(f"  r/{subreddit}...")
        posts = fetch_subreddit(subreddit)
        all_posts.extend(posts)
        time.sleep(1)  # Rate limit between subreddits

    print(f"[Reddit] Got {len(all_posts)} posts total")

    print("[Reddit] Geo-mapping posts...")
    all_posts = geo_map_posts(all_posts)

    # Classify topics
    for post in all_posts:
        post["topics"] = classify_topic(post)

    # Filter: only keep posts less than 14 days old with meaningful engagement
    cutoff = time.time() - (14 * 86400)
    filtered = [
        p for p in all_posts
        if p["created_utc"] > cutoff and (p["score"] >= 5 or p["num_comments"] >= 3)
    ]

    # Sort by engagement (score + comments) so the most-discussed posts surface first
    filtered.sort(key=lambda p: p["score"] + p["num_comments"], reverse=True)

    print(f"[Reddit] {len(filtered)} posts after filtering (14 days, min engagement)")
    return filtered


if __name__ == "__main__":
    posts = collect()
    for p in posts[:20]:
        districts = p.get("districts", [])
        conf = p.get("geo_confidence", "none")
        print(f"  [{conf}] {','.join(districts) or '???'} — r/{p['subreddit']}: {p['title'][:60]}")
