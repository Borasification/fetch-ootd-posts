"""
Tests for review periods (year, quarter, month).
"""

from datetime import date, datetime, timezone

import pytest

from ootd_awards import publish
from ootd_awards.awards import compute_awards
from ootd_awards.period import Period
from ootd_awards.render import member_honours, render_awards, render_wrapped
from tests.fixtures import make_post, sample_posts


class TestParse:

    @pytest.mark.parametrize('text, kind, key, label', [
        ('2025', 'year', '2025', '2025'),
        ('2026-Q1', 'quarter', '2026-Q1', 'T1 2026'),
        ('2026-q3', 'quarter', '2026-Q3', 'T3 2026'),
        ('2026-03', 'month', '2026-03', 'mars 2026'),
    ])
    def test_parse(self, text, kind, key, label):
        period = Period.parse(text)
        assert (period.kind, period.key, period.label) == (kind, key, label)

    @pytest.mark.parametrize('text', ['2026-Q5', '2026-13', '26', 'Q1-2026', ''])
    def test_invalid(self, text):
        with pytest.raises(ValueError):
            Period.parse(text)


class TestDates:

    def test_quarter_bounds_and_windows(self):
        q3 = Period.parse('2026-Q3')
        assert (q3.start, q3.end) == (date(2026, 7, 1), date(2026, 10, 1))
        assert q3.month_windows(today=date(2026, 12, 1)) == [('2026-07-01', '2026-08-01'), ('2026-08-01', '2026-09-01'),
                                      ('2026-09-01', '2026-10-01')]

    def test_future_months_are_left_out(self):
        year = Period.parse('2026')
        windows = year.month_windows(today=date(2026, 9, 29))
        assert windows[-1] == ('2026-09-01', '2026-10-01')
        assert len(windows) == 9
        assert Period.parse('2026-Q4').month_windows(today=date(2026, 9, 29)) == []

    def test_december_rolls_over(self):
        assert Period.parse('2026-Q4').end == date(2027, 1, 1)
        assert Period.parse('2026-12').month_windows(today=date(2027, 1, 1)) == [('2026-12-01', '2027-01-01')]
        assert len(Period.parse('2025').month_windows()) == 12

    def test_contains(self):
        q1 = Period.parse('2026-Q1')
        assert q1.contains(datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc))
        assert not q1.contains(datetime(2026, 4, 1, tzinfo=timezone.utc))
        assert not q1.contains(None)

    def test_provisional_until_30_days_after_end(self):
        q3 = Period.parse('2026-Q3')
        assert q3.settles_on == date(2026, 10, 31)
        assert q3.is_provisional(date(2026, 9, 29))
        assert q3.is_provisional(date(2026, 10, 30))
        assert not q3.is_provisional(date(2026, 10, 31))
        assert not Period.parse('2026-Q1').is_provisional(date(2026, 9, 29))

    def test_rules_scale_with_length(self):
        assert (Period.parse('2025').member_best_n, Period.parse('2025').min_outfits) == (10, 5)
        assert (Period.parse('2026-Q1').member_best_n, Period.parse('2026-Q1').min_outfits) == (5, 3)
        assert (Period.parse('2026-03').member_best_n, Period.parse('2026-03').min_outfits) == (3, 2)


def quarter_posts():
    """Q1 2025 slice of the sample year: alice (3 outfits), bob (3), carol (1, newcomer)."""
    return [p for p in sample_posts() if p.month <= 3]


class TestQuarterAwards:

    def test_rising_star_uses_quarter_bounds_and_minimum(self):
        q1 = Period.parse('2025-Q1')
        newcomer = datetime(2025, 2, 1, tzinfo=timezone.utc)
        posts = [make_post(i, 'zoe', 2, 20, first_ootd_at=newcomer) for i in (100, 101, 102)]
        awards = compute_awards(quarter_posts() + posts, q1)
        # 3 outfits are enough for a quarter; carol started in March but has only 1
        assert [m.username for m in awards.rising] == ['zoe']

    def test_member_ranking_sums_best_five(self):
        awards = compute_awards(quarter_posts(), Period.parse('2025-Q1'))
        assert awards.members[0].best_n == 5

    def test_rendering_uses_quarter_wording(self):
        awards = compute_awards(quarter_posts(), Period.parse('2025-Q1'))
        markdown = render_awards(awards)
        assert markdown.startswith('# :trophy: OOTD Awards T1 2025')
        assert 'Au premier trimestre 2025, **7 tenues**' in markdown
        assert 'Tenue du trimestre' in markdown
        assert 'Membre du trimestre' in markdown
        assert 'tenues postées ce trimestre' in markdown
        assert 'Tenue du mois' in markdown
        assert "l'année" not in markdown
        assert member_honours(awards, 'alice')[0] == 'Tenue du trimestre'

    def test_month_period_has_no_monthly_section(self):
        march = Period.parse('2025-03')
        awards = compute_awards([p for p in sample_posts() if p.month == 3], march)
        markdown = render_awards(awards)
        assert 'Tenue du mois' in markdown  # the winner heading
        assert ':calendar:' not in markdown
        assert 'Le mois le plus actif' not in markdown
        assert 'Ton meilleur mois' not in render_wrapped(awards, awards.members[0])


class TestQuarterBadges:

    def test_quarter_badges_are_reusable_and_undated(self):
        specs = publish.badge_specs(Period.parse('2026-Q1'))
        assert publish.TOP10 not in specs
        assert all(spec.multiple_grant for spec in specs.values())
        assert all('2026' not in spec.name for spec in specs.values())

    def test_month_period_only_grants_outfit_of_the_month(self):
        awards = compute_awards([p for p in sample_posts() if p.month == 3], Period.parse('2025-03'))
        grants = publish.planned_grants(awards)
        assert [(g.badge.name, g.username) for g in grants] == [('OOTD of the Month', 'bob')]

    def test_monthly_badge_not_granted_twice_across_periods(self, tmp_path):
        ledger = tmp_path / 'badges_granted.txt'
        quarter = compute_awards(quarter_posts(), Period.parse('2025-Q1'))
        year = compute_awards(sample_posts(), Period.parse('2025'))
        publish.apply_badges(fake_client(), quarter, ledger, publish=True, log=lambda _: None)

        client = fake_client()
        publish.apply_badges(client, year, ledger, publish=True, log=lambda _: None)
        monthly_badge_id = 7
        # January to March winners (posts 1, 3, 6) already got their monthly badge in Q1
        regranted = [c.args for c in client.grant_badge.call_args_list
                     if c.args[1] == monthly_badge_id and c.args[2].rsplit('/', 1)[-1] in ('1', '3', '6')]
        assert regranted == []
        # later months are still granted by the yearly review
        assert any(c.args[1] == monthly_badge_id and c.args[2].endswith('/8')
                   for c in client.grant_badge.call_args_list)

    def test_wrapped_minimum_scales(self):
        awards = compute_awards(quarter_posts(), Period.parse('2025-Q1'))
        assert [m.username for m in publish.wrapped_recipients(awards)] == ['alice', 'bob']
        assert publish.wrapped_title(Period.parse('2025-Q1')) == 'Ton bilan OOTD T1 2025 sur Borasification'


def fake_client():
    from unittest.mock import Mock
    client = Mock()
    client.forum_url = 'https://forum.example.com'
    client.list_badges.return_value = [{'name': 'OOTD of the Month', 'id': 7}]
    client.create_badge.side_effect = lambda name, *a, **k: {'id': 100 + len(name), 'name': name}
    client.user_badges.return_value = []
    return client
