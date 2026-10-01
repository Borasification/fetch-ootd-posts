"""
Review periods: a year, a quarter or a month.

A period knows its date range, its French labels, and how the award rules
scale with its length (a quarter has fewer outfits per member than a year).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

MONTHS_FR = [
    'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
    'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre',
]
QUARTER_ORDINALS_FR = ['premier', 'deuxième', 'troisième', 'quatrième']

# Outfits are ranked on likes received in their first 30 days, so a period's
# results only settle 30 days after it ends.
LIKES_WINDOW_DAYS = 30

# Rules that scale with the period length:
#   top_n           size of the top outfits ranking
#   max_per_member  outfits a member can place in that ranking
#   member_best_n   best outfits summed for the member ranking
#   min_outfits     minimum outfits for Rising Star and for a Wrapped message
RULES = {
    'year': {'top_n': 50, 'max_per_member': 5, 'member_best_n': 10, 'min_outfits': 5},
    'quarter': {'top_n': 10, 'max_per_member': 2, 'member_best_n': 5, 'min_outfits': 3},
    'month': {'top_n': 10, 'max_per_member': 2, 'member_best_n': 3, 'min_outfits': 2},
}


def month_name(month: int) -> str:
    return MONTHS_FR[month - 1]


@dataclass(frozen=True)
class Period:
    kind: str  # 'year', 'quarter' or 'month'
    year: int
    number: int = 0  # quarter 1-4 or month 1-12; 0 for a year

    @classmethod
    def parse(cls, text: str) -> 'Period':
        """Parse '2025', '2026-Q1' or '2026-03'."""
        text = text.strip().upper()
        if re.fullmatch(r'\d{4}', text):
            return cls('year', int(text))
        match = re.fullmatch(r'(\d{4})-Q([1-4])', text)
        if match:
            return cls('quarter', int(match.group(1)), int(match.group(2)))
        match = re.fullmatch(r'(\d{4})-(\d{2})', text)
        if match and 1 <= int(match.group(2)) <= 12:
            return cls('month', int(match.group(1)), int(match.group(2)))
        raise ValueError(f'Invalid period {text!r}: use 2025, 2026-Q1 or 2026-03')

    @property
    def first_month(self) -> int:
        return {'year': 1, 'quarter': 3 * self.number - 2, 'month': self.number}[self.kind]

    @property
    def month_count(self) -> int:
        return {'year': 12, 'quarter': 3, 'month': 1}[self.kind]

    @property
    def months(self) -> List[Tuple[int, int]]:
        """(year, month) pairs covered by the period."""
        return [(self.year, self.first_month + i) for i in range(self.month_count)]

    @property
    def start(self) -> date:
        return date(self.year, self.first_month, 1)

    @property
    def end(self) -> date:
        """First day after the period."""
        last_year, last_month = self.months[-1]
        return date(last_year + 1, 1, 1) if last_month == 12 else date(last_year, last_month + 1, 1)

    def month_windows(self, today: Optional[date] = None) -> List[Tuple[str, str]]:
        """
        [start, end) dates of each month, for month-by-month queries.

        Months that have not started yet are left out: querying them would
        cache an empty month that later looks already fetched.
        """
        today = today or date.today()
        starts = [date(y, m, 1) for y, m in self.months] + [self.end]
        return [(a.isoformat(), b.isoformat()) for a, b in zip(starts, starts[1:]) if a <= today]

    def contains(self, moment: Optional[datetime]) -> bool:
        if moment is None:
            return False
        start = datetime(self.start.year, self.start.month, 1, tzinfo=timezone.utc)
        end = datetime(self.end.year, self.end.month, 1, tzinfo=timezone.utc)
        return start <= moment < end

    @property
    def settles_on(self) -> date:
        """Date from which every outfit of the period has had its full 30 days of likes."""
        return self.end + timedelta(days=LIKES_WINDOW_DAYS)

    def is_provisional(self, today: Optional[date] = None) -> bool:
        return (today or date.today()) < self.settles_on

    @property
    def key(self) -> str:
        """Identifier for file names: 2025, 2026-Q1, 2026-03."""
        if self.kind == 'year':
            return str(self.year)
        if self.kind == 'quarter':
            return f'{self.year}-Q{self.number}'
        return f'{self.year}-{self.number:02d}'

    @property
    def label(self) -> str:
        """Short French label for titles: 2025, T1 2026, mars 2026."""
        if self.kind == 'year':
            return str(self.year)
        if self.kind == 'quarter':
            return f'T{self.number} {self.year}'
        return f'{month_name(self.number)} {self.year}'

    @property
    def intro(self) -> str:
        """Sentence opener: 'En 2025', 'Au premier trimestre 2026', 'En mars 2026'."""
        if self.kind == 'quarter':
            return f'Au {QUARTER_ORDINALS_FR[self.number - 1]} trimestre {self.year}'
        return f'En {self.label}'

    @property
    def of(self) -> str:
        """French complement: de l'année, du trimestre, du mois."""
        return {'year': "de l'année", 'quarter': 'du trimestre', 'month': 'du mois'}[self.kind]

    @property
    def this(self) -> str:
        """French 'this period': cette année, ce trimestre, ce mois-ci."""
        return {'year': 'cette année', 'quarter': 'ce trimestre', 'month': 'ce mois-ci'}[self.kind]

    @property
    def top_n(self) -> int:
        return RULES[self.kind]['top_n']

    @property
    def max_per_member(self) -> int:
        return RULES[self.kind]['max_per_member']

    @property
    def member_best_n(self) -> int:
        return RULES[self.kind]['member_best_n']

    @property
    def min_outfits(self) -> int:
        return RULES[self.kind]['min_outfits']
