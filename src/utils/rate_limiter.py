"""
Rate limiting utilities.

This module provides rate limiting functionality using a sliding window
algorithm to prevent API abuse and ensure fair resource usage.
"""
import time
import asyncio
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from threading import Lock
from datetime import datetime, timedelta

from ..core.exceptions import RateLimitError
from ..core.logging import get_logger

logger = get_logger(__name__)


class RateLimitExceeded(RateLimitError):
    """Raised when rate limit is exceeded."""
    pass


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    
    # Maximum requests per window
    max_requests: int
    
    # Window size in seconds
    window_seconds: int
    
    # Optional burst allowance (requests that can exceed the limit temporarily)
    burst_size: int = 0
    
    # Whether to use a sliding window (True) or fixed window (False)
    sliding_window: bool = True
    
    # Optional callback when rate limit is hit
    on_limit_exceeded: Optional[Callable[[str, int], None]] = None


class RateLimiter:
    """
    Rate limiter using sliding window algorithm.
    
    This implementation is thread-safe and supports both synchronous
    and asynchronous usage.
    """
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._requests: Dict[str, deque] = defaultdict(deque)
        self._lock = Lock()
        self._burst_tokens: Dict[str, int] = defaultdict(lambda: config.burst_size)
    
    def _clean_old_requests(self, key: str, current_time: float) -> None:
        """Remove requests older than the window."""
        cutoff_time = current_time - self.config.window_seconds
        
        while self._requests[key] and self._requests[key][0] < cutoff_time:
            self._requests[key].popleft()
    
    def _get_wait_time(self, key: str, current_time: float) -> float:
        """Calculate how long to wait before the next request is allowed."""
        if not self._requests[key]:
            return 0.0
        
        # Find the oldest request that would need to expire
        if len(self._requests[key]) >= self.config.max_requests:
            oldest_request = self._requests[key][0]
            wait_time = (oldest_request + self.config.window_seconds) - current_time
            return max(0.0, wait_time)
        
        return 0.0
    
    def check_rate_limit(self, key: str) -> tuple[bool, Optional[float]]:
        """
        Check if a request is allowed under the rate limit.
        
        Args:
            key: The key to rate limit (e.g., user ID, IP address)
            
        Returns:
            Tuple of (is_allowed, wait_time_seconds)
        """
        current_time = time.time()
        
        with self._lock:
            self._clean_old_requests(key, current_time)
            
            request_count = len(self._requests[key])
            
            # Check if under the limit
            if request_count < self.config.max_requests:
                return True, None
            
            # Check burst tokens
            if self._burst_tokens[key] > 0:
                self._burst_tokens[key] -= 1
                logger.warning(
                    "rate_limit_burst_used",
                    key=key,
                    burst_tokens_remaining=self._burst_tokens[key],
                )
                return True, None
            
            # Calculate wait time
            wait_time = self._get_wait_time(key, current_time)
            
            return False, wait_time
    
    def record_request(self, key: str) -> None:
        """
        Record a request for rate limiting.
        
        Args:
            key: The key to rate limit
        """
        current_time = time.time()
        
        with self._lock:
            self._requests[key].append(current_time)
            
            # Replenish burst tokens over time
            if len(self._requests[key]) < self.config.max_requests // 2:
                self._burst_tokens[key] = min(
                    self._burst_tokens[key] + 1,
                    self.config.burst_size
                )
    
    def acquire(self, key: str, wait: bool = True) -> bool:
        """
        Acquire permission to make a request.
        
        Args:
            key: The key to rate limit
            wait: Whether to wait if rate limit is exceeded
            
        Returns:
            True if request is allowed
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded and wait=False
        """
        while True:
            is_allowed, wait_time = self.check_rate_limit(key)
            
            if is_allowed:
                self.record_request(key)
                return True
            
            if not wait:
                if self.config.on_limit_exceeded:
                    self.config.on_limit_exceeded(key, wait_time or 0)
                
                raise RateLimitExceeded(
                    f"Rate limit exceeded for key: {key}",
                    retry_after=int(wait_time or 0),
                    details={
                        "key": key,
                        "max_requests": self.config.max_requests,
                        "window_seconds": self.config.window_seconds,
                    }
                )
            
            logger.info(
                "rate_limit_waiting",
                key=key,
                wait_seconds=round(wait_time or 0, 2),
            )
            
            time.sleep(wait_time or 0.1)
    
    async def acquire_async(self, key: str, wait: bool = True) -> bool:
        """
        Asynchronously acquire permission to make a request.
        
        Args:
            key: The key to rate limit
            wait: Whether to wait if rate limit is exceeded
            
        Returns:
            True if request is allowed
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded and wait=False
        """
        while True:
            is_allowed, wait_time = self.check_rate_limit(key)
            
            if is_allowed:
                self.record_request(key)
                return True
            
            if not wait:
                if self.config.on_limit_exceeded:
                    self.config.on_limit_exceeded(key, wait_time or 0)
                
                raise RateLimitExceeded(
                    f"Rate limit exceeded for key: {key}",
                    retry_after=int(wait_time or 0),
                    details={
                        "key": key,
                        "max_requests": self.config.max_requests,
                        "window_seconds": self.config.window_seconds,
                    }
                )
            
            logger.info(
                "rate_limit_waiting_async",
                key=key,
                wait_seconds=round(wait_time or 0, 2),
            )
            
            await asyncio.sleep(wait_time or 0.1)
    
    def reset(self, key: Optional[str] = None) -> None:
        """
        Reset rate limit tracking.
        
        Args:
            key: The key to reset. If None, resets all keys.
        """
        with self._lock:
            if key is None:
                self._requests.clear()
                self._burst_tokens.clear()
            else:
                self._requests.pop(key, None)
                self._burst_tokens.pop(key, None)
    
    def get_status(self, key: str) -> Dict[str, Any]:
        """
        Get current rate limit status for a key.
        
        Args:
            key: The key to check
            
        Returns:
            Dictionary with rate limit status
        """
        current_time = time.time()
        
        with self._lock:
            self._clean_old_requests(key, current_time)
            
            request_count = len(self._requests[key])
            remaining = max(0, self.config.max_requests - request_count)
            
            # Calculate reset time
            if self._requests[key]:
                oldest_request = self._requests[key][0]
                reset_time = oldest_request + self.config.window_seconds
            else:
                reset_time = current_time
            
            return {
                "limit": self.config.max_requests,
                "remaining": remaining,
                "used": request_count,
                "reset_time": datetime.fromtimestamp(reset_time).isoformat(),
                "burst_tokens": self._burst_tokens[key],
                "window_seconds": self.config.window_seconds,
            }


class MultiServiceRateLimiter:
    """
    Rate limiter that manages multiple services with different limits.
    """
    
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
    
    def add_service(self, service_name: str, config: RateLimitConfig) -> None:
        """
        Add a service with its rate limit configuration.
        
        Args:
            service_name: Name of the service
            config: Rate limit configuration
        """
        self._limiters[service_name] = RateLimiter(config)
    
    def acquire(self, service_name: str, key: str, wait: bool = True) -> bool:
        """
        Acquire permission for a specific service.
        
        Args:
            service_name: Name of the service
            key: The key to rate limit
            wait: Whether to wait if rate limit is exceeded
            
        Returns:
            True if request is allowed
            
        Raises:
            ValueError: If service is not configured
            RateLimitExceeded: If rate limit is exceeded and wait=False
        """
        if service_name not in self._limiters:
            raise ValueError(f"Service '{service_name}' not configured")
        
        return self._limiters[service_name].acquire(key, wait)
    
    async def acquire_async(
        self, 
        service_name: str, 
        key: str, 
        wait: bool = True
    ) -> bool:
        """
        Asynchronously acquire permission for a specific service.
        
        Args:
            service_name: Name of the service
            key: The key to rate limit
            wait: Whether to wait if rate limit is exceeded
            
        Returns:
            True if request is allowed
            
        Raises:
            ValueError: If service is not configured
            RateLimitExceeded: If rate limit is exceeded and wait=False
        """
        if service_name not in self._limiters:
            raise ValueError(f"Service '{service_name}' not configured")
        
        return await self._limiters[service_name].acquire_async(key, wait)
    
    def get_status(self, service_name: str, key: str) -> Dict[str, Any]:
        """
        Get rate limit status for a service and key.
        
        Args:
            service_name: Name of the service
            key: The key to check
            
        Returns:
            Dictionary with rate limit status
            
        Raises:
            ValueError: If service is not configured
        """
        if service_name not in self._limiters:
            raise ValueError(f"Service '{service_name}' not configured")
        
        return self._limiters[service_name].get_status(key)
    
    def reset(self, service_name: Optional[str] = None, key: Optional[str] = None):
        """
        Reset rate limits.
        
        Args:
            service_name: Service to reset. If None, resets all services.
            key: Key to reset. If None, resets all keys for the service.
        """
        if service_name is None:
            for limiter in self._limiters.values():
                limiter.reset()
        elif service_name in self._limiters:
            self._limiters[service_name].reset(key) 