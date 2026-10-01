"""
Tests for rate limiter.
"""

import time
import pytest
from unittest.mock import patch

from ootd_awards.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test cases for RateLimiter class."""
    
    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(rate=1.0, max_tokens=5)
        assert limiter.rate == 1.0
        assert limiter.max_tokens == 5
        assert limiter.tokens == 5
    
    def test_acquire_no_wait_when_tokens_available(self):
        """Test that acquire doesn't wait when tokens are available."""
        limiter = RateLimiter(rate=1.0, max_tokens=5)
        
        start_time = time.time()
        limiter.acquire(tokens=2)
        elapsed = time.time() - start_time
        
        # Should be very fast (no waiting)
        assert elapsed < 0.1
        assert limiter.tokens == 3
    
    def test_acquire_waits_when_tokens_needed(self):
        """Test that acquire waits when tokens need to be replenished."""
        limiter = RateLimiter(rate=2.0, max_tokens=1)  # 2 tokens/sec, max 1
        
        # Consume the only token
        limiter.acquire(tokens=1)
        assert limiter.tokens == 0
        
        # Next acquire should wait
        start_time = time.time()
        limiter.acquire(tokens=1)
        elapsed = time.time() - start_time
        
        # Should wait approximately 0.5 seconds (1 token / 2 tokens/sec)
        assert 0.4 <= elapsed <= 0.6
    
    def test_max_tokens_limit(self):
        """Test that tokens don't exceed max_tokens."""
        limiter = RateLimiter(rate=10.0, max_tokens=3)
        
        # Wait long enough that tokens would exceed max
        time.sleep(0.5)
        
        # Manually trigger token replenishment
        limiter.acquire(tokens=0)  # Acquire 0 tokens to trigger replenishment
        
        # Tokens should be capped at max_tokens
        assert limiter.tokens <= 3
    
    def test_multiple_acquires(self):
        """Test multiple consecutive acquires."""
        limiter = RateLimiter(rate=10.0, max_tokens=5)
        
        for _ in range(3):
            limiter.acquire()
        
        # Should have 2 tokens remaining (allowing for small floating point precision)
        assert abs(limiter.tokens - 2) < 0.01
    
    def test_concurrent_access(self):
        """Test that rate limiter is thread-safe."""
        import threading
        
        # Near-zero refill rate: the check must not depend on thread timing
        limiter = RateLimiter(rate=0.001, max_tokens=100)
        results = []
        
        def acquire_token():
            limiter.acquire()
            results.append(1)
        
        threads = [threading.Thread(target=acquire_token) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # All threads should have acquired tokens
        assert len(results) == 10
        assert abs(limiter.tokens - 90) < 0.01

