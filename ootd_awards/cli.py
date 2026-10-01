"""
Command line: OOTD awards for a year, quarter or month.

    python -m ootd_awards <command> --period 2026-Q1

Data comes from two Data Explorer queries (queries/*.sql), cached in data/.
Nothing public happens without --publish or --send, and results still
settling (less than 30 days after the period ends) need --allow-provisional
as well.
"""

import argparse
import sys
from collections import Counter
from datetime import date

from . import config, publish
from .awards import compute_awards
from .client import DiscourseClient
from .config import DATA_DIR, FORUM_URL, OUTPUT_DIR
from .dataset import (
    EXCLUSIONS_FILE, FANS, POSTS, add_exclusion, exclude_posts, load_exclusions, load_fans, load_posts,
    missing_months,
)
from .period import Period, month_name
from .render import render_awards, render_wrapped


def make_client(args):
    if not config.username or not config.api_secret:
        sys.exit('Missing credentials: set DISCOURSE_API_USERNAME and DISCOURSE_API_KEY '
                 '(or username/api_secret in config_local.py)')
    return DiscourseClient(args.forum_url, config.username, config.api_secret)


def require(value, flag):
    if not value:
        sys.exit(f'Missing Data Explorer query ID: pass {flag} or set it in config')
    return int(value)


def resolve_period(args) -> Period:
    """--period wins; --year is a shorthand for a yearly period; default is last year."""
    try:
        if args.period:
            return Period.parse(args.period)
        return Period.parse(str(args.year or date.today().year - 1))
    except ValueError as error:
        sys.exit(str(error))


def warn_if_provisional(args):
    """Print a warning when the period's 30-day like windows are still open."""
    if args.period.is_provisional():
        print(f'⚠ {args.period.label}: provisional results. Outfits keep collecting their 30-day likes '
              f'until {args.period.settles_on:%d/%m/%Y}.')
        return True
    return False


def refuse_if_provisional(args):
    """Stop before a public action on a provisional period, unless explicitly allowed."""
    if warn_if_provisional(args) and not args.allow_provisional:
        sys.exit('Refusing to publish provisional results: wait until then, or pass --allow-provisional.')


def require_cache(args, kind):
    """Only `fetch` queries Data Explorer; every other command works from the monthly cache."""
    missing = missing_months(args.period, DATA_DIR, kind)
    if missing:
        sys.exit(f'No data for {", ".join(missing)}: run `fetch --period {args.period.key}` first.')


def load(args, client=None, refresh=False):
    """Compute the awards from the cached posts (refetching them when refresh is set)."""
    if refresh:
        query_id = require(args.query_id, '--query-id')
    else:
        require_cache(args, POSTS)
        client, query_id = None, None
    posts = load_posts(client, query_id, args.period, DATA_DIR, refresh=refresh)
    exclusions = load_exclusions(DATA_DIR)
    kept = exclude_posts(posts, exclusions)
    if len(kept) < len(posts):
        print(f'{len(posts) - len(kept)} post(s) ignored: listed in data/{EXCLUSIONS_FILE}')
    return compute_awards(kept, args.period), kept


def fans(args, client=None, refresh=False):
    """Each member's biggest fan, from the monthly cache (refetched when refresh is set)."""
    if refresh:
        if not args.fans_query_id:
            print('No fans query ID configured: Wrapped will omit the biggest fan.')
            return {}
        query_id = int(args.fans_query_id)
    else:
        missing = missing_months(args.period, DATA_DIR, FANS)
        if missing:
            print(f'No fans data for {", ".join(missing)}: Wrapped will omit the biggest fan. '
                  f'Run `fetch --period {args.period.key}` to include it.')
            return {}
        client, query_id = None, None
    return load_fans(client, query_id, args.period, DATA_DIR, refresh=refresh)


def period_output_dir(period):
    path = OUTPUT_DIR / period.key
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_awards(awards):
    markdown = render_awards(awards)
    path = period_output_dir(awards.period) / 'awards.md'
    path.write_text(markdown, encoding='utf-8')
    print(f'Awards written to {path}')
    return markdown


def cmd_fetch(args):
    client = make_client(args)
    awards, posts = load(args, client, refresh=True)
    fans(args, client, refresh=True)
    print(f'{len(posts)} OOTD posts with images in {args.period.label}')
    warn_if_provisional(args)
    print('Topics included (check that no topic is missing or unexpected):')
    topics = Counter((p.topic_id, p.topic_title) for p in posts)
    for (topic_id, title), count in sorted(topics.items()):
        print(f'  {topic_id:>6}  {title}  ({count} posts)')


def cmd_awards(args):
    awards, _ = load(args)
    warn_if_provisional(args)
    write_awards(awards)
    print(f'\nTop {len(awards.top)} (30-day likes / total likes):')
    for rank, post in enumerate(awards.top, 1):
        print(f'  {rank:>2}. @{post.username:<20} {post.likes_30d:>3} / {post.like_count:>3}  '
              f'{args.forum_url}{post.path}')
    print('\nOutfit of the month:')
    for month, post in awards.monthly.items():
        print(f'  {month_name(month):<10} @{post.username} ({post.likes_30d})')
    for label, ranking in (('Member of the period', awards.members), ('Rising star', awards.rising)):
        print(f'\n{label}:')
        for rank, member in enumerate(ranking[:3], 1):
            print(f'  {rank}. @{member.username} ({member.count} outfits, '
                  f'best-{member.best_n} score {member.best_n_score}, median {member.median_likes:g})')
    print(f'\nMost consistent (> {awards.consistency_threshold:g} likes):')
    for rank, (username, count) in enumerate(awards.consistent[:3], 1):
        print(f'  {rank}. @{username} ({count} outfits)')
    print('\nPilier de l\'OOTD (outfits posted):')
    for rank, member in enumerate(awards.pillars[:3], 1):
        print(f'  {rank}. @{member.username} ({member.count} outfits, {member.total_likes} likes)')


def cmd_draft(args):
    client = make_client(args)
    awards, _ = load(args, client)
    warn_if_provisional(args)
    post = publish.send_awards_draft(client, write_awards(awards), args.period, config.username)
    print(f'Draft sent to @{config.username}: {publish.post_link(client, post)}')


def cmd_publish(args):
    refuse_if_provisional(args)
    client = make_client(args)
    awards, _ = load(args, client)
    markdown = write_awards(awards)
    if args.topic_id:
        post = publish.publish_awards_reply(client, markdown, args.topic_id)
        print(f'Awards posted: {args.forum_url}/t/{post["topic_slug"]}/{post["topic_id"]}/{post["post_number"]}')
    else:
        post = publish.publish_awards_topic(client, markdown, args.period, args.category_id)
        print(f'Awards topic published: {args.forum_url}/t/{post["topic_slug"]}/{post["topic_id"]}')


def cmd_badges(args):
    if args.publish:
        refuse_if_provisional(args)
    else:
        warn_if_provisional(args)
    client = make_client(args) if args.publish else None
    awards, _ = load(args, client)
    publish.apply_badges(client, awards, DATA_DIR / 'badges_granted.txt', args.publish)


def cmd_wrapped(args):
    if args.resend and not args.to:
        sys.exit('--resend only works with --to USERNAME: it never re-sends to every member.')
    if args.send:
        refuse_if_provisional(args)
    else:
        warn_if_provisional(args)
    client = make_client(args)
    awards, _ = load(args, client)
    member_fans = fans(args, client)
    wrapped_dir = period_output_dir(args.period) / 'wrapped'
    wrapped_dir.mkdir(exist_ok=True)
    recipients = publish.wrapped_recipients(awards)
    if args.to and awards.member(args.to) and awards.member(args.to) not in recipients:
        recipients.append(awards.member(args.to))
    for member in recipients:
        (wrapped_dir / f'{member.username}.md').write_text(
            render_wrapped(awards, member, member_fans.get(member.username)), encoding='utf-8'
        )
    print(f'{len(recipients)} Wrapped messages written to {wrapped_dir}')
    publish.send_wrapped(
        client, awards, member_fans, DATA_DIR / f'wrapped_sent_{args.period.key}.txt',
        send=args.send, admin_username=config.username, only_username=args.to, resend=args.resend,
    )


def cmd_exclude(args):
    if args.list:
        path = DATA_DIR / EXCLUSIONS_FILE
        print(path.read_text(encoding='utf-8') if path.exists() else 'No excluded posts.')
        return
    if not args.url:
        sys.exit('Give a post link, e.g. exclude https://forum.borasification.com/t/<slug>/<topic>/<post>')
    try:
        topic_id, post_number = add_exclusion(DATA_DIR, args.url, args.reason or '')
    except ValueError as error:
        sys.exit(str(error))
    print(f'Post {topic_id}/{post_number} excluded from every ranking, award, Wrapped and badge '
          f'(data/{EXCLUSIONS_FILE}). Nothing was sent to the forum.')


def main():
    parser = argparse.ArgumentParser(
        description='OOTD awards for a year, quarter or month: awards topic, badges, Wrapped messages',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Periods: 2025 (year), 2026-Q1 (quarter), 2026-03 (month). --year 2025 = --period 2025.

Typical flow:
  python -m ootd_awards fetch --period 2026-Q1     # run the Data Explorer queries, cache results
  python -m ootd_awards awards --period 2026-Q1    # compute awards, write output/2026-Q1/awards.md
  python -m ootd_awards draft --period 2026-Q1     # PM the awards topic to yourself for review
  python -m ootd_awards publish --period 2026-Q1 --category-id 5
  python -m ootd_awards badges --period 2026-Q1    # dry run, then --publish
  python -m ootd_awards wrapped --period 2026-Q1   # preview PM to yourself, then --send
        """,
    )
    common = argparse.ArgumentParser(add_help=False)
    period_group = common.add_mutually_exclusive_group()
    period_group.add_argument('--period', help='2025, 2026-Q1 or 2026-03 (default: last year)')
    period_group.add_argument('--year', type=int, help='Shorthand for --period YEAR')
    common.add_argument('--allow-provisional', action='store_true',
                        help='Allow publishing results less than 30 days after the period ends')
    common.add_argument('--forum-url', default=FORUM_URL)
    common.add_argument('--query-id', default=config.year_posts_query_id,
                        help='Data Explorer ID of year_posts.sql')
    common.add_argument('--fans-query-id', default=config.fans_query_id,
                        help='Data Explorer ID of fans.sql')

    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('fetch', parents=[common], help='Run the queries and refresh the local cache').set_defaults(func=cmd_fetch)
    commands.add_parser('awards', parents=[common], help='Compute awards and write awards.md').set_defaults(func=cmd_awards)
    commands.add_parser('draft', parents=[common], help='Send the awards topic as a PM to yourself').set_defaults(func=cmd_draft)

    publish_parser = commands.add_parser(
        'publish', parents=[common], help='Publish the awards: new topic, or reply in an existing topic')
    target = publish_parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--category-id', type=int, help='Create a new "OOTD Awards <period>" topic in this category')
    target.add_argument('--topic-id', type=int, help='Post the awards as a reply in this topic (e.g. the best-of)')
    publish_parser.set_defaults(func=cmd_publish)

    badges_parser = commands.add_parser('badges', parents=[common], help='Create and grant badges (dry run by default)')
    badges_parser.add_argument('--publish', action='store_true', help='Actually create and grant badges')
    badges_parser.set_defaults(func=cmd_badges)

    wrapped_parser = commands.add_parser('wrapped', parents=[common], help='Write Wrapped PMs, preview one to yourself')
    wrapped_parser.add_argument('--send', action='store_true',
                                help='Send to every eligible member, or only to --to')
    wrapped_parser.add_argument('--to', '--preview-user', dest='to', metavar='USERNAME',
                                help='Only this member: preview their Wrapped to yourself, or send it with --send')
    wrapped_parser.add_argument('--resend', action='store_true',
                                help='Send again to members already sent to (e.g. a corrected version)')
    wrapped_parser.set_defaults(func=cmd_wrapped)

    exclude_parser = commands.add_parser(
        'exclude', help='Mark a post as "not an outfit" so every period ignores it (local only)')
    exclude_parser.add_argument('url', nargs='?', help='Post link: .../t/<slug>/<topic>/<post number>')
    exclude_parser.add_argument('--reason', help='Note kept next to the link, e.g. "photo de savon"')
    exclude_parser.add_argument('--list', action='store_true', help='Show the excluded posts')
    exclude_parser.set_defaults(func=cmd_exclude)

    args = parser.parse_args()
    if args.func is not cmd_exclude:
        args.period = resolve_period(args)
    args.func(args)
