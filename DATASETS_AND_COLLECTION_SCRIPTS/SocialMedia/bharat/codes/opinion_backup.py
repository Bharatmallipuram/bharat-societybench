

import csv
import os
import re
import sys
import time
from datetime import date, datetime, timezone

import praw
from prawcore.exceptions import PrawcoreException

# =============================================================================
# 1. SETTINGS
# =============================================================================

CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
USER_AGENT = "python:news-opinion-research:v1.1 (by /u/Mountain_Version2257)"

TOPIC = "NEET-UG 2024 paper leak and exam irregularities controversy (India)"

# ---- Keywords (repo: <=10 broad, minimal keywords; validation filters later)
KEYWORDS = [
    "NEET paper leak",
    "NEET 2024",
    "NEET-UG",
    "NEET scam",
    "NEET grace marks",
    "re-NEET",
    "NTA NEET",
    "NEET Supreme Court",
    "NEET CBI",
    "नीट पेपर लीक",
]

SEARCH_SCOPES = [
    "all",
    "india+IndiaSpeaks+unitedstatesofindia+indianews+JEENEETards+Indian_Academia",
]

# Reddit search has no date filter and returns at most ~250 posts per query,
# so each keyword is searched with several sort orders to reach more posts.
SORTS = ["relevance", "top", "comments", "new"]
SEARCH_LIMIT = 250

# ---- Time window (repo time_periods.py: 60-day pre-roll before the first
#      event burst, post-roll up to today)
DATE_FROM = "2024-03-01"
DATE_TO = date.today().isoformat()

REPLACE_MORE_LIMIT = 3
SKIP_AUTHORS = {"automoderator"}   # stickied rule reminders, not opinions

RAW_POSTS_FILE = "reddit_neet_raw_posts.csv"
OUTPUT_FILE = "valid_data_reddit_neet.csv"

# =============================================================================
# 2. VALIDATION TABLE (repo v1: anchor / entity / event / noise)
# =============================================================================

# ANCHOR: specific to this event; one hit alone makes a post valid.
ANCHOR_TERMS = [
    r"neet[- ]?(ug)?\s*(2024)?\s*paper[- ]?leak", r"paper[- ]?leak.{0,40}neet",
    r"re[- ]?neet", r"neet[- ]?(ug)?\s*(2024)?\s*scam", r"neet.{0,30}grace marks",
    r"grace marks.{0,30}neet", r"neet.{0,40}re[- ]?(exam|test)",
    r"hazaribagh", r"neet.{0,40}(toppers|720)", r"नीट",
    r"public examinations? \(prevention of unfair means\)",
    r"anti[- ]paper[- ]leak (law|act)",
]

# ENTITY: who/what the event is about.
ENTITY_TERMS = [
    r"\bneet\b", r"neet[- ]?ug", r"\bnta\b", r"national testing agency",
    r"subodh kumar singh", r"dharmendra pradhan", r"medical entrance",
]

# EVENT: what happened. Needs an ENTITY hit too.
EVENT_TERMS = [
    r"leak", r"scam", r"grace marks", r"irregularit", r"cheat", r"fraud",
    r"re[- ]?(exam|test)", r"cancel", r"\bcbi\b", r"supreme court",
    r"\bsc\b", r"court", r"arrest", r"probe", r"investigat",
    r"protest", r"controvers", r"\btoppers\b", r"\b(718|719|720)\b",
    r"solver gang", r"mafia", r"corrupt", r"resign", r"remov", r"sack",
    r"petition", r"hearing", r"verdict",
]
# ("result" is deliberately NOT an event term: every NEET year has results,
#  so it pulled in posts like "I got rank X in NEET 2024".)

# NOISE: any hit makes a post invalid.
NOISE_PATTERNS = [
    r"not in (employment|education)",        # "NEET" = unemployed youth
    r"\bneet[- ]?pg\b(?!.*neet[- ]?ug)",     # NEET-PG only (different exam)
    r"\bneet[- ]?(ss|mds)\b",
]
# Checked on the TITLE only: a post titled about a later NEET year is a
# different exam cycle (a 2024 post body may still mention "NEET 2025").
TITLE_NOISE_PATTERNS = [
    r"neet[- ]?(ug)?\s*(2025|2026)(?!.*2024)",
]

_c = lambda pats: [re.compile(p, re.IGNORECASE) for p in pats]
ANCHOR_RE, ENTITY_RE, EVENT_RE, NOISE_RE, TITLE_NOISE_RE = map(
    _c, (ANCHOR_TERMS, ENTITY_TERMS, EVENT_TERMS, NOISE_PATTERNS,
         TITLE_NOISE_PATTERNS)
)


def validate(title, body=""):
    """Returns (is_valid, reason) using the repo's v1 layered rule."""
    text = f"{title} {body}"
    for r in TITLE_NOISE_RE:
        if r.search(title):
            return False, f"noise:{r.pattern}"
    for r in NOISE_RE:
        if r.search(text):
            return False, f"noise:{r.pattern}"
    for r in ANCHOR_RE:
        if r.search(text):
            return True, f"anchor:{r.pattern}"
    ent = next((r.pattern for r in ENTITY_RE if r.search(text)), None)
    evt = next((r.pattern for r in EVENT_RE if r.search(text)), None)
    if ent and evt:
        return True, f"entity:{ent}+event:{evt}"
    if ent:
        return False, f"entity_only:{ent}"
    return False, "no_match"


# =============================================================================
# 3. OUTPUT FORMAT (repo FIELDS) + extra "subreddit" column (ignored by repo)
# =============================================================================

FIELDS = [
    "platform", "type", "id", "parent_id", "parent_comment_id", "user_id",
    "user_name", "title", "content", "create_time", "create_timestamp",
    "liked_count", "comment_count", "share_count", "ip_location",
    "source_keyword", "url", "subreddit",
]
RAW_FIELDS = [
    "id", "create_time", "subreddit", "title", "liked_count",
    "comment_count", "source_keyword", "valid", "reason", "url",
]

# =============================================================================
# HELPERS
# =============================================================================

def ts(day, end=False):
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.timestamp()


TS_FROM, TS_TO = ts(DATE_FROM), ts(DATE_TO, end=True)


def dt_str(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def clean(v):
    return (v or "").replace("\r", " ").replace("\n", " ").strip()


def author(thing):
    return str(thing.author) if thing.author else "[deleted]"


def user_id(thing):
    return getattr(thing, "author_fullname", "") or author(thing)


def open_for_write(path):
    """If the file is open in Excel, write to a timestamped copy instead."""
    try:
        return open(path, "w", newline="", encoding="utf-8-sig"), path
    except PermissionError:
        alt = path.replace(".csv", datetime.now().strftime("_%Y%m%d_%H%M%S.csv"))
        print(f"'{path}' is open in another program; writing '{alt}' instead.")
        return open(alt, "w", newline="", encoding="utf-8-sig"), alt


# =============================================================================
# STEP A: crawl posts
# =============================================================================

def crawl_posts(reddit):
    found = {}                       # id -> (submission, first keyword)
    for kw in KEYWORDS:
        for scope in SEARCH_SCOPES:
            for sort in SORTS:
                n_new = 0
                try:
                    for s in reddit.subreddit(scope).search(
                        kw, sort=sort, time_filter="all", limit=SEARCH_LIMIT
                    ):
                        if not (TS_FROM <= s.created_utc <= TS_TO):
                            continue
                        if s.id not in found:
                            found[s.id] = (s, kw)
                            n_new += 1
                except PrawcoreException as exc:
                    print(f"  search error [{kw} | {scope[:10]} | {sort}]: {exc}")
                print(f"  [{kw}] r/{scope[:12]:<12} {sort:<9} +{n_new:<4} "
                      f"total {len(found)}")
                time.sleep(1)
    return found


# =============================================================================
# STEP B: crawl comments of one valid post
# =============================================================================

def crawl_comments(s):
    rows = []
    try:
        s.comment_sort = "top"
        s.comments.replace_more(limit=REPLACE_MORE_LIMIT)
        comments = s.comments.list()
    except Exception as exc:
        print(f"    comments failed for {s.id}: {exc}")
        return rows

    for c in comments:
        body = clean(c.body)
        if not body or body in ("[deleted]", "[removed]"):
            continue
        if author(c).lower() in SKIP_AUTHORS:
            continue
        reply_to = c.parent_id.split("_", 1)[1] if c.parent_id.startswith("t1_") else ""
        rows.append({
            "platform": "reddit",
            "type": "comment",
            "id": c.id,
            "parent_id": s.id,                 # always the post (repo rule)
            "parent_comment_id": reply_to,     # set only for replies
            "user_id": user_id(c),
            "user_name": author(c),
            "title": "",
            "content": body,
            "create_time": dt_str(c.created_utc),
            "create_timestamp": int(c.created_utc),
            "liked_count": c.score,
            "comment_count": len(c.replies),   # = sub_comment_count
            "share_count": 0,
            "ip_location": "",                 # Reddit never provides it
            "source_keyword": "",
            "url": f"https://www.reddit.com{c.permalink}",
            "subreddit": str(s.subreddit),
        })
    return rows


def post_row(s, kw):
    return {
        "platform": "reddit",
        "type": "post",
        "id": s.id,
        "parent_id": "",
        "parent_comment_id": "",
        "user_id": user_id(s),
        "user_name": author(s),
        "title": clean(s.title),
        "content": clean(s.selftext) if s.is_self else s.url,
        "create_time": dt_str(s.created_utc),
        "create_timestamp": int(s.created_utc),
        "liked_count": s.score,
        "comment_count": s.num_comments,
        "share_count": getattr(s, "num_crossposts", 0),
        "ip_location": "",
        "source_keyword": kw,
        "url": f"https://www.reddit.com{s.permalink}",
        "subreddit": str(s.subreddit),
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("Missing Reddit credentials. Set REDDIT_CLIENT_ID and "
                 "REDDIT_CLIENT_SECRET in this terminal first.")

    reddit = praw.Reddit(client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
                         user_agent=USER_AGENT, timeout=30)
    reddit.read_only = True

    print(f"Topic : {TOPIC}\nWindow: {DATE_FROM} -> {DATE_TO}\n")
    print("STEP A  searching posts ...")
    found = crawl_posts(reddit)

    # ---- validate every post (repo v1 rule) ----
    print(f"\nSTEP B  validating {len(found)} posts ...")
    raw, valid_posts = [], []
    for sid, (s, kw) in found.items():
        ok, reason = validate(s.title, s.selftext or "")
        raw.append({
            "id": sid, "create_time": dt_str(s.created_utc),
            "subreddit": str(s.subreddit), "title": clean(s.title),
            "liked_count": s.score, "comment_count": s.num_comments,
            "source_keyword": kw, "valid": ok, "reason": reason,
            "url": f"https://www.reddit.com{s.permalink}",
        })
        if ok:
            valid_posts.append((s, kw))

    f, raw_path = open_for_write(RAW_POSTS_FILE)
    with f:
        w = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        w.writeheader()
        w.writerows(sorted(raw, key=lambda r: r["create_time"]))
    print(f"  valid posts: {len(valid_posts)} / {len(found)}  (all saved in {raw_path})")

    # ---- comments of valid posts ----
    print("\nSTEP C  fetching comments of valid posts ...")
    records, n_comments = [], 0
    valid_posts.sort(key=lambda x: x[0].created_utc)
    for i, (s, kw) in enumerate(valid_posts, 1):
        records.append(post_row(s, kw))
        cr = crawl_comments(s)
        records.extend(cr)
        n_comments += len(cr)
        print(f"  {i}/{len(valid_posts)} [{dt_str(s.created_utc)[:10]}] "
              f"r/{s.subreddit} {clean(s.title)[:55]} -> {len(cr)} comments")
        time.sleep(1)

    if not records:
        print("\nNo valid records.")
        return

    f, out_path = open_for_write(OUTPUT_FILE)
    with f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(records)

    print("\n" + "=" * 56)
    print(f"posts found     : {len(found)}")
    print(f"posts valid     : {len(valid_posts)}")
    print(f"comments saved  : {n_comments}")
    print(f"output          : {out_path}")
    print(f"raw post log    : {raw_path}")
    print("=" * 56)
    print("Next (SocietyBench step 0):")
    print(f"  python eval/media_step0_aggregate.py {out_path} output_neet "
          f"--stages neet_stages.json")


if __name__ == "__main__":
    main()