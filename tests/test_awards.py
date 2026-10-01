"""
Tests for the year review award rules.
"""

from ootd_awards.awards import (
    compute_awards, member_stats, monthly_winners, most_consistent, percentile, rising_stars, top_outfits,
)
from ootd_awards.period import Period
from tests.fixtures import YEAR_2025, make_post, sample_posts


class TestTopOutfits:

    def test_ranks_by_30_day_likes(self):
        top = top_outfits(sample_posts(), n=3, max_per_member=3)
        assert [p.id for p in top] == [1, 2, 3]

    def test_caps_outfits_per_member(self):
        top = top_outfits(sample_posts(), n=4, max_per_member=2)
        assert [p.id for p in top] == [1, 2, 8, 13]

    def test_ties_broken_by_total_likes_then_date(self):
        posts = [
            make_post(1, 'a', 2, 50, like_count=55),
            make_post(2, 'b', 1, 50, like_count=60),
            make_post(3, 'c', 1, 50, like_count=55),
        ]
        assert [p.id for p in top_outfits(posts)] == [2, 3, 1]


class TestMonthlyWinners:

    def test_one_winner_per_month(self):
        winners = monthly_winners(sample_posts())
        assert sorted(winners) == [1, 2, 3, 4, 5, 6, 7, 12]
        assert winners[1].id == 1
        assert winners[3].id == 6
        assert winners[12].id == 8


class TestMembers:

    def test_member_of_the_year_uses_best_outfits(self):
        awards = compute_awards(sample_posts(), YEAR_2025)
        assert [m.username for m in awards.members][:3] == ['bob', 'alice', 'carol']
        assert awards.member('alice').best_n_score == 204

    def test_best_month(self):
        stats = member_stats(sample_posts(), 10)
        assert stats['bob'].best_month == 3
        assert stats['alice'].best_month == 1

    def test_rising_star_requires_first_outfit_this_year(self):
        stats = member_stats(sample_posts(), 10)
        assert [m.username for m in rising_stars(stats, YEAR_2025)] == ['carol']
        assert rising_stars(stats, Period.parse('2024')) == []

    def test_rising_star_requires_min_outfits(self):
        # carol has 5 outfits: enough for a year (5), dropping one is not
        posts = [p for p in sample_posts() if p.id != 13]
        assert rising_stars(member_stats(posts, 10), YEAR_2025) == []


class TestConsistency:

    def test_percentile(self):
        assert percentile([1, 2, 3, 4, 5], 0.5) == 3
        assert percentile([10, 20], 0.75) == 17.5
        assert percentile([], 0.75) == 0

    def test_most_consistent_counts_outfits_above_threshold(self):
        threshold, ranking = most_consistent(sample_posts())
        assert threshold == 61.25
        assert ranking == [('alice', 3), ('bob', 1)]


class TestPillars:

    def test_ranked_by_outfits_then_likes(self):
        awards = compute_awards(sample_posts(), YEAR_2025)
        # bob and carol both posted 5 outfits: bob has more likes
        assert [(m.username, m.count) for m in awards.pillars] == [
            ('bob', 5), ('carol', 5), ('alice', 3), ('dave', 1),
        ]


class TestComputeAwards:

    def test_headline_stats(self):
        awards = compute_awards(sample_posts(), YEAR_2025)
        assert len(awards.outfits) == 14
        assert awards.busiest_month == 3
        assert awards.winner.id == 1
        assert awards.member_rank('carol') == 3

    def test_empty_year(self):
        awards = compute_awards([], YEAR_2025)
        assert awards.winner is None
        assert awards.busiest_month is None
