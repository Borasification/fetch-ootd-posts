"""
Forum credentials and settings.

Values come from environment variables, falling back to a gitignored
config_local.py at the repository root (see config_local.example.py).
Never commit real credentials.

    DISCOURSE_API_USERNAME, DISCOURSE_API_KEY
    OOTD_YEAR_POSTS_QUERY_ID, OOTD_FANS_QUERY_ID  (Data Explorer query IDs)
"""

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / 'data'
OUTPUT_DIR = ROOT / 'output'
FORUM_URL = 'https://forum.borasification.com'


def _load_local():
    path = ROOT / 'config_local.py'
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location('config_local', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_local = _load_local()


def _setting(env_name, local_name, default=None):
    return os.environ.get(env_name) or getattr(_local, local_name, default)


username = _setting('DISCOURSE_API_USERNAME', 'username')
api_secret = _setting('DISCOURSE_API_KEY', 'api_secret')
year_posts_query_id = _setting('OOTD_YEAR_POSTS_QUERY_ID', 'year_posts_query_id')
fans_query_id = _setting('OOTD_FANS_QUERY_ID', 'fans_query_id')
