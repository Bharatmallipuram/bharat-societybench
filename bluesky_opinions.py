"""
Usage:
    pip install requests
    set BSKY_HANDLE=yourname.bsky.social          (Windows)  /  export ... (Mac/Linux)
    set BSKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx     (create at Bluesky > Settings > App Passwords)
    python bluesky_opinions.py
Output: bluesky_opinions.csv with columns:
    type,id,parent_id,platform,create_time,title,content,liked_count,
    comment_count,share_count,user_name,ip_location,source_keyword,url
"""
import csv
import os
import time
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests

# ---- Credentials ------------------------------------------------------------
# HANDLE = os.environ.get("BSKY_HANDLE", "")
HANDLE = "kobe08-24.bsky.social"
# APP_PASSWORD = os.environ.get("BSKY_APP_PASSWORD", "")
APP_PASSWORD = "**********"


# ---- What to collect --------------------------------------------------------
TOPICS = [
    "NEET_Paper_Leak",
]
LANGUAGE = "en"               # set to None for all languages
SORT = "top"                  # "top" or "latest"
POSTS_PER_TOPIC = 100         # max posts kept per topic
FETCH_REPLIES = True          # also collect replies for each post
MIN_REPLIES_TO_FETCH = 1      # only open threads with at least this many replies
REPLIES_PER_POST = 100        # max replies kept per post
SINCE = None                  # e.g. "2026-09-01T00:00:00Z" or None
OUTPUT_FILE = "bluesky_opinions_NEET_Paper_Leak.csv"
# -----------------------------------------------------------------------------

BASE = "https://bsky.social/xrpc"
COLUMNS = [
    "type", "id", "parent_id", "platform", "create_time", "title", "content",
    "liked_count", "comment_count", "share_count", "user_name", "ip_location",
    "source_keyword", "url",
]

session = requests.Session()
seen_ids = set()


def clean(text):
    return (text or "").replace("\r", " ").replace("\n", " ").strip()


def login():
    r = session.post(f"{BASE}/com.atproto.server.createSession",
                     json={"identifier": HANDLE, "password": APP_PASSWORD}, timeout=30)
    r.raise_for_status()
    session.headers["Authorization"] = f"Bearer {r.json()['accessJwt']}"


def get(endpoint, params):
    """GET with simple retry on rate limits / temporary errors."""
    for attempt in range(5):
        r = session.get(f"{BASE}/{endpoint}", params=params, timeout=30)
        if r.status_code in (429, 502, 503):
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Bluesky request kept failing: {endpoint}")


def post_url(post):
    return f"https://bsky.app/profile/{post['author']['handle']}/post/{post['uri'].split('/')[-1]}"


def to_row(post, row_type, keyword, parent_id=""):
    rec = post.get("record", {})
    created = rec.get("createdAt", post.get("indexedAt", ""))
    return {
        "type": row_type,
        "id": post["uri"].split("/")[-1],
        "parent_id": parent_id,
        "platform": "bluesky",
        "create_time": created,
        "title": "",
        "content": clean(rec.get("text", "")),
        "liked_count": post.get("likeCount", 0),
        "comment_count": post.get("replyCount", 0),
        "share_count": post.get("repostCount", 0) + post.get("quoteCount", 0),
        "user_name": post["author"]["handle"],
        "ip_location": "",  # Bluesky does not provide location
        "source_keyword": keyword,
        "url": post_url(post),
    }


def walk_replies(node, keyword, parent_rkey, out, limit):
    """Recursively collect replies from a getPostThread tree."""
    for child in node.get("replies", []):
        if len(out) >= limit:
            return
        post = child.get("post")
        if not post:  # blocked / not-found placeholder
            continue
        rkey = post["uri"].split("/")[-1]
        if rkey in seen_ids:
            continue
        seen_ids.add(rkey)
        out.append(to_row(post, "comment", keyword, parent_rkey))
        walk_replies(child, keyword, rkey, out, limit)


def collect_replies(post, keyword):
    data = get("app.bsky.feed.getPostThread", {"uri": post["uri"], "depth": 6, "parentHeight": 0})
    out = []
    walk_replies(data["thread"], keyword, post["uri"].split("/")[-1], out, REPLIES_PER_POST)
    return out


def search_topic(topic):
    rows, posts, cursor = [], [], None
    while len(posts) < POSTS_PER_TOPIC:
        params = {"q": topic, "sort": SORT, "limit": min(100, POSTS_PER_TOPIC - len(posts))}
        if LANGUAGE:
            params["lang"] = LANGUAGE
        if SINCE:
            params["since"] = SINCE
        if cursor:
            params["cursor"] = cursor
        data = get("app.bsky.feed.searchPosts", params)
        batch = data.get("posts", [])
        if not batch:
            break
        posts += batch
        cursor = data.get("cursor")
        if not cursor:
            break

    for p in posts:
        rkey = p["uri"].split("/")[-1]
        if rkey in seen_ids:
            continue
        seen_ids.add(rkey)
        rows.append(to_row(p, "post", topic))
        print(f"  - {clean(p['record'].get('text', ''))[:80]} ({p.get('replyCount', 0)} replies)")
        if FETCH_REPLIES and p.get("replyCount", 0) >= MIN_REPLIES_TO_FETCH:
            rows += collect_replies(p, topic)
    return rows


def main():
    if not HANDLE or not APP_PASSWORD:
        raise SystemExit("Missing credentials. Set BSKY_HANDLE and BSKY_APP_PASSWORD.")
    login()
    
    print("Hi")

    rows = []
    for topic in TOPICS:
        print(f"Topic: {topic}")
        rows += search_topic(topic)

    if not rows:
        print("Nothing found.")
        return

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    posts = sum(r["type"] == "post" for r in rows)
    print(f"\nSaved {posts} posts and {len(rows) - posts} replies to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

