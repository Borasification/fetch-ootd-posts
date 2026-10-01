"""
Tests for Discourse API client.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from ootd_awards.client import DiscourseClient, RateLimitInfo


class TestDiscourseClient:
    """Test cases for DiscourseClient class."""
    
    def test_initialization(self):
        """Test client initialization."""
        client = DiscourseClient(
            'https://forum.example.com',
            'testuser',
            'testkey'
        )
        
        assert client.forum_url == 'https://forum.example.com'
        assert client.headers['Api-Username'] == 'testuser'
        assert client.headers['Api-Key'] == 'testkey'
    
    def test_parse_rate_limit_headers(self):
        """Test parsing rate limit headers."""
        mock_response = Mock()
        mock_response.headers = {
            'X-RateLimit-Remaining': '10',
            'X-RateLimit-Limit': '60',
            'X-RateLimit-Reset': '1234567890'
        }
        
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        info = client._parse_rate_limit_headers(mock_response)
        
        assert isinstance(info, RateLimitInfo)
        assert info.remaining == '10'
        assert info.limit == '60'
        assert info.reset == '1234567890'
    
    def test_parse_rate_limit_headers_missing(self):
        """Test parsing when headers are missing."""
        mock_response = Mock()
        mock_response.headers = {}
        
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        info = client._parse_rate_limit_headers(mock_response)
        
        assert info.remaining is None
        assert info.limit is None
        assert info.reset is None
    
    @patch('requests.get')
    @patch('time.sleep')
    def test_handle_rate_limit_429_retry(self, mock_sleep, mock_get):
        """Test handling 429 rate limit with retry."""
        # First call returns 429, second returns 200
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.json.return_value = {'extras': {'wait_seconds': 2}}
        mock_response_429.headers = {}
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'success': True}
        mock_response_200.headers = {}  # No rate limit headers, so _adjust_rate_limiter won't sleep
        
        mock_get.side_effect = [mock_response_429, mock_response_200]
        
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        result = client._handle_rate_limit(
            mock_response_429,
            'https://forum.example.com/test',
            None,
            {}
        )
        
        assert result.status_code == 200
        # Sleep is called once for the retry wait (the 2 seconds)
        # The _adjust_rate_limiter shouldn't sleep since headers are empty (remaining is None, not '0')
        # We check that sleep was called at least once
        assert mock_sleep.call_count >= 1
        # mock_get is called once for the retry (after initial 429 response)
        assert mock_get.call_count >= 1
    
    @patch('requests.get')
    @patch('time.sleep')
    def test_handle_rate_limit_max_retries(self, mock_sleep, mock_get):
        """Test that max retries are respected."""
        # Always return 429
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {'extras': {'wait_seconds': 1}}
        mock_response.headers = {}
        mock_get.return_value = mock_response
        
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        
        with pytest.raises(Exception) as exc_info:
            client._handle_rate_limit(
                mock_response,
                'https://forum.example.com/test',
                None,
                {}
            )
        
        assert 'retries' in str(exc_info.value).lower()
        # Should retry MAX_RETRIES times (5)
        assert mock_sleep.call_count == 5



class TestDiscourseClientWrites:
    """Test cases for Data Explorer, posting and badge endpoints."""

    @staticmethod
    def ok(payload, status=200):
        response = Mock()
        response.status_code = status
        response.json.return_value = payload
        response.content = b'{}'
        response.headers = {}
        return response

    @patch('requests.request')
    def test_run_query_maps_columns(self, mock_request):
        mock_request.return_value = self.ok({'columns': ['id', 'username'], 'rows': [[1, 'alice'], [2, 'bob']]})
        client = DiscourseClient('https://forum.example.com', 'user', 'key')

        rows = client.run_query(42, {'start_date': '2025-01-01'})

        assert rows == [{'id': 1, 'username': 'alice'}, {'id': 2, 'username': 'bob'}]
        method, url = mock_request.call_args.args
        assert method == 'POST'
        assert url == 'https://forum.example.com/admin/plugins/explorer/queries/42/run'
        body = mock_request.call_args.kwargs['json']
        assert body['params'] == '{"start_date": "2025-01-01"}'
        assert body['limit'] == 10_000

    @patch('requests.request')
    def test_create_private_message(self, mock_request):
        mock_request.return_value = self.ok({'id': 9, 'topic_id': 3})
        client = DiscourseClient('https://forum.example.com', 'user', 'key')

        client.create_post('hello', title='Hi', target_recipients='alice')

        body = mock_request.call_args.kwargs['json']
        assert body == {'raw': 'hello', 'title': 'Hi', 'target_recipients': 'alice',
                        'archetype': 'private_message'}

    @patch('requests.request')
    def test_grant_badge_with_reason(self, mock_request):
        mock_request.return_value = self.ok({'badges': []})
        client = DiscourseClient('https://forum.example.com', 'user', 'key')

        client.grant_badge('alice', 5, 'https://forum.example.com/t/x/1/2')

        assert mock_request.call_args.kwargs['json'] == {
            'username': 'alice', 'badge_id': 5, 'reason': 'https://forum.example.com/t/x/1/2',
        }

    @patch('requests.request')
    @patch('time.sleep')
    def test_post_is_retried_after_rate_limit(self, mock_sleep, mock_request):
        limited = self.ok({'extras': {'wait_seconds': 1}}, status=429)
        mock_request.side_effect = [limited, self.ok({'id': 1})]
        client = DiscourseClient('https://forum.example.com', 'user', 'key')

        assert client.create_post('hello', topic_id=3) == {'id': 1}
        assert mock_request.call_count == 2
        assert mock_request.call_args.args[0] == 'POST'

    @patch('requests.request')
    def test_request_failure_raises(self, mock_request):
        failed = self.ok({}, status=403)
        failed.text = 'Forbidden'
        mock_request.return_value = failed
        client = DiscourseClient('https://forum.example.com', 'user', 'key')

        with pytest.raises(requests.RequestException, match='403'):
            client.create_post('hello', topic_id=3)

    @patch('requests.get')
    def test_list_badges(self, mock_get):
        mock_get.return_value = self.ok({'badges': [{'id': 1, 'name': 'Basic'}]})
        client = DiscourseClient('https://forum.example.com', 'user', 'key')

        assert client.list_badges() == [{'id': 1, 'name': 'Basic'}]
        assert mock_get.call_args.args[0] == 'https://forum.example.com/admin/badges.json'


class TestNetworkRetries:
    """Network glitches are retried only when a retry cannot create a duplicate."""

    @staticmethod
    def ok(payload):
        response = Mock()
        response.status_code = 200
        response.json.return_value = payload
        response.content = b'{}'
        response.headers = {}
        return response

    @patch('time.sleep')
    @patch('requests.request')
    def test_query_retried_after_connect_timeout(self, mock_request, mock_sleep):
        mock_request.side_effect = [requests.exceptions.ConnectTimeout(), self.ok({'columns': [], 'rows': []})]
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        assert client.run_query(1) == []
        assert mock_request.call_count == 2
        assert mock_request.call_args.kwargs['timeout'] == (10, 120)

    @patch('time.sleep')
    @patch('requests.request')
    def test_query_retried_after_read_timeout_and_503(self, mock_request, mock_sleep):
        unavailable = self.ok({})
        unavailable.status_code = 503
        mock_request.side_effect = [requests.exceptions.ReadTimeout(), unavailable,
                                    self.ok({'columns': ['id'], 'rows': [[1]]})]
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        assert client.run_query(1) == [{'id': 1}]
        assert mock_request.call_count == 3

    @patch('time.sleep')
    @patch('requests.request')
    def test_post_retried_only_if_it_never_reached_the_forum(self, mock_request, mock_sleep):
        mock_request.side_effect = [requests.exceptions.ConnectTimeout(), self.ok({'id': 9})]
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        assert client.create_post('hello', topic_id=3) == {'id': 9}

    @patch('time.sleep')
    @patch('requests.request')
    def test_post_not_retried_after_read_timeout(self, mock_request, mock_sleep):
        # the forum may already have created the post: never send it twice
        mock_request.side_effect = [requests.exceptions.ReadTimeout(), self.ok({'id': 9})]
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        with pytest.raises(requests.exceptions.ReadTimeout):
            client.create_post('hello', topic_id=3)
        assert mock_request.call_count == 1

    @patch('time.sleep')
    @patch('requests.request')
    def test_gives_up_after_max_retries(self, mock_request, mock_sleep):
        mock_request.side_effect = requests.exceptions.ConnectTimeout()
        client = DiscourseClient('https://forum.example.com', 'user', 'key')
        with pytest.raises(requests.exceptions.ConnectTimeout):
            client.run_query(1)
        assert mock_request.call_count == 5
