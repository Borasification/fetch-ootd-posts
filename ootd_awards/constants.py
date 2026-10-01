"""
Constants for the Discourse API client.
"""

# API Configuration
DEFAULT_RATE_LIMIT = 1.0  # requests per second
MAX_TOKENS = 1  # Maximum tokens for rate limiter (1 = no burst, steady rate)
DATA_EXPLORER_MAX_ROWS = 10_000  # Data Explorer QUERY_RESULT_MAX_LIMIT: rows per query run
MAX_RETRIES = 5  # Maximum retries for rate-limited requests
MAX_BACKOFF_SECONDS = 30  # Maximum wait time for exponential backoff
REQUEST_TIMEOUT = (10, 120)  # seconds to connect, seconds to wait for the response (a Data Explorer run)
TRANSIENT_STATUS = (502, 503, 504)  # forum temporarily unavailable

# HTTP Status Codes
HTTP_SUCCESS = (200, 201, 204)
HTTP_TOO_MANY_REQUESTS = 429

# Rate Limit Headers
RATE_LIMIT_REMAINING_HEADER = 'X-RateLimit-Remaining'
RATE_LIMIT_LIMIT_HEADER = 'X-RateLimit-Limit'
RATE_LIMIT_RESET_HEADER = 'X-RateLimit-Reset'
