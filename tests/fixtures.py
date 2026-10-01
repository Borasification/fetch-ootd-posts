"""
Shared fixtures for the year review tests.
"""

from datetime import datetime, timezone

from ootd_awards.dataset import Post
from ootd_awards.period import Period

YEAR_2025 = Period.parse('2025')
# Synthetic upload hash (not a real forum image): 62**3 + 36*62 + 10 -> base62 '1Aa'
SHA1 = format(62 ** 2 + 36 * 62 + 10, '040x')
BASE62 = '1Aa'


def make_post(post_id, username, month, likes_30d, like_count=None,
              first_ootd_at=None, day=1, uploads=None):
    created_at = datetime(2025, month, day, 12, 0, tzinfo=timezone.utc)
    return Post(
        id=post_id,
        topic_id=13530,
        slug='outfit-of-the-day-part-12bis',
        topic_title='Outfit of the day - Part 12bis',
        post_number=post_id,
        username=username,
        created_at=created_at,
        like_count=likes_30d if like_count is None else like_count,
        likes_30d=likes_30d,
        first_ootd_at=first_ootd_at or datetime(2021, 1, 1, tzinfo=timezone.utc),
        uploads=uploads if uploads is not None else [
            {'sha1': SHA1, 'url': f'https://assets.example.com/original/3X/{SHA1}.jpeg',
             'width': 1536, 'height': 2040},
        ],
    )


def sample_posts():
    """A small year: alice dominates, bob is steady, carol is a 2025 newcomer."""
    newcomer = datetime(2025, 3, 2, tzinfo=timezone.utc)
    return [
        make_post(1, 'alice', 1, 70),
        make_post(2, 'alice', 1, 68),
        make_post(3, 'alice', 2, 66),
        make_post(4, 'bob', 2, 40),
        make_post(5, 'bob', 3, 41),
        make_post(6, 'bob', 3, 42),
        make_post(7, 'bob', 4, 43),
        make_post(8, 'bob', 12, 65, like_count=65),
        make_post(9, 'carol', 3, 30, first_ootd_at=newcomer),
        make_post(10, 'carol', 4, 35, first_ootd_at=newcomer),
        make_post(11, 'carol', 5, 36, first_ootd_at=newcomer),
        make_post(12, 'carol', 6, 37, first_ootd_at=newcomer),
        make_post(13, 'carol', 7, 50, first_ootd_at=newcomer),
        make_post(14, 'dave', 12, 20, like_count=10),
    ]
