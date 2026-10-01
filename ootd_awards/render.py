"""
Markdown rendering for the awards topic and the personal "Wrapped" messages,
for any review period (year, quarter or month).

Images use Discourse short upload URLs (upload://<base62 sha1>.<ext>), so
they render natively in [grid] blocks and lightboxes.
"""

import string
from typing import Dict, List, Optional

from .awards import MAX_PER_MEMBER_IN_TOP, Awards, MemberStats
from .dataset import Post
from .period import month_name

BASE62_ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase

WRAPPED_TOP_N = 3
LOOKBOOK_TOP_N = 5


def base62_sha1(sha1: str) -> str:
    """Encode a hex sha1 the way Discourse builds upload:// short URLs."""
    number = int(sha1, 16)
    encoded = ''
    while number:
        number, remainder = divmod(number, 62)
        encoded = BASE62_ALPHABET[remainder] + encoded
    return encoded or '0'


COVER_MIN_SIDE = 600  # px on the short side: below that, a thumbnail, screenshot or crop
COVER_MIN_RATIO = 1.2  # height / width of a full-body, portrait shot


def select_cover_upload(uploads: List[Dict], min_side: int = COVER_MIN_SIDE,
                        min_ratio: float = COVER_MIN_RATIO) -> Optional[Dict]:
    """
    Pick the image that best shows the full outfit.

    Only real photos count (at least min_side px on the short side), unless
    the post has none. Among them, take the first portrait one (full-body
    shots are portrait and usually come first), otherwise the largest.
    """
    def size(upload):
        return upload.get('width') or 0, upload.get('height') or 0

    photos = [u for u in uploads if min(size(u)) >= min_side] or uploads
    for upload in photos:
        width, height = size(upload)
        if width and height / width >= min_ratio:
            return upload
    return max(photos, key=lambda u: size(u)[0] * size(u)[1], default=None)


def image(post: Post) -> str:
    """Markdown for the post's cover image, or an empty string when it has none."""
    upload = select_cover_upload(post.uploads)
    if not upload:
        return ''
    extension = upload['url'].rsplit('.', 1)[-1].lower()
    size = f"|{upload['width']}x{upload['height']}" if upload.get('width') and upload.get('height') else ''
    return f"![{post.username}{size}](upload://{base62_sha1(upload['sha1'])}.{extension})"


def grid(posts: List[Post]) -> str:
    images = [image(p) for p in posts]
    return '[grid]\n' + '\n'.join(i for i in images if i) + '\n[/grid]'


def caption(post: Post, mention: bool = True) -> str:
    author = f'@{post.username}' if mention else f'**{post.username}**'
    return f'{author} — ❤ {post.like_count} — [voir le post]({post.path})'


def render_awards(awards: Awards) -> str:
    """Markdown body of the public 'OOTD Awards {period}' topic."""
    period = awards.period
    lines = [
        f'# :trophy: OOTD Awards {period.label}',
        '',
        f'{period.intro}, **{len(awards.outfits)} tenues** ont été postées par **{len(awards.members)} membres** '
        f'et ont reçu **{awards.total_likes} likes**.',
    ]
    if awards.busiest_month and period.kind != 'month':
        lines.append(f'Le mois le plus actif : **{month_name(awards.busiest_month)}**.')
    lines += [
        '',
        '> Classement sur les likes reçus pendant les 30 premiers jours de chaque tenue, '
        'pour que les tenues de fin de période aient les mêmes chances que les autres. '
        f'Au plus {MAX_PER_MEMBER_IN_TOP} tenues par membre dans le top 10.',
        '',
    ]

    winner = awards.winner
    if winner:
        lines += [f'## :1st_place_medal: Tenue {period.of}', '', caption(winner), '', image(winner), '']

    runners_up = awards.top[1:]
    if runners_up:
        lines += ['## :star: Le top 10', '', grid(runners_up), '']
        lines += [f'{rank}. {caption(post)}' for rank, post in enumerate(runners_up, 2)]
        lines.append('')

    if awards.monthly and period.kind != 'month':
        monthly = list(awards.monthly.items())
        lines += ['## :calendar: Tenue du mois', '', grid([post for _, post in monthly]), '']
        lines += [f'- **{month_name(month).capitalize()}** — {caption(post)}' for month, post in monthly]
        lines.append('')

    if awards.members:
        member = awards.members[0]
        lines += [
            f'## :crown: Membre {period.of}',
            '',
            f'@{member.username} — {member.count} tenues, {member.total_likes} likes. '
            f'Le classement additionne les likes des {period.member_best_n} meilleures tenues de chacun : '
            f'la qualité compte plus que le volume.',
            '',
            grid(member.outfits[:WRAPPED_TOP_N]),
            '',
        ]
        podium = awards.members[1:3]
        lines += [f'{rank}. @{m.username} — {m.count} tenues, {m.total_likes} likes'
                  for rank, m in enumerate(podium, 2)]
        lines.append('')

    if awards.rising:
        star = awards.rising[0]
        first = star.outfits[0].first_ootd_at
        lines += [
            f'## :seedling: Révélation {period.of}',
            '',
            f'@{star.username} — première tenue le {first.day} {month_name(first.month)} {first.year}, '
            f'{star.count} tenues, {star.median_likes:g} likes en médiane.',
            '',
            grid(star.outfits[:WRAPPED_TOP_N]),
            '',
        ]

    if awards.consistent:
        username, count = awards.consistent[0]
        lines += [
            '## :chart_with_upwards_trend: Le plus régulier',
            '',
            f'@{username} — {count} tenues au-dessus de {awards.consistency_threshold:g} likes '
            f'(le top 25 % {period.of}).',
            '',
        ]
        lines += [f'{rank}. @{name} — {n} tenues' for rank, (name, n) in enumerate(awards.consistent[1:3], 2)]
        lines.append('')

    if awards.pillars:
        pillar = awards.pillars[0]
        lines += [
            '## :classical_building: Pilier de l\'OOTD',
            '',
            f'@{pillar.username} — {pillar.count} tenues postées {period.this}, {pillar.total_likes} likes. '
            f'Merci pour ta présence, jour après jour !',
            '',
        ]
        lines += [f'{rank}. @{m.username} — {m.count} tenues, {m.total_likes} likes'
                  for rank, m in enumerate(awards.pillars[1:3], 2)]
        lines.append('')

    lines += ['---', '', 'Merci à tous pour ces superbes tenues ! :clap:', '']
    return '\n'.join(lines)


def member_honours(awards: Awards, username: str) -> List[str]:
    """Awards won by a member, as short French labels."""
    of = awards.period.of
    honours = []
    if awards.winner and awards.winner.username == username:
        honours.append(f'Tenue {of}')
    elif any(p.username == username for p in awards.top):
        honours.append(f'Top 10 {of}')
    months = [month_name(m) for m, p in awards.monthly.items() if p.username == username]
    if months and awards.period.kind != 'month':
        honours.append(f'Tenue du mois ({", ".join(months)})')
    if awards.members and awards.members[0].username == username:
        honours.append(f'Membre {of}')
    if awards.rising and awards.rising[0].username == username:
        honours.append(f'Révélation {of}')
    if awards.consistent and awards.consistent[0][0] == username:
        honours.append('Le plus régulier')
    podium = [m.username for m in awards.pillars[:3]]
    if username in podium:
        rank = podium.index(username) + 1
        honours.append('Pilier de l\'OOTD' + ('' if rank == 1 else f' ({rank}e)'))
    return honours


def render_wrapped(awards: Awards, member: MemberStats, fan: Optional[Dict] = None) -> str:
    """Markdown body of a member's personal 'Wrapped' PM."""
    period = awards.period
    best = member.outfits[0]
    lines = [
        f'Salut {member.username} ! Voici ton bilan OOTD {period.label} sur Borasification :necktie:',
        '',
        f'- **{member.count}** tenues postées',
        f'- **{member.total_likes}** likes reçus',
        f'- **#{awards.member_rank(member.username)}** au classement des membres (sur {len(awards.members)})',
    ]
    if period.kind != 'month':
        lines.append(f'- Ton meilleur mois : **{month_name(member.best_month)}**')
    if fan:
        lines.append(f'- Ton plus grand fan : **{fan["fan"]}** ({fan["likes"]} likes)')

    honours = member_honours(awards, member.username)
    if honours:
        lines.append(f'- :trophy: {" · ".join(honours)}')

    lines += ['', f'## Ta tenue {period.of}', '', caption(best, mention=False), '', image(best), '']

    if member.count > 1:
        lines += ['## Ton top 3', '', grid(member.outfits[:WRAPPED_TOP_N]), '']

    lines += [
        '## Pour ton lookbook',
        '',
        'Copie-colle ce bloc dans ton lookbook :',
        '',
        '````markdown',
        f'## Mon best-of {period.label}',
        '',
        grid(member.outfits[:LOOKBOOK_TOP_N]),
        '````',
        '',
        'À bientôt sur l\'OOTD !',
        '',
    ]
    return '\n'.join(lines)
