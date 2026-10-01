# OOTD Awards

Highlights the community's best outfits on the Borasification forum for a **year**, a **quarter** or a **month**:

- an **awards topic**: outfit of the period, top 50 for a year or top 10 for a quarter or month, outfit of each month, member of the period, rising star, most consistent. It is drafted to you as a private message before anything is published;
- **forum badges** for the winners, each linked to the winning post;
- a personal **"Wrapped"** private message for each active member: outfits, likes, rank, best month, biggest fan, awards won, best outfits, and a ready-made best-of block they can paste into their own lookbook.

Only "Outfit of the day" topics are read. Lookbooks are members' personal spaces and are never used for awards.

## How it works

Everything comes from two SQL queries saved in the forum's [Data Explorer](https://meta.discourse.org/t/discourse-data-explorer/32566) plugin and run through the Discourse API:

- `year_posts.sql`: every OOTD post with at least one image, with its likes (total and within 30 days), its images and its author's first OOTD date;
- `fans.sql`: like counts per (member, fan) pair, used for each member's "biggest fan".

Queries run **one month at a time**: a longer range exceeds Data Explorer's statement timeout and its 10,000-row limit. Each month is cached in `data/`, and any period is assembled from its months. Once a quarter has been fetched, its months and its year reuse that data.

## Setup

1. **Python 3.9+ with working SSL** (some old pyenv builds lack it):
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. **Data Explorer queries.** In Admin › Plugins › Data Explorer, create two queries by pasting `ootd_awards/queries/year_posts.sql` and `ootd_awards/queries/fans.sql`. Each query's ID is the number at the end of its URL.
3. **Credentials.** Copy `config_local.example.py` to `config_local.py` (gitignored) and fill in:
   - an **admin** API username and key. Data Explorer and badges need admin access; a global-scope key is simplest;
   - the two query IDs.

   Environment variables take precedence: `DISCOURSE_API_USERNAME`, `DISCOURSE_API_KEY`, `OOTD_YEAR_POSTS_QUERY_ID`, `OOTD_FANS_QUERY_ID`.

## Usage

Run from the repository root:

```bash
python -m ootd_awards <command> --period <period>
```

`--period` takes `2025` (year), `2026-Q1` (quarter) or `2026-03` (month). `--year 2025` is a shorthand, and the default is last year.

### Commands and what they send

| Command | What it does | Writes to the forum? |
|---|---|---|
| `fetch` | Runs the two queries for each month of the period and refreshes the cache | No (read-only queries) |
| `awards` | Prints the winners, writes `output/<period>/awards.md` | No |
| `draft` | Sends the awards topic to **you** as a private message, to check the rendering | Yes, a PM to you only |
| `publish --category-id N` | Creates a new public "OOTD Awards <period>" topic (winners are notified through their @mentions) | **Yes, public** |
| `publish --topic-id N` | Posts the awards as a reply in an existing topic, e.g. the OOTD best-of | **Yes, public** |
| `badges` | Lists the badges and grants it would make | No (dry run) |
| `badges --publish` | Creates missing badges and grants them | **Yes, public**; members are notified |
| `wrapped` | Writes every Wrapped to `output/<period>/wrapped/`, sends **you** one preview | Yes, a PM to you only |
| `wrapped --send` | Sends each eligible member their Wrapped | **Yes, to every eligible member** |
| `wrapped --to NAME` | Sends **you** a preview of that member's Wrapped | Yes, a PM to you only |
| `wrapped --to NAME --send` | Sends the Wrapped to that member only (add `--resend` if they already got one, e.g. a corrected version) | **Yes, to that member** |
| `exclude <post link> [--reason ...]` | Marks a post as "not an outfit" (a product photo, an inspiration collage...) so every period ignores it. `exclude --list` shows them | No (local file `data/excluded_posts.txt`) |

`fetch` is the only command that queries the forum. The others work from the cache, and tell you which months to fetch when data is missing.

### Typical flow

```bash
python -m ootd_awards fetch   --period 2026-Q1
python -m ootd_awards awards  --period 2026-Q1
python -m ootd_awards draft   --period 2026-Q1                     # review the PM on the forum
python -m ootd_awards publish --period 2026-Q1 --category-id <id>  # the category ID is in its URL: /c/<name>/<id>
python -m ootd_awards badges  --period 2026-Q1                     # read the plan...
python -m ootd_awards badges  --period 2026-Q1 --publish           # ...then apply it
python -m ootd_awards wrapped --period 2026-Q1                     # read output/2026-Q1/wrapped/ and your preview PM...
python -m ootd_awards wrapped --period 2026-Q1 --send              # ...then send
```

Publish the topic before granting badges and sending Wrapped messages, so the links members follow are already live.

### Posts that are not outfits

A post in an OOTD topic counts as an outfit when its author uploaded at least one photo in it: quoted photos, link previews and images under 300 px are ignored. The cover shown for a post is its first portrait photo of at least 600 px, otherwise its largest photo. No image rule can tell a product photo from a square outfit shot, so list such posts by hand:

```bash
python -m ootd_awards exclude https://forum.borasification.com/t/<slug>/<topic>/<post> --reason "photo de savon"
```

### Safety

- **No duplicates.** Badge grants are logged in `data/badges_granted.txt` and Wrapped sends in `data/wrapped_sent_<period>.txt`, so re-running never grants or sends twice. The badge log is shared by all periods, so an "OOTD of the Month" won in a quarterly review is not granted again by the yearly one. If you revoke a badge by hand, delete its line from the log.
- **Provisional results.** Outfits are ranked on their first 30 days of likes, so a period's results settle 30 days after it ends (Q3 2026: from 31 October 2026). Before that, every command warns, and `publish`, `badges --publish` and `wrapped --send` refuse to run unless you add `--allow-provisional`.
- **Fresh numbers.** `fetch` always re-queries the period's months, which updates their like counts. Run it again just before publishing.

## Award rules

Outfits are ranked by the likes they received **in their first 30 days**, so an outfit posted at the end of the period competes fairly; total likes break ties. Rules scale with the length of the period:

| Award | Year | Quarter | Month |
|---|---|---|---|
| Outfit of the period and top outfits | Top 50, max 5 per member (shown in blocks of 10) | Top 10, max 2 per member | Top 10, max 2 per member |
| Outfit of the month, for each month | ✓ | ✓ | — |
| Member of the period: sum of the member's best N outfits | N = 10 | N = 5 | N = 3 |
| Rising Star: first OOTD ever in the period, best median, min outfits | 5 | 3 | 2 |
| Most Consistent: most outfits above the period's 75th percentile | ✓ | ✓ | ✓ |
| Pilier de l'OOTD: most outfits posted (total likes break ties), podium of 3 | ✓ | ✓ | ✓ |
| Wrapped PM: min outfits | 5 | 3 | 2 |

### Badges

| Period | Badges |
|---|---|
| Year | OOTD of the Year {year} (gold), OOTD Top 50 {year} (silver), Member of the Year {year} (gold), Rising Star {year} (silver), OOTD of the Month (bronze) |
| Quarter | OOTD of the Quarter (silver), Member of the Quarter (silver), Rising Star of the Quarter (bronze), OOTD of the Month (bronze) |
| Month | OOTD of the Month (bronze) |

Quarterly and monthly badges can be granted several times; each grant links to the winning post, which dates it.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `SSLError: ... SSL module is not available` | The Python build has no OpenSSL; use a recent Python in `.venv` |
| 403 on `fetch` | The API key is not an admin key |
| 404 on `fetch` | Wrong query ID, or Data Explorer disabled |
| `statement timeout` in Data Explorer | Test a single month with "Include query plan" to find the slow step |
| `No data for 2026-10: run fetch ...` | That month has not been fetched yet |
| Wrapped has no "biggest fan" line | Fans data missing for the period: run `fetch` for it |

## Development

```bash
.venv/bin/python -m pytest
```

```
ootd_awards/
  cli.py          commands (python -m ootd_awards)
  config.py       settings from environment variables or config_local.py
  client.py       Discourse API client (Data Explorer, posts, badges), rate limited
  period.py       year / quarter / month periods, French labels, scaled rules
  dataset.py      month-by-month fetch and per-month cache
  awards.py       award rules (pure functions)
  render.py       French markdown for the awards topic and Wrapped PMs
  publish.py      drafts, topic, badges and Wrapped sending
  queries/        the two Data Explorer SQL queries
tests/            pytest suite, with synthetic data only
data/, output/    cache and generated files: forum data, gitignored, never commit
```
