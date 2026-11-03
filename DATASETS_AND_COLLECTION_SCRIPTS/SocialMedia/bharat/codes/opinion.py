
import csv
import os
import time
from datetime import datetime, timezone

import praw
from prawcore.exceptions import (
    PrawcoreException,
    ResponseException,
    RequestException,
)

# ---------------- Credentials ----------------

CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
USER_AGENT = "news-opinion-research/1.0"

# ---------------- Topics ----------------
TOPICS = [
    "Russia-Ukraine war",
]

ARTICLE_URLS = [
]

# ---------------- Settings ----------------

DATE_FROM = "2024-01-01"
DATE_TO = "2024-12-31"

SUBREDDITS = "all"
SORT = "relevance"

# Number of search results requested per query.
SEARCH_POOL = 100

# Maximum posts retained per topic after filtering.
THREADS_PER_TOPIC = 5

# Maximum comments retained per post.
COMMENTS_PER_THREAD = 200

OUTPUT_FILE = "olympics_2024.csv"

COLUMNS = [
    "type", "id", "parent_id", "platform", "create_time",
    "title", "content", "liked_count", "comment_count",
    "share_count", "user_name", "ip_location",
    "source_keyword", "url", "stage", "total_comments",
    "top_comment_rank",
]

# ---------------- Reddit connection ----------------

if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit(
        "Missing Reddit credentials. Set REDDIT_CLIENT_ID "
        "and REDDIT_CLIENT_SECRET environment variables."
    )

reddit = praw.Reddit(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    user_agent=USER_AGENT,
    timeout=30,
)

seen_post_ids = set()
seen_comment_ids = set()


# ---------------- Helper functions ----------------

def iso(timestamp):
    return datetime.fromtimestamp(
        timestamp, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(value):
    return (value or "").replace("\r", " ").replace(
        "\n", " "
    ).strip()


def date_timestamp(date_string, end_of_day=False):
    if not date_string:
        return None

    dt = datetime.strptime(
        date_string, "%Y-%m-%d"
    ).replace(tzinfo=timezone.utc)

    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)

    return dt.timestamp()


TS_FROM = date_timestamp(DATE_FROM)
TS_TO = date_timestamp(DATE_TO, end_of_day=True)


def in_range(submission):
    created = submission.created_utc

    if TS_FROM is not None and created < TS_FROM:
        return False

    if TS_TO is not None and created > TS_TO:
        return False

    return True


def parent_id_of(comment):
    # t1_xxx = comment parent; t3_xxx = submission parent.
    return comment.parent_id.split("_", 1)[-1]


# ---------------- Collect a thread ----------------

def collect_thread(submission, keyword):
    rows = []

    # Do not duplicate the same submission across topics.
    is_new_post = submission.id not in seen_post_ids

    if is_new_post:
        seen_post_ids.add(submission.id)

        post_content = (
            clean(submission.selftext)
            if submission.is_self
            else submission.url
        )

        rows.append({
            "type": "post",
            "id": submission.id,
            "parent_id": "",
            "platform": "reddit",
            "create_time": iso(submission.created_utc),
            "title": clean(submission.title),
            "content": post_content,
            "liked_count": submission.score,
            "comment_count": submission.num_comments,
            "share_count": getattr(
                submission, "num_crossposts", 0
            ),
            "user_name": (
                str(submission.author)
                if submission.author else "[deleted]"
            ),
            "ip_location": "",
            "source_keyword": keyword,
            "url": f"https://www.reddit.com{submission.permalink}",
            "stage": "post",
            "total_comments": submission.num_comments,
            "top_comment_rank": "",
        })

    # Avoid fetching the same comments repeatedly when the post
    # has already been collected through another topic.
    if not is_new_post:
        return rows

    try:
        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)
        comments = submission.comments.list()

        # Keep the highest-ranked comments returned by Reddit.
        comments = comments[:COMMENTS_PER_THREAD]

        comment_rows = []

        for comment in comments:
            if comment.id in seen_comment_ids:
                continue

            body = clean(comment.body)

            if not body or body in ("[deleted]", "[removed]"):
                continue

            seen_comment_ids.add(comment.id)

            comment_rows.append({
                "type": "comment",
                "id": comment.id,
                "parent_id": parent_id_of(comment),
                "platform": "reddit",
                "create_time": iso(comment.created_utc),
                "title": clean(submission.title),
                "content": body,
                "liked_count": comment.score,
                "comment_count": len(comment.replies),
                "share_count": 0,
                "user_name": (
                    str(comment.author)
                    if comment.author else "[deleted]"
                ),
                "ip_location": "",
                "source_keyword": keyword,
                "url": f"https://www.reddit.com{comment.permalink}",
                "stage": (
                    "top-level comment"
                    if comment.parent_id.startswith("t3_")
                    else "reply"
                ),
                "total_comments": submission.num_comments,
                "top_comment_rank": 0,
            })

        # Rank collected comments by score.
        comment_rows.sort(
            key=lambda row: row["liked_count"],
            reverse=True,
        )

        for rank, row in enumerate(comment_rows, start=1):
            row["top_comment_rank"] = rank

        rows.extend(comment_rows)

    except (PrawcoreException, Exception) as exc:
        print(
            f"    Could not fetch comments for "
            f"{submission.id}: {exc}"
        )

    return rows


# ---------------- Search Reddit ----------------

def search_topic(topic):
    """
    Fetch candidate posts, then apply the requested date range.
    Reddit search may not return all historical posts.
    """
    candidates = {}

    try:
        results = reddit.subreddit(SUBREDDITS).search(
            topic,
            sort=SORT,
            time_filter="all",
            syntax="lucene",
            limit=SEARCH_POOL,
        )

        for submission in results:
            if not in_range(submission):
                continue

            candidates[submission.id] = submission

    except PrawcoreException as exc:
        print(f"  Search error for '{topic}': {exc}")

    # Sort candidates by score so results are deterministic.
    ordered = sorted(
        candidates.values(),
        key=lambda item: (item.score, item.created_utc),
        reverse=True,
    )

    return ordered[:THREADS_PER_TOPIC]


def search_article_url(url):
    """Find Reddit submissions associated with an article URL."""
    try:
        # Reddit's info endpoint can return no results for some URLs.
        return list(reddit.info(url=url))[:THREADS_PER_TOPIC]

    except PrawcoreException as exc:
        print(f"  Article lookup failed: {exc}")
        return []


# ---------------- Main program ----------------

def main():
    all_rows = []

    for topic in TOPICS:
        print(f"\nTopic: {topic}")

        submissions = search_topic(topic)

        if not submissions:
            print("  No matching posts found in the requested dates.")
            continue

        for submission in submissions:
            print(
                f"  - [{iso(submission.created_utc)[:10]}] "
                f"{clean(submission.title)[:80]} "
                f"({submission.num_comments} comments)"
            )

            all_rows.extend(collect_thread(submission, topic))

    for url in ARTICLE_URLS:
        if not url.strip():
            continue

        print(f"\nArticle: {url}")

        for submission in search_article_url(url):
            if not in_range(submission):
                continue

            print(f"  - {clean(submission.title)[:80]}")

            all_rows.extend(collect_thread(submission, url))

    if not all_rows:
        print("\nNo records collected.")
        return

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    posts = sum(row["type"] == "post" for row in all_rows)
    comments = len(all_rows) - posts

    print(f"\nSaved to: {OUTPUT_FILE}")
    print(f"Posts: {posts}")
    print(f"Comments: {comments}")
    print(f"Total rows: {len(all_rows)}")


if __name__ == "__main__":
    main()
