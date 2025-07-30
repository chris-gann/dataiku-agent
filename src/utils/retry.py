"""
Retry utilities with exponential backoff.

This module provides retry functionality with configurable backoff strategies
for handling transient failures in external API calls.
"""
import asyncio
import random
import time
from typing import Callable, TypeVar, Optional, Union, Type, Tuple, Any
from dataclasses import dataclass
from functools import wraps

from ..core.exceptions import (
    is_retryable,
    get_retry_after,
    MaxRetriesExceededError,
)
from ..core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    
    # Specific exceptions to retry
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    
    # Function to determine if an exception is retryable
    is_retryable_func: Optional[Callable[[Exception], bool]] = None
    
    def calculate_delay(self, attempt: int, error: Optional[Exception] = None) -> float:
        """
        Calculate delay for the given attempt.
        
        Args:
            attempt: Current attempt number (0-based)
            error: The exception that caused the retry
            
        Returns:
            Delay in seconds
        """
        # Check if error has a specific retry-after value
        if error:
            retry_after = get_retry_after(error)
            if retry_after is not None:
                return min(retry_after, self.max_delay)
        
        # Calculate exponential backoff
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        # Add jitter if enabled
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        
        return delay
    
    def should_retry(self, error: Exception) -> bool:
        """
        Determine if an error should be retried.
        
        Args:
            error: The exception to check
            
        Returns:
            True if the error should be retried
        """
        # Check custom function first
        if self.is_retryable_func:
            return self.is_retryable_func(error)
        
        # Check if it's an instance of retry_exceptions
        if isinstance(error, self.retry_exceptions):
            return is_retryable(error)
        
        return False


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    **retry_kwargs
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry a function with exponential backoff.
    
    Args:
        config: Retry configuration
        **retry_kwargs: Keyword arguments to override config
        
    Returns:
        Decorated function
    """
    if config is None:
        config = RetryConfig(**retry_kwargs)
    else:
        # Override config with any provided kwargs
        for key, value in retry_kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            last_error = None
            
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                
                except Exception as e:
                    last_error = e
                    
                    if not config.should_retry(e) or attempt == config.max_attempts - 1:
                        logger.error(
                            "retry_failed",
                            function=func.__name__,
                            attempt=attempt + 1,
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                        raise
                    
                    delay = config.calculate_delay(attempt, e)
                    
                    logger.warning(
                        "retrying_operation",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=config.max_attempts,
                        delay_seconds=round(delay, 2),
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    
                    time.sleep(delay)
            
            # Should never reach here, but just in case
            raise MaxRetriesExceededError(
                f"Max retries ({config.max_attempts}) exceeded for {func.__name__}",
                attempts=config.max_attempts,
                last_error=last_error,
            )
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_error = None
            
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                
                except Exception as e:
                    last_error = e
                    
                    if not config.should_retry(e) or attempt == config.max_attempts - 1:
                        logger.error(
                            "retry_failed",
                            function=func.__name__,
                            attempt=attempt + 1,
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                        raise
                    
                    delay = config.calculate_delay(attempt, e)
                    
                    logger.warning(
                        "retrying_operation",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=config.max_attempts,
                        delay_seconds=round(delay, 2),
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    
                    await asyncio.sleep(delay)
            
            # Should never reach here, but just in case
            raise MaxRetriesExceededError(
                f"Max retries ({config.max_attempts}) exceeded for {func.__name__}",
                attempts=config.max_attempts,
                last_error=last_error,
            )
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class RetryManager:
    """
    Context manager for manual retry logic.
    
    Example:
        with RetryManager(max_attempts=3) as retry:
            while retry.should_continue():
                try:
                    result = do_something()
                    break
                except Exception as e:
                    retry.record_attempt(e)
    """
    
    def __init__(self, config: Optional[RetryConfig] = None, **kwargs):
        self.config = config or RetryConfig(**kwargs)
        self.attempts = 0
        self.last_error = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
    
    def should_continue(self) -> bool:
        """Check if we should continue retrying."""
        return self.attempts < self.config.max_attempts
    
    def record_attempt(self, error: Exception) -> None:
        """
        Record a failed attempt.
        
        Args:
            error: The exception that occurred
            
        Raises:
            The original exception if it shouldn't be retried
            MaxRetriesExceededError if max attempts reached
        """
        self.attempts += 1
        self.last_error = error
        
        if not self.config.should_retry(error):
            raise error
        
        if self.attempts >= self.config.max_attempts:
            raise MaxRetriesExceededError(
                f"Max retries ({self.config.max_attempts}) exceeded",
                attempts=self.attempts,
                last_error=error,
            )
        
        delay = self.config.calculate_delay(self.attempts - 1, error)
        
        logger.warning(
            "retry_manager_retrying",
            attempt=self.attempts,
            max_attempts=self.config.max_attempts,
            delay_seconds=round(delay, 2),
            error=str(error),
            error_type=type(error).__name__,
        )
        
        time.sleep(delay) 