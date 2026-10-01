"""
Tests for the year review dataset loader (Data Explorer paging and cache).
"""

from unittest.mock import Mock

import pytest

from ootd_awards.dataset import (
    POSTS, load_fans, load_posts, missing_months, parse_row, run_paginated, run_single_page,
)
from ootd_awards.period import Period

YEAR_2025 = Period.parse('2025')


def row(post_id, created_at='2025-02-18T07:14:07.737Z'):
    return {
        'id': post_id, 'topic_id': 1, 'slug': 's', 'topic_title': 't', 'post_number': post_id,
        'username': 'alice', 'created_at': created_at, 'like_count': 3, 'likes_30d': 2,
        'first_ootd_at': None, 'uploads': '[{"sha1": "ab", "url": "x.jpg", "width": 1, "height": 2}]',
    }


def paging_client(rows):
    """Fake client that honours after_id and limit like year_posts.sql does."""
    client = Mock()

    def run_query(query_id, params, limit):
        return [
            r for r in rows
            if r['id'] > params.get('after_id', 0)
            and params.get('start_date', '') <= r.get('created_at', '')[:10] < params.get('end_date', '9999')
        ][:limit]

    client.run_query.side_effect = run_query
    return client


class TestPaging:

    def test_pages_until_short_page(self):
        client = paging_client([row(i) for i in range(1, 8)])
        rows = run_paginated(client, 1, {}, page_size=3)
        assert [r['id'] for r in rows] == list(range(1, 8))
        assert [c.args[1]['after_id'] for c in client.run_query.call_args_list] == [0, 3, 6]

    def test_exact_multiple_of_page_size(self):
        client = paging_client([row(i) for i in range(1, 7)])
        assert len(run_paginated(client, 1, {}, page_size=3)) == 6
        assert client.run_query.call_count == 3

    def test_single_page_refuses_truncated_results(self):
        client = paging_client([row(i) for i in range(1, 4)])
        with pytest.raises(RuntimeError, match='truncated'):
            run_single_page(client, 1, {}, page_size=3)


class TestLoadPosts:

    def test_fetches_month_by_month_then_uses_cache(self, tmp_path):
        client = paging_client([row(1, '2025-01-31T23:59:00Z'), row(2, '2025-02-01T00:00:00Z'),
                                row(3, '2025-12-31T10:00:00Z'), row(4, '2026-01-01T00:00:00Z')])
        posts = load_posts(client, 1, YEAR_2025, tmp_path, log=lambda _: None)
        assert [p.id for p in posts] == [1, 2, 3]
        assert client.run_query.call_count == 12
        assert (tmp_path / 'posts_2025-01.jsonl').exists()
        assert (tmp_path / 'posts_2025-12.jsonl').exists()

        client.run_query.reset_mock()
        assert len(load_posts(client, 1, YEAR_2025, tmp_path, log=lambda _: None)) == 3
        client.run_query.assert_not_called()

    def test_months_cached_by_a_quarter_serve_a_month_and_the_year(self, tmp_path):
        client = paging_client([row(1, '2025-01-15T10:00:00Z'), row(2, '2025-03-15T10:00:00Z'),
                                row(3, '2025-07-15T10:00:00Z')])
        load_posts(client, 1, Period.parse('2025-Q1'), tmp_path, log=lambda _: None)
        assert client.run_query.call_count == 3

        client.run_query.reset_mock()
        march = load_posts(None, 1, Period.parse('2025-03'), tmp_path, log=lambda _: None)
        assert [p.id for p in march] == [2]
        assert missing_months(Period.parse('2025'), tmp_path, POSTS) == [f'2025-{m:02d}' for m in range(4, 13)]

        year = load_posts(client, 1, YEAR_2025, tmp_path, log=lambda _: None)
        assert [p.id for p in year] == [1, 2, 3]
        # only the 9 months not cached by the quarter are queried
        assert client.run_query.call_count == 9

    def test_missing_cache_without_client(self, tmp_path):
        with pytest.raises(RuntimeError, match='fetch'):
            load_posts(None, 1, YEAR_2025, tmp_path)

    def test_parse_row_decodes_uploads_json(self):
        post = parse_row(row(1))
        assert post.uploads == [{'sha1': 'ab', 'url': 'x.jpg', 'width': 1, 'height': 2}]
        assert post.created_at.year == 2025


class TestLoadFans:

    def test_sums_months_before_picking_biggest_fan(self, tmp_path):
        monthly = {
            '2025-01-01': [{'username': 'alice', 'fan': 'bob', 'likes': 5},
                           {'username': 'alice', 'fan': 'carol', 'likes': 3}],
            '2025-02-01': [{'username': 'alice', 'fan': 'carol', 'likes': 4},
                           {'username': 'dave', 'fan': 'erin', 'likes': 2},
                           {'username': 'dave', 'fan': 'bob', 'likes': 2}],
        }
        client = Mock()
        client.run_query.side_effect = lambda query_id, params, limit: monthly.get(params['start_date'], [])

        fans = load_fans(client, 2, YEAR_2025, tmp_path, log=lambda _: None)

        # carol wins over the year (7) although bob won January alone (5)
        assert fans['alice'] == {'fan': 'carol', 'likes': 7}
        # ties broken alphabetically
        assert fans['dave'] == {'fan': 'bob', 'likes': 2}


class TestExclusions:

    def test_parse_post_ref(self):
        from ootd_awards.dataset import parse_post_ref
        # synthetic topic/post numbers
        assert parse_post_ref('https://forum.example.com/t/outfit-of-the-day-part-7/500/42') == (500, 42)
        assert parse_post_ref('500/42') == (500, 42)
        # a topic link: "part-7/500" must not be read as topic 7, post 500
        assert parse_post_ref('https://forum.example.com/t/outfit-of-the-day-part-7/500') is None
        assert parse_post_ref('https://forum.example.com/t/outfit-of-the-day-part-7/500/42?u=someone') == (500, 42)
        assert parse_post_ref('https://forum.example.com/t/outfit-of-the-day-part-7/500/42  # a note') == (500, 42)
        assert parse_post_ref('part-7/500') is None

    def test_add_list_and_apply(self, tmp_path):
        from ootd_awards.dataset import add_exclusion, exclude_posts, load_exclusions
        url = 'https://forum.example.com/t/s/1/2'
        assert add_exclusion(tmp_path, url, 'photo de savon') == (1, 2)
        add_exclusion(tmp_path, url)  # adding twice keeps one line
        assert (tmp_path / 'excluded_posts.txt').read_text().splitlines() == [f'{url}  # photo de savon']
        exclusions = load_exclusions(tmp_path)
        assert exclusions == {(1, 2)}

        posts = [parse_row(row(2)), parse_row(row(3))]  # row() puts every post in topic 1
        assert [p.post_number for p in exclude_posts(posts, exclusions)] == [3]

    def test_rejects_topic_link(self, tmp_path):
        from ootd_awards.dataset import add_exclusion
        with pytest.raises(ValueError, match='Not a post link'):
            add_exclusion(tmp_path, 'https://forum.example.com/t/slug/500')
