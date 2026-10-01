"""
Award rules for the OOTD review of a period (year, quarter or month).

Pure functions over a list of Post objects. Outfits are ranked by likes
received in their first 30 days, so an outfit posted at the end of the
period competes fairly with one posted at the start; total likes break ties.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Dict, List, Optional, Tuple

from .dataset import Post
from .period import Period

TOP_N = 10
MAX_PER_MEMBER_IN_TOP = 2
CONSISTENCY_PERCENTILE = 0.75


def rank_key(post: Post) -> Tuple:
    """Sort key: likes in the first 30 days, then total likes, then earliest."""
    return (-post.likes_30d, -post.like_count, post.created_at)


def ranked(posts: List[Post]) -> List[Post]:
    return sorted(posts, key=rank_key)


def top_outfits(posts: List[Post], n: int = TOP_N, max_per_member: int = MAX_PER_MEMBER_IN_TOP) -> List[Post]:
    """Best n outfits, with at most max_per_member outfits from the same member."""
    selected = []
    per_member = Counter()
    for post in ranked(posts):
        if per_member[post.username] >= max_per_member:
            continue
        selected.append(post)
        per_member[post.username] += 1
        if len(selected) == n:
            break
    return selected


def monthly_winners(posts: List[Post]) -> Dict[int, Post]:
    """Best outfit of each calendar month: {month: post}."""
    by_month = defaultdict(list)
    for post in posts:
        by_month[post.month].append(post)
    return {month: ranked(month_posts)[0] for month, month_posts in sorted(by_month.items())}


@dataclass
class MemberStats:
    """A member's period, computed from their outfits."""
    username: str
    best_n: int  # number of best outfits summed in best_n_score
    outfits: List[Post] = field(default_factory=list)  # ranked, best first

    @property
    def count(self) -> int:
        return len(self.outfits)

    @property
    def total_likes(self) -> int:
        return sum(p.like_count for p in self.outfits)

    @property
    def best_n_score(self) -> int:
        """Sum of 30-day likes of the member's best_n best outfits."""
        return sum(p.likes_30d for p in self.outfits[:self.best_n])

    @property
    def median_likes(self) -> float:
        return median(p.likes_30d for p in self.outfits)

    @property
    def best_month(self) -> int:
        """Month in which the member's outfits gathered the most 30-day likes."""
        likes_by_month = Counter()
        for post in self.outfits:
            likes_by_month[post.month] += post.likes_30d
        return min(likes_by_month, key=lambda month: (-likes_by_month[month], month))


def member_stats(posts: List[Post], best_n: int) -> Dict[str, MemberStats]:
    stats = {}
    for post in ranked(posts):
        stats.setdefault(post.username, MemberStats(post.username, best_n)).outfits.append(post)
    return stats


def rank_members(stats: Dict[str, MemberStats]) -> List[MemberStats]:
    """Members ranked by the sum of their best outfits, rewarding quality over volume."""
    return sorted(stats.values(), key=lambda m: (-m.best_n_score, -m.total_likes, m.username))


def pillars(stats: Dict[str, MemberStats]) -> List[MemberStats]:
    """Members ranked by outfits posted ("Pilier de l'OOTD"), then total likes: presence over peaks."""
    return sorted(stats.values(), key=lambda m: (-m.count, -m.total_likes, m.username))


def rising_stars(stats: Dict[str, MemberStats], period: Period) -> List[MemberStats]:
    """Members whose first OOTD ever falls in the period, ranked by median 30-day likes."""
    newcomers = [
        m for m in stats.values()
        if m.count >= period.min_outfits
        and period.contains(m.outfits[0].first_ootd_at)
    ]
    return sorted(newcomers, key=lambda m: (-m.median_likes, -m.best_n_score, m.username))


def percentile(values: List[int], fraction: float) -> float:
    """Linear-interpolated percentile (fraction in [0, 1])."""
    ordered = sorted(values)
    if not ordered:
        return 0
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def most_consistent(posts: List[Post],
                    fraction: float = CONSISTENCY_PERCENTILE) -> Tuple[float, List[Tuple[str, int]]]:
    """
    Members with the most outfits above the period's percentile of 30-day likes.

    Returns:
        (threshold, [(username, outfits_above_threshold), ...]) best first
    """
    threshold = percentile([p.likes_30d for p in posts], fraction)
    counts = Counter(p.username for p in posts if p.likes_30d > threshold)
    return threshold, sorted(counts.items(), key=lambda item: (-item[1], item[0]))


@dataclass
class Awards:
    period: Period
    outfits: List[Post]
    top: List[Post]
    monthly: Dict[int, Post]
    members: List[MemberStats]
    rising: List[MemberStats]
    consistency_threshold: float
    consistent: List[Tuple[str, int]]
    pillars: List[MemberStats]

    @property
    def winner(self) -> Optional[Post]:
        """Outfit of the period."""
        return self.top[0] if self.top else None

    @property
    def total_likes(self) -> int:
        return sum(p.like_count for p in self.outfits)

    @property
    def busiest_month(self) -> Optional[int]:
        counts = Counter(p.month for p in self.outfits)
        return min(counts, key=lambda month: (-counts[month], month)) if counts else None

    def member(self, username: str) -> Optional[MemberStats]:
        """Member by username, case-insensitive like Discourse usernames."""
        return next((m for m in self.members if m.username.lower() == username.lower()), None)

    def member_rank(self, username: str) -> Optional[int]:
        return next((i for i, m in enumerate(self.members, 1) if m.username == username), None)


def compute_awards(posts: List[Post], period: Period) -> Awards:
    """Compute every award from a period of OOTD posts."""
    outfits = list(posts)
    stats = member_stats(outfits, period.member_best_n)
    threshold, consistent = most_consistent(outfits)
    return Awards(
        period=period,
        outfits=outfits,
        top=top_outfits(outfits),
        monthly=monthly_winners(outfits),
        members=rank_members(stats),
        rising=rising_stars(stats, period),
        consistency_threshold=threshold,
        consistent=consistent,
        pillars=pillars(stats),
    )
