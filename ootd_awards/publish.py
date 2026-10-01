"""
Publishing: draft PMs, the public awards topic, badges and Wrapped messages.

Every function that writes to the forum takes an explicit flag; without it,
it only reports what it would do. Badge grants and Wrapped sends are logged
to local ledger files so a re-run never grants or sends twice. The badge
ledger is shared by all periods, so an "OOTD of the Month" won in a quarterly
review is not granted again by the yearly review.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from .awards import Awards, MemberStats
from .dataset import Post
from .period import Period
from .render import render_wrapped

GOLD, SILVER, BRONZE = 1, 2, 3

# Badge roles: which award each badge rewards.
WINNER, TOP10, MONTHLY, MEMBER, RISING = 'winner', 'top10', 'monthly', 'member', 'rising'


@dataclass(frozen=True)
class BadgeSpec:
    name: str
    description: str
    badge_type_id: int
    multiple_grant: bool = False


@dataclass(frozen=True)
class Grant:
    badge: BadgeSpec
    username: str
    post: Post

    @property
    def ledger_key(self) -> str:
        return f'{self.badge.name}|{self.username}|{self.post.id}'


MONTHLY_BADGE = BadgeSpec('OOTD of the Month', 'Tenue la plus appréciée du mois', BRONZE, multiple_grant=True)


def badge_specs(period: Period) -> Dict[str, BadgeSpec]:
    """
    Badges awarded for a period, by role.

    Yearly badges carry the year in their name. Quarterly badges are reusable
    (multiple grant): each grant links to the winning post, which dates it,
    and the forum does not collect four new badges a year. A monthly review
    only awards the outfit of the month.
    """
    if period.kind == 'year':
        year = period.year
        return {
            WINNER: BadgeSpec(f'OOTD of the Year {year}', f'Tenue la plus appréciée de {year}', GOLD),
            TOP10: BadgeSpec(f'OOTD Top 10 {year}', f'Une des 10 meilleures tenues de {year}', SILVER),
            MONTHLY: MONTHLY_BADGE,
            MEMBER: BadgeSpec(f'Member of the Year {year}', f'Membre de l\'année {year} sur l\'OOTD', GOLD),
            RISING: BadgeSpec(f'Rising Star {year}', f'Révélation OOTD de l\'année {year}', SILVER),
        }
    if period.kind == 'quarter':
        return {
            WINNER: BadgeSpec('OOTD of the Quarter', 'Tenue la plus appréciée du trimestre', SILVER, True),
            MONTHLY: MONTHLY_BADGE,
            MEMBER: BadgeSpec('Member of the Quarter', 'Membre du trimestre sur l\'OOTD', SILVER, True),
            RISING: BadgeSpec('Rising Star of the Quarter', 'Révélation OOTD du trimestre', BRONZE, True),
        }
    return {WINNER: MONTHLY_BADGE}


def planned_grants(awards: Awards) -> List[Grant]:
    """Every badge grant implied by the awards, each pointing at the winning post."""
    specs = badge_specs(awards.period)
    grants = []
    if awards.winner:
        grants.append(Grant(specs[WINNER], awards.winner.username, awards.winner))

    if TOP10 in specs:
        seen = set()
        for post in awards.top:
            if post.username not in seen:
                seen.add(post.username)
                grants.append(Grant(specs[TOP10], post.username, post))

    if MONTHLY in specs:
        for post in awards.monthly.values():
            grants.append(Grant(specs[MONTHLY], post.username, post))

    if MEMBER in specs and awards.members:
        member = awards.members[0]
        grants.append(Grant(specs[MEMBER], member.username, member.outfits[0]))
    if RISING in specs and awards.rising:
        star = awards.rising[0]
        grants.append(Grant(specs[RISING], star.username, star.outfits[0]))
    return grants


def read_ledger(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()}


def append_ledger(path: Path, entry: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(f'{entry}\n')


def apply_badges(client, awards: Awards, ledger_path: Path, publish: bool,
                 log: Callable[[str], None] = print) -> List[Grant]:
    """
    Create missing badges and grant them. Without publish, only log the plan.

    Returns:
        The grants that were (or, in dry-run, would be) made
    """
    grants = planned_grants(awards)
    done = read_ledger(ledger_path)
    pending = [g for g in grants if g.ledger_key not in done]

    if not publish:
        log('Dry run: nothing is sent to the forum. Re-run with --publish to apply.')
        for spec in badge_specs(awards.period).values():
            log(f'  badge   {spec.name} (type {spec.badge_type_id}, multiple={spec.multiple_grant})')
        for grant in pending:
            log(f'  grant   {grant.badge.name} -> @{grant.username} ({grant.post.path})')
        return pending

    existing = {badge['name']: badge for badge in client.list_badges()}
    badge_ids = {}
    for spec in badge_specs(awards.period).values():
        if spec.name not in existing:
            log(f'Creating badge {spec.name}')
            existing[spec.name] = client.create_badge(
                spec.name, spec.description, spec.badge_type_id, multiple_grant=spec.multiple_grant
            )
        badge_ids[spec.name] = existing[spec.name]['id']

    for grant in pending:
        badge_id = badge_ids[grant.badge.name]
        if not grant.badge.multiple_grant:
            owned = {ub['badge_id'] for ub in client.user_badges(grant.username)}
            if badge_id in owned:
                log(f'Skipping {grant.badge.name} for @{grant.username}: already granted')
                append_ledger(ledger_path, grant.ledger_key)
                continue
        log(f'Granting {grant.badge.name} to @{grant.username}')
        client.grant_badge(grant.username, badge_id, f'{client.forum_url}{grant.post.path}')
        append_ledger(ledger_path, grant.ledger_key)
    return pending


def send_awards_draft(client, awards_markdown: str, period: Period, admin_username: str) -> Dict:
    """Send the awards topic as a PM to the admin for review."""
    title = f'[Brouillon] OOTD Awards {period.label} ({datetime.now():%d/%m %H:%M})'
    return client.create_post(awards_markdown, title=title, target_recipients=admin_username)


def publish_awards_topic(client, awards_markdown: str, period: Period, category_id: int) -> Dict:
    """Create the public awards topic."""
    return client.create_post(awards_markdown, title=f'OOTD Awards {period.label}', category_id=category_id)


def publish_awards_reply(client, awards_markdown: str, topic_id: int) -> Dict:
    """Post the awards as a reply in an existing topic (e.g. the OOTD best-of topic)."""
    return client.create_post(awards_markdown, topic_id=topic_id)


def post_link(client, post: Dict) -> str:
    """Forum URL of a post returned by create_post."""
    return f"{client.forum_url}/t/{post.get('topic_slug', '-')}/{post.get('topic_id')}/{post.get('post_number', 1)}"


def wrapped_title(period: Period) -> str:
    return f'Ton bilan OOTD {period.label} sur Borasification'


def wrapped_recipients(awards: Awards) -> List[MemberStats]:
    """Members with enough outfits in the period to get a Wrapped message."""
    return [m for m in awards.members if m.count >= awards.period.min_outfits]


def send_wrapped(client, awards: Awards, fans: Dict[str, Dict], ledger_path: Path,
                 send: bool, admin_username: str, only_username: Optional[str] = None,
                 resend: bool = False, log: Callable[[str], None] = print) -> List[str]:
    """
    Send Wrapped PMs.

    Without send, a single preview goes to the admin: only_username's Wrapped,
    or the top-ranked member's. With send, every eligible member not already
    in the ledger gets theirs, or only only_username when given (any member
    with outfits in the period). A member already in the ledger is skipped
    unless resend is set, e.g. to send a corrected version.

    Returns:
        Usernames whose Wrapped was sent (or previewed)
    """
    if only_username:
        member = awards.member(only_username)
        if member is None:
            raise ValueError(f'@{only_username} has no outfits in {awards.period.label}')
        targets = [member]
    else:
        targets = wrapped_recipients(awards)
        if not targets:
            log('No member is eligible for a Wrapped message.')
            return []

    if not send:
        member = targets[0]
        body = render_wrapped(awards, member, fans.get(member.username))
        post = client.create_post(body, title=f'[Aperçu {member.username}] {wrapped_title(awards.period)}',
                                  target_recipients=admin_username)
        audience = f'@{member.username}' if only_username else f'{len(targets)} members'
        log(f'Preview of @{member.username}\'s Wrapped sent to @{admin_username}: {post_link(client, post)}')
        log(f'Re-run with --send to message {audience}.')
        return [member.username]

    sent = read_ledger(ledger_path)
    delivered = []
    for member in targets:
        if member.username in sent and not resend:
            log(f'Skipping @{member.username}: already sent (add --resend to send again)')
            continue
        body = render_wrapped(awards, member, fans.get(member.username))
        post = client.create_post(body, title=wrapped_title(awards.period), target_recipients=member.username)
        if member.username not in sent:
            append_ledger(ledger_path, member.username)
        delivered.append(member.username)
        log(f'Sent Wrapped to @{member.username} ({len(delivered)}): {post_link(client, post)}')
    log(f'Done: {len(delivered)} sent, {len(targets) - len(delivered)} skipped.')
    return delivered
