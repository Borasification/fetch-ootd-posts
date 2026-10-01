"""
Rate limiting utilities for API requests.

Implements a token bucket algorithm for smooth rate limiting.
"""

import time
from threading import Lock
from typing import Optional


class RateLimiter:
    """
    Token bucket rate limiter for API requests.
    Allows bursts while maintaining average rate.
    
    Example:
        limiter = RateLimiter(rate=0.5, max_tokens=5)
        limiter.acquire()  # Will wait if needed to respect rate limit
    """
    
    def __init__(self, rate: float = 0.5, max_tokens: int = 5):
        """
        Initialize rate limiter.
        
        Args:
            rate: Tokens per second to add to bucket
            max_tokens: Maximum number of tokens (allows bursts)
        """
        self.rate = rate
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.last_update = time.time()
        self.lock = Lock()
    
    def acquire(self, tokens: int = 1):
        """
        Wait until enough tokens are available.
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        while True:
            with self.lock:
                now = time.time()
                # Add tokens based on elapsed time since last update
                elapsed = now - self.last_update
                self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
                self.last_update = now
                
                if self.tokens >= tokens:
                    # We have enough tokens, consume them and return
                    self.tokens -= tokens
                    return
            
            # Not enough tokens, calculate wait time
            # We need (tokens - self.tokens) more tokens
            # At rate tokens/sec, that takes (tokens - self.tokens) / rate seconds
            wait_time = (tokens - self.tokens) / self.rate
            
            if wait_time > 0:
                time.sleep(wait_time)
                # After sleeping, the while loop will re-check and add the tokens
                # that accumulated during the sleep

