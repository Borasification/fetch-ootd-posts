"""
Tests for year review publishing (badges, drafts, Wrapped).
"""

from unittest.mock import Mock

from ootd_awards import publish
from ootd_awards.awards import compute_awards
from tests.fixtures import YEAR_2025, sample_posts


def fake_client():
    client = Mock()
    client.forum_url = 'https://forum.example.com'
    client.list_badges.return_value = [{'name': 'OOTD of the Month', 'id': 7}]
    client.create_badge.side_effect = lambda name, *a, **k: {'id': 100 + len(name), 'name': name}
    client.user_badges.return_value = []
    return client


class TestBadges:

    def test_planned_grants(self):
        grants = publish.planned_grants(compute_awards(sample_posts(), YEAR_2025))
        summary = [(g.badge.name, g.username) for g in grants]
        assert ('OOTD of the Year 2025', 'alice') in summary
        assert ('Member of the Year 2025', 'bob') in summary
        assert ('Rising Star 2025', 'carol') in summary
        # Top 10 badge granted once per member, even with two outfits in the top
        assert [u for b, u in summary if b == 'OOTD Top 10 2025'].count('alice') == 1
        # Monthly badge can be granted several times
        assert [u for b, u in summary if b == 'OOTD of the Month'].count('alice') == 2

    def test_dry_run_does_not_touch_forum(self, tmp_path):
        client = fake_client()
        pending = publish.apply_badges(client, compute_awards(sample_posts(), YEAR_2025),
                                       tmp_path / 'ledger.txt', publish=False, log=lambda _: None)
        assert pending
        assert client.method_calls == []
        assert not (tmp_path / 'ledger.txt').exists()

    def test_publish_creates_missing_badges_and_is_idempotent(self, tmp_path):
        client = fake_client()
        awards = compute_awards(sample_posts(), YEAR_2025)
        ledger = tmp_path / 'ledger.txt'

        publish.apply_badges(client, awards, ledger, publish=True, log=lambda _: None)
        created = {c.args[0] for c in client.create_badge.call_args_list}
        assert 'OOTD of the Month' not in created
        assert 'OOTD of the Year 2025' in created
        assert client.grant_badge.call_count == len(publish.planned_grants(awards))
        username, _, reason = client.grant_badge.call_args_list[0].args
        assert reason.startswith('https://forum.example.com/t/')

        client.grant_badge.reset_mock()
        publish.apply_badges(client, awards, ledger, publish=True, log=lambda _: None)
        client.grant_badge.assert_not_called()

    def test_skips_single_grant_badge_already_owned(self, tmp_path):
        client = fake_client()
        year_badge_id = 100 + len('OOTD of the Year 2025')
        client.user_badges.return_value = [{'badge_id': year_badge_id}]
        publish.apply_badges(client, compute_awards(sample_posts(), YEAR_2025),
                             tmp_path / 'ledger.txt', publish=True, log=lambda _: None)
        granted_ids = {c.args[1] for c in client.grant_badge.call_args_list}
        assert year_badge_id not in granted_ids


class TestWrapped:

    def test_preview_goes_to_admin_only(self, tmp_path):
        client = fake_client()
        sent = publish.send_wrapped(client, compute_awards(sample_posts(), YEAR_2025), {}, tmp_path / 'sent.txt',
                                    send=False, admin_username='admin', log=lambda _: None)
        assert sent == ['bob']
        client.create_post.assert_called_once()
        assert client.create_post.call_args.kwargs['target_recipients'] == 'admin'
        assert not (tmp_path / 'sent.txt').exists()

    def test_send_skips_small_contributors_and_already_sent(self, tmp_path):
        client = fake_client()
        ledger = tmp_path / 'sent.txt'
        ledger.write_text('bob\n')
        sent = publish.send_wrapped(client, compute_awards(sample_posts(), YEAR_2025), {}, ledger,
                                    send=True, admin_username='admin', log=lambda _: None)
        # alice has 3 outfits and dave 1: below the 5-outfit minimum
        assert sent == ['carol']
        assert client.create_post.call_args.kwargs['target_recipients'] == 'carol'
        assert ledger.read_text().split() == ['bob', 'carol']

    def test_reply_goes_into_existing_topic(self):
        client = fake_client()
        publish.publish_awards_reply(client, 'body', 1015)
        client.create_post.assert_called_once_with('body', topic_id=1015)

    def test_to_one_member_sends_only_to_them(self, tmp_path):
        client = fake_client()
        ledger = tmp_path / 'sent.txt'
        sent = publish.send_wrapped(client, compute_awards(sample_posts(), YEAR_2025), {}, ledger,
                                    send=True, admin_username='admin', only_username='CAROL',
                                    log=lambda _: None)
        assert sent == ['carol']
        client.create_post.assert_called_once()
        assert client.create_post.call_args.kwargs['target_recipients'] == 'carol'
        assert ledger.read_text().split() == ['carol']

    def test_to_member_below_threshold_is_allowed(self, tmp_path):
        client = fake_client()
        sent = publish.send_wrapped(client, compute_awards(sample_posts(), YEAR_2025), {}, tmp_path / 'sent.txt',
                                    send=True, admin_username='admin', only_username='dave',
                                    log=lambda _: None)
        assert sent == ['dave']

    def test_to_member_already_sent_needs_resend(self, tmp_path):
        client = fake_client()
        ledger = tmp_path / 'sent.txt'
        ledger.write_text('carol\n')
        awards = compute_awards(sample_posts(), YEAR_2025)

        assert publish.send_wrapped(client, awards, {}, ledger, send=True, admin_username='admin',
                                    only_username='carol', log=lambda _: None) == []
        client.create_post.assert_not_called()

        assert publish.send_wrapped(client, awards, {}, ledger, send=True, admin_username='admin',
                                    only_username='carol', resend=True, log=lambda _: None) == ['carol']
        assert ledger.read_text().split() == ['carol']

    def test_to_without_send_previews_that_member_to_admin(self, tmp_path):
        client = fake_client()
        sent = publish.send_wrapped(client, compute_awards(sample_posts(), YEAR_2025), {}, tmp_path / 'sent.txt',
                                    send=False, admin_username='admin', only_username='carol',
                                    log=lambda _: None)
        assert sent == ['carol']
        kwargs = client.create_post.call_args.kwargs
        assert kwargs['target_recipients'] == 'admin'
        assert kwargs['title'].startswith('[Aperçu carol]')

    def test_preview_logs_the_link(self, tmp_path):
        client = fake_client()
        client.create_post.return_value = {'topic_slug': 'apercu-carol', 'topic_id': 42, 'post_number': 1}
        lines = []
        publish.send_wrapped(client, compute_awards(sample_posts(), YEAR_2025), {}, tmp_path / 'sent.txt',
                             send=False, admin_username='admin', only_username='carol', log=lines.append)
        assert 'https://forum.example.com/t/apercu-carol/42/1' in lines[0]

    def test_to_unknown_member_fails(self, tmp_path):
        import pytest
        with pytest.raises(ValueError, match='no outfits'):
            publish.send_wrapped(fake_client(), compute_awards(sample_posts(), YEAR_2025), {},
                                 tmp_path / 'sent.txt', send=True, admin_username='admin',
                                 only_username='nobody', log=lambda _: None)

    def test_draft_is_a_pm_to_admin(self):
        client = fake_client()
        publish.send_awards_draft(client, 'body', YEAR_2025, 'admin')
        kwargs = client.create_post.call_args.kwargs
        assert kwargs['target_recipients'] == 'admin'
        assert kwargs['title'].startswith('[Brouillon] OOTD Awards 2025')
