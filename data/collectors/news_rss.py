"""
Local news RSS collector.
Fetches headlines from NYC-focused outlets, geo-maps to community districts.
Adapted from nyc-news-engine patterns.
"""

import re
import hashlib
import feedparser
from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NEWS_FEEDS, NEIGHBORHOOD_TO_CD, TOPIC_RULES


def fetch_feed(feed_config):
    """Fetch and parse a single RSS feed."""
    try:
        parsed = feedparser.parse(feed_config["url"])
        items = []

        for entry in (parsed.entries or [])[:20]:
            title = entry.get("title", "Untitled")
            link = entry.get("link", "")
            snippet = entry.get("summary", "")
            # Strip HTML tags
            snippet = re.sub(r"<[^>]*>", "", snippet).strip()[:350]

            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    pass

            items.append({
                "id": hashlib.md5(link.encode()).hexdigest()[:12],
                "title": title,
                "link": link,
                "snippet": snippet,
                "pub_date": pub_date,
                "outlet": feed_config["name"],
                "outlet_slug": feed_config["slug"],
                "tier": feed_config["tier"],
            })

        return items
    except Exception as e:
        print(f"  Warning: Could not fetch {feed_config['name']}: {e}")
        return []


def geo_map_article(article):
    """Extract neighborhood mentions from article title and snippet."""
    text = f"{article['title']} {article['snippet']}".lower()
    districts = set()
    neighborhoods = set()

    for neighborhood, cds in NEIGHBORHOOD_TO_CD.items():
        pattern = r'\b' + re.escape(neighborhood) + r'\b'
        if re.search(pattern, text):
            for cd in cds:
                districts.add(cd)
            neighborhoods.add(neighborhood)

    article["districts"] = list(districts)
    article["matched_neighborhoods"] = list(neighborhoods)
    article["geo_confidence"] = "high" if districts else "none"
    return article


def classify_article(article):
    """Classify article into topic categories."""
    text = f"{article['title']} {article['snippet']}".lower()
    topics = []

    for topic, keywords in TOPIC_RULES.items():
        for kw in keywords:
            if kw in text:
                topics.append(topic)
                break

    article["topics"] = topics[:3] if topics else []
    return article


def collect():
    """Main entry point. Returns list of geo-mapped, classified articles."""
    print("[News] Fetching local news RSS feeds...")
    all_articles = []

    for feed in NEWS_FEEDS:
        print(f"  {feed['name']}...")
        articles = fetch_feed(feed)
        all_articles.extend(articles)

    print(f"[News] Got {len(all_articles)} articles total")

    # Geo-map and classify
    for article in all_articles:
        geo_map_article(article)
        classify_article(article)

    # Filter to last 14 days
    cutoff = (datetime.now() - timedelta(days=14)).isoformat()
    filtered = [
        a for a in all_articles
        if a.get("pub_date") and a["pub_date"] >= cutoff
    ]

    print(f"[News] {len(filtered)} articles after filtering (14 days)")
    return filtered


if __name__ == "__main__":
    articles = collect()
    for a in articles[:15]:
        districts = a.get("districts", [])
        print(f"  [{','.join(districts) or 'no-geo'}] {a['outlet']}: {a['title'][:60]}")
