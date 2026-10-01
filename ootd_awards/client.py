"""
Discourse API client with rate limiting support.
"""

import json
import time
from typing import Dict, List, NamedTuple, Optional

import requests
from requests import RequestException

from .constants import (
    DATA_EXPLORER_MAX_ROWS,
    DEFAULT_RATE_LIMIT,
    HTTP_SUCCESS,
    HTTP_TOO_MANY_REQUESTS,
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    MAX_TOKENS,
    REQUEST_TIMEOUT,
    TRANSIENT_STATUS,
    RATE_LIMIT_LIMIT_HEADER,
    RATE_LIMIT_REMAINING_HEADER,
    RATE_LIMIT_RESET_HEADER,
)
from .rate_limiter import RateLimiter


class RateLimitInfo(NamedTuple):
    """Rate limit information from API response headers."""
    remaining: Optional[str]
    limit: Optional[str]
    reset: Optional[str]


class DiscourseClient:
    """Client for interacting with Discourse API with built-in rate limiting."""
    
    def __init__(self, forum_url: str, username: str, api_key: str, rate_limit: float = DEFAULT_RATE_LIMIT):
        """
        Initialize Discourse API client.
        
        Args:
            forum_url: Base URL of the Discourse forum
            username: API username
            api_key: API key
            rate_limit: Requests per second (default: 1.0 = 1 request per second)
        """
        self.forum_url = forum_url.rstrip('/')
        self.headers = {
            'Api-Username': username,
            'Api-Key': api_key,
            'Content-Type': 'application/json'
        }
        self.rate_limiter = RateLimiter(rate=rate_limit, max_tokens=MAX_TOKENS)
    
    def _wait_for_rate_limit(self):
        """Wait before making a request to respect rate limits."""
        self.rate_limiter.acquire(tokens=1)
    
    def _parse_rate_limit_headers(self, response: requests.Response) -> RateLimitInfo:
        """
        Parse rate limit headers from response.
        
        Args:
            response: HTTP response object
            
        Returns:
            RateLimitInfo named tuple with rate limit information
        """
        return RateLimitInfo(
            remaining=response.headers.get(RATE_LIMIT_REMAINING_HEADER),
            limit=response.headers.get(RATE_LIMIT_LIMIT_HEADER),
            reset=response.headers.get(RATE_LIMIT_RESET_HEADER)
        )
    
    def _adjust_rate_limiter(self, rate_limit_info: RateLimitInfo):
        """
        Adjust rate limiter based on API rate limit headers.
        
        Note: This does NOT sleep - it only logs information. The rate limiter
        itself handles all timing. Adding sleep here would cause double-delays.
        
        Args:
            rate_limit_info: Parsed rate limit information
        """
        # Log rate limit status for debugging, but don't add extra sleeps
        # The rate limiter already handles spacing between requests
        if rate_limit_info.remaining == '0':
            # We're at the limit - the rate limiter will naturally pace requests
            # No need to sleep here as it would add double delays
            pass
    
    @staticmethod
    def _send(
        method: str,
        url: str,
        headers: Dict,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
        idempotent: bool = True
    ) -> requests.Response:
        """
        Send an HTTP request, retrying network glitches (no rate limiting).

        A request that never reached the forum (connection failure) is always
        retried. Timeouts, dropped connections and 502/503/504 are retried only
        for idempotent requests: retrying a post, PM or badge grant that the
        forum may already have processed could create a duplicate.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if method == 'GET':
                    response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
                else:
                    response = requests.request(method, url, headers=headers, params=params, json=json_body,
                                                timeout=REQUEST_TIMEOUT)
            except requests.exceptions.ConnectTimeout as error:
                problem = error
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
                if not idempotent:
                    raise
                problem = error
            else:
                if response.status_code not in TRANSIENT_STATUS or not idempotent or attempt == MAX_RETRIES:
                    return response
                problem = f'HTTP {response.status_code}'

            if attempt == MAX_RETRIES:
                raise problem
            wait = min(2 ** attempt, MAX_BACKOFF_SECONDS)
            print(f'Network problem ({type(problem).__name__ if isinstance(problem, Exception) else problem}), '
                  f'retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...')
            time.sleep(wait)
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
        idempotent: Optional[bool] = None
    ) -> Dict:
        """
        Make a rate-limited API request and return the decoded JSON.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: Path relative to the forum URL, e.g. '/posts.json'
            params: Query string parameters
            json_body: JSON body for non-GET requests
            idempotent: Safe to retry after a timeout (default: only GET)
            
        Returns:
            Decoded JSON response (empty dict for empty bodies)
            
        Raises:
            RequestException: If the API request fails
        """
        self._wait_for_rate_limit()
        
        url = f'{self.forum_url}{path}'
        if idempotent is None:
            idempotent = method == 'GET'
        response = self._send(method, url, self.headers, params, json_body, idempotent)
        response = self._handle_rate_limit(response, url, params, self.headers, method, json_body, idempotent)
        
        if response.status_code not in HTTP_SUCCESS:
            raise RequestException(
                f"{method} {path} failed with status {response.status_code}: {response.text}"
            )
        
        return response.json() if response.content else {}
    
    def _handle_rate_limit(
        self, 
        response: requests.Response, 
        url: str, 
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        method: str = 'GET',
        json_body: Optional[Dict] = None,
        idempotent: bool = True
    ) -> requests.Response:
        """
        Handle rate limiting with exponential backoff and header parsing.
        
        Args:
            response: HTTP response that may be rate limited
            url: Original request URL
            params: Original request parameters
            headers: Original request headers
            method: Original HTTP method
            json_body: Original JSON body (non-GET requests)
            
        Returns:
            HTTP response (retried if needed)
            
        Raises:
            Exception: If rate limit exceeded after max retries
        """
        original_params = params or {}
        original_headers = headers or self.headers
        retry_count = 0
        
        while response.status_code == HTTP_TOO_MANY_REQUESTS and retry_count < MAX_RETRIES:
            # Get wait time from API response
            try:
                error_data = response.json()
                wait_seconds = error_data.get("extras", {}).get("wait_seconds", 5)
            except (ValueError, KeyError):
                # Fallback to exponential backoff
                wait_seconds = min(2 ** retry_count, MAX_BACKOFF_SECONDS)
            
            print(f"Rate limit hit (attempt {retry_count + 1}/{MAX_RETRIES}). Waiting {wait_seconds:.1f} seconds...")
            time.sleep(wait_seconds)
            
            # Retry with the same request
            response = self._send(method, url, original_headers, original_params, json_body, idempotent)
            retry_count += 1
        
        if response.status_code == HTTP_TOO_MANY_REQUESTS:
            raise RequestException(f"Rate limit exceeded after {MAX_RETRIES} retries")
        
        # Parse and use rate limit headers if available
        rate_limit_info = self._parse_rate_limit_headers(response)
        self._adjust_rate_limiter(rate_limit_info)
        
        return response
    
    def run_query(self, query_id: int, params: Optional[Dict] = None,
                  limit: int = DATA_EXPLORER_MAX_ROWS) -> List[Dict]:
        """
        Run a saved Data Explorer query.
        
        Data Explorer returns at most `limit` rows (capped at 10,000 by the
        server), so large results must be paged by the query itself.
        
        Args:
            query_id: Data Explorer query ID (visible in the query URL)
            params: Query parameters, e.g. {'start_date': '2025-01-01'}
            limit: Maximum number of rows to return
            
        Returns:
            List of rows, each a dict keyed by column name
        """
        body = {'params': json.dumps(params or {}), 'limit': limit}
        # a Data Explorer run is read-only: safe to retry
        result = self._request('POST', f'/admin/plugins/explorer/queries/{query_id}/run', json_body=body,
                               idempotent=True)
        columns = result.get('columns', [])
        return [dict(zip(columns, row)) for row in result.get('rows', [])]
    
    def create_post(
        self,
        raw: str,
        title: Optional[str] = None,
        topic_id: Optional[int] = None,
        category_id: Optional[int] = None,
        target_recipients: Optional[str] = None
    ) -> Dict:
        """
        Create a topic, a reply, or a private message.
        
        Args:
            raw: Post content (markdown)
            title: Topic title (required for new topics and PMs)
            topic_id: Reply to this topic instead of creating a new one
            category_id: Category for a new topic
            target_recipients: Comma-separated usernames; makes it a private message
            
        Returns:
            Created post JSON
        """
        body = {'raw': raw}
        if title:
            body['title'] = title
        if topic_id:
            body['topic_id'] = topic_id
        if category_id:
            body['category'] = category_id
        if target_recipients:
            body['target_recipients'] = target_recipients
            body['archetype'] = 'private_message'
        return self._request('POST', '/posts.json', json_body=body)
    
    def list_badges(self) -> List[Dict]:
        """Return all badges defined on the forum."""
        return self._request('GET', '/admin/badges.json').get('badges', [])
    
    def create_badge(
        self,
        name: str,
        description: str,
        badge_type_id: int,
        multiple_grant: bool = False,
        icon: str = 'trophy'
    ) -> Dict:
        """
        Create a manually-granted badge.
        
        Args:
            name: Badge name (unique)
            description: Short description shown on the badge page
            badge_type_id: 1 = gold, 2 = silver, 3 = bronze
            multiple_grant: Whether a user can receive the badge several times
            icon: Font Awesome icon name
            
        Returns:
            Created badge JSON
        """
        body = {
            'name': name,
            'description': description,
            'badge_type_id': badge_type_id,
            'multiple_grant': multiple_grant,
            'icon': icon,
            'enabled': True,
            'listable': True,
            'allow_title': True,
        }
        return self._request('POST', '/admin/badges.json', json_body=body).get('badge', {})
    
    def user_badges(self, username: str) -> List[Dict]:
        """Return the badges granted to a user."""
        return self._request('GET', f'/user-badges/{username}.json').get('user_badges', [])
    
    def grant_badge(self, username: str, badge_id: int, reason_url: Optional[str] = None) -> Dict:
        """
        Grant a badge to a user.
        
        Args:
            username: Recipient
            badge_id: Badge to grant
            reason_url: Post or topic URL shown as the reason for the badge
            
        Returns:
            Granted user badge JSON
        """
        body = {'username': username, 'badge_id': badge_id}
        if reason_url:
            body['reason'] = reason_url
        return self._request('POST', '/user_badges.json', json_body=body)
