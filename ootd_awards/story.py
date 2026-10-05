"""
"Vestiaire" story page: an animated, interactive look back at a period.

story_payload() turns the awards into the JSON the page needs, and
render_story_html() inlines it with the page's CSS and JS into one
standalone HTML file for a local preview. The page's CSS and JS live in
the Discourse theme component (discourse-theme/), so they hold no data and no
member names; story_post_markdown() builds the forum post that feeds it.
"""

import base64
import json
import textwrap
import zlib
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from .awards import Awards, MemberStats
from .dataset import Post
from .period import month_name
from .render import member_honours, select_cover_upload

ASSETS_DIR = Path(__file__).resolve().parent / 'story'
# The page's code lives in the Discourse theme component, the single source
# for the forum and for the local preview. story.scss is plain CSS.
THEME_DIR = Path(__file__).resolve().parent.parent / 'discourse-theme'
STORY_CSS = THEME_DIR / 'stylesheets' / 'story.scss'
STORY_JS = THEME_DIR / 'javascripts' / 'discourse' / 'lib' / 'ootd-story.js'
# How the data travels in a forum post: zlib-compressed JSON, base64-encoded.
# A year is ~265 kB of JSON but ~58 kB once packed (Discourse's default post
# limit is 32 000 characters, so max_post_length must be raised).
PACK_FORMAT = 'zlib-base64-v1'
PACK_LINE = 76
DISCOURSE_DEFAULT_MAX_POST_LENGTH = 32000

MOSAIC_SIZE = 30  # full-size photos: keep the hero light
MEMBER_TOP_N = 3


def fr(n) -> str:
    """French number formatting, matching the page's Intl.NumberFormat('fr-FR')."""
    return f'{n:,}'.replace(',', '\u202f')


def image_url(upload: Dict, forum_url: str) -> str:
    """Absolute URL of an upload (Discourse stores //cdn/... or /uploads/...)."""
    url = upload['url']
    if url.startswith('//'):
        return f'https:{url}'
    if url.startswith('/'):
        return f'{forum_url}{url}'
    return url


def outfit(post: Post, forum_url: str, rank: Optional[int] = None) -> Optional[Dict]:
    """One outfit as the page needs it, or None when the post has no usable image."""
    upload = select_cover_upload(post.uploads)
    if not upload:
        return None
    item = {
        'u': post.username,
        'likes': post.like_count,
        'likes30': post.likes_30d,
        'month': post.month,
        'img': image_url(upload, forum_url),
        'w': upload.get('width') or 3,
        'h': upload.get('height') or 4,
        'url': f'{forum_url}{post.path}',
    }
    if rank is not None:
        item['rank'] = rank
    return item


def _outfits(posts: List[Post], forum_url: str, n: int) -> List[Dict]:
    items = [outfit(post, forum_url) for post in posts[:n * 2]]
    return [item for item in items if item][:n]


def avatar_url(member: MemberStats, forum_url: str) -> Optional[str]:
    avatar = member.outfits[0].avatar if member.outfits else None
    return image_url({'url': avatar}, forum_url) if avatar else None


def _member(member: MemberStats, forum_url: str, newcomer: bool) -> Dict:
    return {
        'u': member.username,
        'avatar': avatar_url(member, forum_url),
        'count': member.count,
        'likes': member.total_likes,
        'median': member.median_likes,
        'new': newcomer,
        'top': _outfits(member.outfits, forum_url, MEMBER_TOP_N),
    }


def _latest_topic_url(posts: List[Post], forum_url: str) -> str:
    """The OOTD thread of the period's latest outfit: where the footer sends people."""
    if not posts:
        return forum_url
    latest = max(posts, key=lambda p: p.created_at)
    return f'{forum_url}/t/{latest.slug}/{latest.topic_id}'


def story_payload(awards: Awards, fans: Dict[str, Dict], forum_url: str) -> Dict:
    """Everything the story page shows, computed from the period's awards."""
    period = awards.period
    rising = {m.username for m in awards.rising}
    newcomers = {m.username for m in awards.members
                 if period.contains(m.outfits[0].first_ootd_at)}

    per_month = Counter(p.month for p in awards.outfits)
    monthly = [{
        'month': month,
        'name': month_name(month),
        'count': per_month.get(month, 0),
        'winner': outfit(awards.monthly[month], forum_url) if month in awards.monthly else None,
    } for _, month in period.months]

    # A mosaic of photo-sized covers, spread over the whole period
    covers = [outfit(p, forum_url) for p in awards.outfits]
    covers = [c for c in covers if c and c['h'] >= c['w']]
    step = max(1, len(covers) // MOSAIC_SIZE)
    mosaic = [c['img'] for c in covers[::step]][:MOSAIC_SIZE]

    def award(members: List[MemberStats], detail) -> Optional[Dict]:
        if not members:
            return None
        winner = members[0]
        return {
            **_member(winner, forum_url, winner.username in newcomers),
            'detail': detail(winner),
            'podium': [{'u': m.username, 'detail': detail(m)} for m in members[1:3]],
        }

    consistent_members = [awards.member(u) for u, _ in awards.consistent]
    consistent_counts = dict(awards.consistent)

    wrapped = {}
    for member in awards.members:
        if member.count < period.min_outfits:
            continue
        fan = fans.get(member.username)
        wrapped[member.username] = {
            'avatar': avatar_url(member, forum_url),
            'count': member.count,
            'likes': member.total_likes,
            'rank': awards.member_rank(member.username),
            'best_month': month_name(member.best_month) if period.kind != 'month' else None,
            'fan': fan,
            'honours': member_honours(awards, member.username),
            'top': _outfits(member.outfits, forum_url, MEMBER_TOP_N),
        }

    return {
        'period': {
            'key': period.key,
            'label': period.label,
            'kind': period.kind,
            'intro': period.intro,
            'of': period.of,
            'this': period.this,
            'top_n': period.top_n,
            'best_n': period.member_best_n,
        },
        'forum_url': forum_url,
        'ootd_url': _latest_topic_url(awards.outfits, forum_url),
        'stats': {
            'outfits': len(awards.outfits),
            'members': len(awards.members),
            'likes': awards.total_likes,
            'busiest_month': month_name(awards.busiest_month) if awards.busiest_month else None,
        },
        'top': [item for item in (outfit(p, forum_url, rank) for rank, p in enumerate(awards.top, 1)) if item],
        'monthly': monthly,
        'mosaic': mosaic,
        'members': [_member(m, forum_url, m.username in rising) for m in awards.members],
        'awards': {
            'member': award(awards.members, lambda m: f'{fr(m.count)} tenues, {fr(m.total_likes)} likes'),
            'rising': award(awards.rising,
                            lambda m: f'{fr(m.count)} tenues, {m.median_likes:g} likes en médiane'),
            'pillar': award(awards.pillars, lambda m: f'{fr(m.count)} tenues postées'),
            'consistent': award(consistent_members,
                                lambda m: f'{fr(consistent_counts[m.username])} tenues au-dessus de '
                                          f'{awards.consistency_threshold:g} likes'),
        },
        'wrapped': wrapped,
    }


def render_story_html(payload: Dict) -> str:
    """Standalone preview page: the template with CSS, JS and data inlined."""
    template = (ASSETS_DIR / 'preview.html').read_text(encoding='utf-8')
    data = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    # data last: nothing inserted after it can be mistaken for a placeholder
    return (template
            .replace('{{TITLE}}', f"Vestiaire {payload['period']['label']}")
            .replace('/*{{CSS}}*/', STORY_CSS.read_text(encoding='utf-8'))
            .replace('/*{{JS}}*/', STORY_JS.read_text(encoding='utf-8'))
            .replace('{{DATA}}', data))


def pack_payload(payload: Dict) -> str:
    """Compress the payload for a forum post: zlib then base64, in 76-character lines."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    packed = base64.b64encode(zlib.compress(raw, 9)).decode('ascii')
    return '\n'.join(textwrap.wrap(packed, PACK_LINE))


def unpack_payload(packed: str) -> Dict:
    """Inverse of pack_payload (what the theme component does in the browser)."""
    return json.loads(zlib.decompress(base64.b64decode(''.join(packed.split()))).decode('utf-8'))


def story_post_markdown(payload: Dict) -> str:
    """
    The forum post that carries the story page.

    The "vestiaire" theme component replaces the [wrap=vestiaire] block with
    a card that opens the page full screen, and reads the data from the
    [wrap=vestiaire-data] block. Without the component, readers see the intro
    and a folded "details" block. The data sits in a code block, so usernames
    in it are never turned into @mentions.
    """
    period = payload['period']
    stats = payload['stats']
    return '\n'.join([
        f"{period['intro']}, **{fr(stats['outfits'])} tenues** ont été postées par "
        f"**{fr(stats['members'])} membres** dans l'OOTD. Ouvre le vestiaire pour revivre "
        f"{period['this']} tenue après tenue, et découvrir ton propre bilan.",
        '',
        f"[wrap=vestiaire period={period['key']}]",
        "*Le vestiaire s'ouvre ici avec le composant « Vestiaire OOTD ».*",
        '[/wrap]',
        '',
        f'[wrap=vestiaire-data format={PACK_FORMAT}]',
        '[details="Données du vestiaire, générées automatiquement"]',
        '```text',
        pack_payload(payload),
        '```',
        '[/details]',
        '[/wrap]',
        '',
    ])
