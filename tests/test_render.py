"""
Tests for year review markdown rendering.
"""

from ootd_awards.awards import compute_awards
from ootd_awards.render import (
    base62_sha1, image, member_honours, render_awards, render_wrapped, select_cover_upload,
)
from tests.fixtures import BASE62, SHA1, YEAR_2025, make_post, sample_posts


class TestImages:

    def test_base62_uses_discourse_alphabet(self):
        # Discourse short URLs use 0-9, then a-z, then A-Z (checked against a real
        # cooked post's data-base62-sha1 when this was written)
        assert base62_sha1(format(9, '040x')) == '9'
        assert base62_sha1(format(10, '040x')) == 'a'
        assert base62_sha1(format(36, '040x')) == 'A'
        assert base62_sha1(format(62, '040x')) == '10'
        assert base62_sha1(SHA1) == BASE62

    def test_image_uses_short_upload_url(self):
        post = make_post(1, 'alice', 1, 10)
        assert image(post) == f'![alice|1536x2040](upload://{BASE62}.jpeg)'

    def test_image_without_uploads(self):
        assert image(make_post(1, 'alice', 1, 10, uploads=[])) == ''

    def test_cover_prefers_first_portrait(self):
        landscape = {'sha1': 'a', 'url': 'x.jpg', 'width': 1000, 'height': 700}
        square = {'sha1': 'b', 'url': 'y.jpg', 'width': 1000, 'height': 1100}
        portrait = {'sha1': 'c', 'url': 'z.jpg', 'width': 1000, 'height': 1500}
        assert select_cover_upload([landscape, square, portrait]) is portrait
        # no portrait photo: the largest one, not the first
        assert select_cover_upload([landscape, square]) is square
        assert select_cover_upload([]) is None

    def test_cover_ignores_small_images(self):
        # a post mixing screenshots with one real photo (seen on the forum)
        uploads = [
            {'sha1': 'a', 'url': 'a.jpg', 'width': 1200, 'height': 630},
            {'sha1': 'b', 'url': 'b.jpg', 'width': 348, 'height': 582},   # small portrait crop
            {'sha1': 'c', 'url': 'c.jpg', 'width': 1999, 'height': 1999},
        ]
        assert select_cover_upload(uploads)['sha1'] == 'c'
        # 16x16 icon before the photo
        icon = {'sha1': 'i', 'url': 'i.png', 'width': 16, 'height': 16}
        photo = {'sha1': 'p', 'url': 'p.jpg', 'width': 1500, 'height': 1500}
        assert select_cover_upload([icon, photo]) is photo

    def test_cover_falls_back_when_no_real_photo(self):
        small = [{'sha1': 'a', 'url': 'a.jpg', 'width': 400, 'height': 300},
                 {'sha1': 'b', 'url': 'b.jpg', 'width': 400, 'height': 560}]
        assert select_cover_upload(small)['sha1'] == 'b'


class TestAwardsTopic:

    def test_contains_every_section(self):
        markdown = render_awards(compute_awards(sample_posts(), YEAR_2025))
        for heading in ("Tenue de l'année", 'Le top 50', 'Tenue du mois', "Membre de l'année",
                        "Révélation de l'année", 'Le plus régulier', "Pilier de l'OOTD"):
            assert heading in markdown
        assert '@alice — ❤ 70 — [voir le post](/t/outfit-of-the-day-part-12bis/13530/1)' in markdown
        assert '- **Décembre** — @bob' in markdown
        assert markdown.count('[grid]') == markdown.count('[/grid]')

    def test_year_top_50_is_split_in_blocks_of_10(self):
        posts = [make_post(i, f'member{i % 12}', 1 + i % 12, 100 - i) for i in range(1, 80)]
        markdown = render_awards(compute_awards(posts, YEAR_2025))
        assert 'Au plus 5 tenues par membre dans le top 50.' in markdown
        for block in ('### 2–10', '### 11–20', '### 21–30', '### 31–40', '### 41–50'):
            assert block in markdown
        assert '\n50. @' in markdown and '\n51. @' not in markdown
        assert markdown.count('[grid]') >= 5

    def test_empty_year_renders(self):
        markdown = render_awards(compute_awards([], YEAR_2025))
        assert 'OOTD Awards 2025' in markdown
        assert "Tenue de l'année" not in markdown


class TestWrapped:

    def test_member_wrapped(self):
        awards = compute_awards(sample_posts(), YEAR_2025)
        markdown = render_wrapped(awards, awards.member('carol'), {'fan': 'bob', 'likes': 12})
        assert '**5** tenues postées' in markdown
        assert '**#3** au classement des membres (sur 4)' in markdown
        assert 'Ton meilleur mois : **juillet**' in markdown
        assert '**bob** (12 likes)' in markdown
        assert "Révélation de l'année" in markdown
        assert '## Mon best-of 2025' in markdown
        # PMs must not mention the member (no notification noise)
        assert '@carol' not in markdown

    def test_honours(self):
        awards = compute_awards(sample_posts(), YEAR_2025)
        assert member_honours(awards, 'alice') == [
            "Tenue de l'année", 'Tenue du mois (janvier, février)', 'Le plus régulier', "Pilier de l'OOTD (3e)",
        ]
        assert "Pilier de l'OOTD" in member_honours(awards, 'bob')
        assert member_honours(awards, 'nobody') == []
