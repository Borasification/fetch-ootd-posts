"""
Tests for the story page generator.
"""

import json

from ootd_awards.awards import compute_awards
from ootd_awards.period import Period
from ootd_awards.story import fr, image_url, render_story_html, story_payload
from tests.fixtures import YEAR_2025, make_post, sample_posts

FORUM = 'https://forum.example.com'


def payload(posts=None, period=YEAR_2025, fans=None):
    return story_payload(compute_awards(posts or sample_posts(), period), fans or {}, FORUM)


class TestPayload:

    def test_sections_data(self):
        data = payload()
        assert data['period']['label'] == '2025'
        assert data['stats']['outfits'] == 14
        assert [item['rank'] for item in data['top']] == list(range(1, len(data['top']) + 1))
        assert data['top'][0]['u'] == 'alice'
        assert data['top'][0]['url'] == f'{FORUM}/t/outfit-of-the-day-part-12bis/13530/1'
        assert len(data['monthly']) == 12
        assert {m['month']: m['count'] for m in data['monthly']}[3] == 3
        assert data['awards']['pillar']['u'] == 'bob'
        assert data['ootd_url'] == f'{FORUM}/t/outfit-of-the-day-part-12bis/13530'

    def test_wrapped_only_for_members_with_enough_outfits(self):
        data = payload(fans={'carol': {'fan': 'bob', 'likes': 4}})
        assert set(data['wrapped']) == {'bob', 'carol'}  # alice has 3 outfits, dave 1: below 5
        assert data['wrapped']['carol']['fan'] == {'fan': 'bob', 'likes': 4}

    def test_quarter_has_three_months(self):
        data = payload([p for p in sample_posts() if p.month <= 3], Period.parse('2025-Q1'))
        assert [m['name'] for m in data['monthly']] == ['janvier', 'février', 'mars']

    def test_image_urls_are_absolute(self):
        assert image_url({'url': '//cdn.example.com/a.jpg'}, FORUM) == 'https://cdn.example.com/a.jpg'
        assert image_url({'url': '/uploads/a.jpg'}, FORUM) == f'{FORUM}/uploads/a.jpg'
        assert image_url({'url': 'https://cdn.example.com/a.jpg'}, FORUM) == 'https://cdn.example.com/a.jpg'

    def test_french_numbers(self):
        assert fr(4714) == '4 714'
        assert fr(12) == '12'


class TestHtml:

    def test_standalone_page(self):
        html = render_story_html(payload())
        assert '{{' not in html and '/*{{' not in html
        assert '<title>Vestiaire 2025</title>' in html
        assert 'OotdStory.render' in html and '.ootd-story' in html

    def test_data_cannot_close_the_script_tag(self):
        posts = [make_post(1, 'evil</script><script>alert(1)</script>', 1, 10)]
        html = render_story_html(payload(posts))
        start = html.index('<script type="application/json" id="vestiaire-data">')
        end = html.index('</script>', start)
        block = html[start:end]
        assert 'alert(1)' in block  # still inside the JSON block, as text
        assert json.loads(block.split('>', 1)[1])['top'][0]['u'].startswith('evil</script>')


class TestAvatars:

    def test_profile_picture_made_absolute_and_optional(self):
        posts = sample_posts()
        for post in posts:
            if post.username == 'bob':
                post.avatar = '//cdn.example.com/optimized/avatar_120x120.png'
        data = payload(posts)
        members = {m['u']: m for m in data['members']}
        assert members['bob']['avatar'] == 'https://cdn.example.com/optimized/avatar_120x120.png'
        assert members['alice']['avatar'] is None  # default letter avatar: the page shows a monogram
        assert data['wrapped']['bob']['avatar'].startswith('https://')

    def test_avatar_read_from_query_row(self):
        from ootd_awards.dataset import parse_row
        row = {'id': 1, 'topic_id': 1, 'slug': 's', 'topic_title': 't', 'post_number': 1, 'username': 'a',
               'created_at': '2025-01-01T00:00:00Z', 'like_count': 1, 'likes_30d': 1, 'first_ootd_at': None,
               'uploads': [], 'avatar_url': '//cdn.example.com/a.png'}
        assert parse_row(row).avatar == '//cdn.example.com/a.png'
        del row['avatar_url']  # caches fetched before avatars existed still load
        assert parse_row(row).avatar is None


class TestForumPost:

    def test_pack_round_trip(self):
        from ootd_awards.story import pack_payload, unpack_payload
        data = payload()
        packed = pack_payload(data)
        assert max(len(line) for line in packed.splitlines()) <= 76
        assert unpack_payload(packed) == json.loads(json.dumps(data))

    def test_post_markdown_blocks(self):
        from ootd_awards.story import story_post_markdown
        markdown = story_post_markdown(payload())
        assert '[wrap=vestiaire period=2025]' in markdown
        assert '[wrap=vestiaire-data format=zlib-base64-v1]' in markdown
        assert markdown.count('```') == 2
        # usernames only travel inside the compressed code block: no @mentions, no notifications
        assert '@' not in markdown

    def test_theme_files_present(self):
        from pathlib import Path
        theme = Path(__file__).parent.parent / 'discourse-theme'
        about = json.loads((theme / 'about.json').read_text())
        assert about['component'] is True
        for asset in about['assets'].values():
            assert (theme / asset).exists(), asset
        for path in ('common/common.scss', 'stylesheets/story.scss', 'stylesheets/vestiaire.scss',
                     'javascripts/discourse/lib/ootd-story.js', 'javascripts/discourse/lib/vestiaire-mount.js',
                     'javascripts/discourse/api-initializers/vestiaire.js'):
            assert (theme / path).exists(), path
