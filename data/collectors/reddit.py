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


# Filter out personal/lifestyle posts that aren't neighborhood news
SKIP_PATTERNS = re.compile(
    r'\b(moving to|should i move|best (bar|restaurant|coffee|brunch|pizza|bagel|gym|salon|haircut|dentist|doctor)s?'
    r'|recommend(ation)?s? for|where (can i|to|should)|looking for a? ?(roommate|apartment|sublet)'
    r'|is this (a )?(good|safe) (area|neighborhood)|how (safe )?is|what\'?s? it like (living|to live)'
    r'|date (night|idea)|things to do|hidden gem|first time visit'
    r'|selling|for sale|free stuff|giving away)\b',
    re.IGNORECASE
)

# Boost posts that look like actual news/community issues
NEWS_PATTERNS = re.compile(
    r'\b(closed|closing|shut down|demolished|fire|shooting|stabbing|crash|accident'
    r'|protest|rally|march|arrested|investigation|indicted|lawsuit|sued'
    r'|rezoning|development|construction|new building|demolition|evict'
    r'|flooding|power outage|blackout|water main|gas leak|collapse'
    r'|school|hospital|clinic|shelter|library|park|playground'
    r'|MTA|subway|bus|train|ferry|bike lane|congestion'
    r'|DOB|DOT|DEP|NYPD|FDNY|SLA|liquor license|community board'
    r'|budget|funding|cut|layoff|mayor|council|governor'
    r'|rat|rodent|sanitation|garbage|trash|illegal dumping'
    r'|crime|robbery|theft|assault|gun|weapon)\b',
    re.IGNORECASE
)


def newsworthiness_score(post):
    """Score a post for newsworthiness. Higher = more newsworthy."""
    text = f"{post['title']} {post['selftext']}"
    score = 0

    # Engagement is the base signal
    score += min(post["score"], 500)  # cap so a viral meme doesn't dominate
    score += post["num_comments"] * 3  # comments indicate discussion, weight higher

    # Boost news-like content
    news_matches = len(NEWS_PATTERNS.findall(text))
    score += news_matches * 20

    # Boost posts with topic classifications (means they match our editorial categories)
    if post.get("topics") and post["topics"] != ["quality-of-life"]:
        score += 30

    # Boost geo-specific posts (we can map them to a district)
    if post.get("geo_confidence") == "high":
        score += 25

    # Penalize lifestyle/recommendation posts
    if SKIP_PATTERNS.search(text):
        score -= 100

    # Penalize image-only posts with no text (usually memes/photos)
    if not post["selftext"] and post.get("score", 0) > 50:
        score -= 30

    # Boost link posts to news sites
    url = post.get("url", "")
    if any(d in url for d in ["gothamist", "thecity", "nypost", "nydailynews",
                               "nytimes", "ny1", "amny", "bklyner", "qns.com",
                               "bronxtimes", "silive", "patch.com", "cityandstate"]):
        score += 50

    return score


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
        if p["created_utc"] > cutoff and (p["score"] >= 10 or p["num_comments"] >= 5)
    ]

    # Score for newsworthiness and sort
    for post in filtered:
        post["news_score"] = newsworthiness_score(post)

    # Drop clearly non-newsy posts
    filtered = [p for p in filtered if p["news_score"] > 0]

    filtered.sort(key=lambda p: p["news_score"], reverse=True)

    print(f"[Reddit] {len(filtered)} posts after filtering (14 days, newsworthiness)")
    return filtered


if __name__ == "__main__":
    posts = collect()
    for p in posts[:20]:
        districts = p.get("districts", [])
        conf = p.get("geo_confidence", "none")
        print(f"  [{conf}] {','.join(districts) or '???'} — r/{p['subreddit']}: {p['title'][:60]}")
