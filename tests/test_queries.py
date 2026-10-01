"""
Checks on the Data Explorer SQL files, which cannot run locally.
"""

from pathlib import Path

import pytest

QUERIES = sorted((Path(__file__).parent.parent / 'ootd_awards' / 'queries').glob('*.sql'))


@pytest.mark.parametrize('query', QUERIES, ids=lambda path: path.name)
def test_no_semicolons(query):
    # Data Explorer rejects any semicolon, even in comments
    assert ';' not in query.read_text(encoding='utf-8')


def test_queries_found():
    assert {path.name for path in QUERIES} == {'year_posts.sql', 'fans.sql'}
