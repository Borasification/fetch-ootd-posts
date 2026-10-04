"""
Load a period of outfits from the Data Explorer queries, with a local JSONL cache.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from .constants import DATA_EXPLORER_MAX_ROWS
from .period import Period


@dataclass
class Post:
    """An outfit post, as returned by year_posts.sql."""
    id: int
    topic_id: int
    slug: str
    topic_title: str
    post_number: int
    username: str
    created_at: datetime
    like_count: int
    likes_30d: int
    first_ootd_at: Optional[datetime]
    uploads: List[Dict] = field(default_factory=list)
    avatar: Optional[str] = None  # profile picture URL; None for default letter avatars

    @property
    def path(self) -> str:
        """Forum-relative URL of the post."""
        return f'/t/{self.slug}/{self.topic_id}/{self.post_number}'

    @property
    def month(self) -> int:
        return self.created_at.month


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse the ISO timestamps returned by Data Explorer (e.g. 2025-02-18T07:14:07.737Z)."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def parse_row(row: Dict) -> Post:
    """Convert a Data Explorer row into a Post."""
    uploads = row.get('uploads') or []
    if isinstance(uploads, str):
        uploads = json.loads(uploads)
    return Post(
        id=int(row['id']),
        topic_id=int(row['topic_id']),
        slug=row['slug'],
        topic_title=row['topic_title'],
        post_number=int(row['post_number']),
        username=row['username'],
        created_at=parse_datetime(row['created_at']),
        like_count=int(row['like_count'] or 0),
        likes_30d=int(row['likes_30d'] or 0),
        first_ootd_at=parse_datetime(row.get('first_ootd_at')),
        uploads=[u for u in uploads if u],
        avatar=row.get('avatar_url') or None,
    )


def run_paginated(client, query_id: int, params: Dict, page_size: int = DATA_EXPLORER_MAX_ROWS) -> List[Dict]:
    """
    Run a query that pages by post id (see year_posts.sql :after_id).

    Data Explorer caps each run at page_size rows, so keep asking for rows
    after the last id until a page comes back short.
    """
    rows, after_id = [], 0
    while True:
        page = client.run_query(query_id, {**params, 'after_id': after_id}, limit=page_size)
        rows.extend(page)
        if len(page) < page_size:
            return rows
        after_id = page[-1]['id']


def run_single_page(client, query_id: int, params: Dict, page_size: int = DATA_EXPLORER_MAX_ROWS) -> List[Dict]:
    """Run a query expected to fit in one page; fail rather than silently truncate."""
    rows = client.run_query(query_id, params, limit=page_size)
    if len(rows) >= page_size:
        raise RuntimeError(f'Query {query_id} returned {len(rows)} rows, the Data Explorer maximum: '
                           f'results may be truncated')
    return rows


POSTS, FANS = 'posts', 'fans'


def month_cache_file(cache_dir: Path, kind: str, month_key: str) -> Path:
    """Cache file of one month of query results, e.g. data/posts_2026-03.jsonl."""
    return cache_dir / f'{kind}_{month_key}.jsonl'


def missing_months(period: Period, cache_dir: Path, kind: str) -> List[str]:
    """Months of the period (YYYY-MM) that have no cached results yet."""
    return [start[:7] for start, _ in period.month_windows()
            if not month_cache_file(cache_dir, kind, start[:7]).exists()]


def _load_rows(client, query_id: int, period: Period, cache_dir: Path, kind: str, refresh: bool, runner,
               log: Callable[[str], None]) -> List[Dict]:
    """
    Return the period's query rows, assembled from one cache file per month.

    Months are cached separately so that any period reuses what was already
    fetched (a quarter's fetch also serves its three months, and a year is
    built from its months). Missing months are queried, as are all months
    when refreshing; queries run one month at a time because a longer range
    exceeds the Data Explorer statement timeout or its 10,000-row limit.
    """
    rows = []
    for start_date, end_date in period.month_windows():
        cache_file = month_cache_file(cache_dir, kind, start_date[:7])
        if cache_file.exists() and not refresh:
            with open(cache_file, encoding='utf-8') as f:
                rows.extend(json.loads(line) for line in f if line.strip())
            continue

        if client is None:
            raise RuntimeError(f'{cache_file} not found; run the fetch command first')
        month_rows = runner(client, query_id, {'start_date': start_date, 'end_date': end_date})
        log(f'  {kind} {start_date[:7]}: {len(month_rows)} rows')
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.writelines(f'{json.dumps(row, ensure_ascii=False)}\n' for row in month_rows)
        rows.extend(month_rows)
    return rows


def load_posts(client, query_id: int, period: Period, cache_dir: Path, refresh: bool = False,
               log: Callable[[str], None] = print) -> List[Post]:
    """Load the period's outfit posts, sorted by creation date."""
    rows = _load_rows(client, query_id, period, cache_dir, POSTS, refresh, run_paginated, log)
    return sorted((parse_row(row) for row in rows), key=lambda p: p.created_at)


def load_fans(client, query_id: int, period: Period, cache_dir: Path, refresh: bool = False,
              log: Callable[[str], None] = print) -> Dict[str, Dict]:
    """
    Load each member's biggest fan over the period: {username: {'fan': ..., 'likes': ...}}.

    fans.sql returns like counts per (member, fan) pair for each month;
    they are summed over the period before picking the top fan.
    """
    rows = _load_rows(client, query_id, period, cache_dir, FANS, refresh, run_single_page, log)
    likes = Counter()
    for row in rows:
        likes[(row['username'], row['fan'])] += int(row['likes'])

    fans = {}
    for (username, fan), count in sorted(likes.items(), key=lambda item: (-item[1], item[0][1])):
        fans.setdefault(username, {'fan': fan, 'likes': count})
    return fans


# Posts in OOTD topics that are not outfits (a product photo, an inspiration
# collage...). No image rule can tell them apart reliably, so the admin lists
# them by hand. The file lives in data/ and is never committed.
EXCLUSIONS_FILE = 'excluded_posts.txt'
POST_URL = re.compile(r'/t/[^/\s]+/(\d+)/(\d+)(?:[/?#\s]|$)')
POST_PAIR = re.compile(r'^\s*(\d+)/(\d+)\s*$')


def parse_post_ref(text: str) -> Optional[Tuple[int, int]]:
    """(topic_id, post_number) from a post URL (.../t/slug/500/42) or exactly '500/42'."""
    match = POST_URL.search(text) if '/t/' in text else POST_PAIR.match(text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def load_exclusions(cache_dir: Path) -> Set[Tuple[int, int]]:
    """Posts listed in data/excluded_posts.txt, one URL per line, # for comments."""
    path = cache_dir / EXCLUSIONS_FILE
    if not path.exists():
        return set()
    refs = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        ref = parse_post_ref(line.split('#', 1)[0])
        if ref:
            refs.add(ref)
    return refs


def add_exclusion(cache_dir: Path, url: str, reason: str = '') -> Tuple[int, int]:
    """Append a post to the exclusion list; returns its (topic_id, post_number)."""
    ref = parse_post_ref(url)
    if ref is None:
        raise ValueError(f'Not a post link: {url!r} (expected .../t/<slug>/<topic>/<post number>)')
    if ref not in load_exclusions(cache_dir):
        cache_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_dir / EXCLUSIONS_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{url.strip()}{f'  # {reason}' if reason else ''}\n")
    return ref


def exclude_posts(posts: List[Post], exclusions: Set[Tuple[int, int]]) -> List[Post]:
    return [p for p in posts if (p.topic_id, p.post_number) not in exclusions]
