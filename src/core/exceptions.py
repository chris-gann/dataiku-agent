"""
Custom exceptions for Dataiku Agent.

This module defines all custom exceptions used throughout the application
for better error handling and debugging.
"""
from typing import Optional, Dict, Any


class DataikuAgentException(Exception):
    """Base exception for all Dataiku Agent errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(DataikuAgentException):
    """Raised when there's a configuration error."""
    pass


class ValidationError(DataikuAgentException):
    """Raised when input validation fails."""
    pass


# External API Errors
class ExternalAPIError(DataikuAgentException):
    """Base class for external API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body


class SlackAPIError(ExternalAPIError):
    """Raised when Slack API returns an error."""
    pass


class OpenAIAPIError(ExternalAPIError):
    """Raised when OpenAI API returns an error."""
    pass


class BraveSearchAPIError(ExternalAPIError):
    """Raised when Brave Search API returns an error."""
    pass


# Rate Limiting Errors
class RateLimitError(DataikuAgentException):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.retry_after = retry_after


class SlackRateLimitError(RateLimitError):
    """Raised when Slack rate limit is exceeded."""
    pass


class OpenAIRateLimitError(RateLimitError):
    """Raised when OpenAI rate limit is exceeded."""
    pass


class BraveSearchRateLimitError(RateLimitError):
    """Raised when Brave Search rate limit is exceeded."""
    pass


# Cache Errors
class CacheError(DataikuAgentException):
    """Base class for cache-related errors."""
    pass


class CacheConnectionError(CacheError):
    """Raised when cache connection fails."""
    pass


class CacheOperationError(CacheError):
    """Raised when cache operation fails."""
    pass


# Security Errors
class SecurityError(DataikuAgentException):
    """Base class for security-related errors."""
    pass


class AuthenticationError(SecurityError):
    """Raised when authentication fails."""
    pass


class AuthorizationError(SecurityError):
    """Raised when authorization fails."""
    pass


class SignatureVerificationError(SecurityError):
    """Raised when request signature verification fails."""
    pass


# Processing Errors
class ProcessingError(DataikuAgentException):
    """Base class for message processing errors."""
    pass


class MessageTooLongError(ProcessingError):
    """Raised when message exceeds maximum length."""
    
    def __init__(self, message: str, max_length: int, actual_length: int):
        super().__init__(message, {
            "max_length": max_length,
            "actual_length": actual_length
        })
        self.max_length = max_length
        self.actual_length = actual_length


class EmptyQueryError(ProcessingError):
    """Raised when query is empty."""
    pass


class InvalidChannelError(ProcessingError):
    """Raised when message comes from invalid channel."""
    pass


class BlockedUserError(ProcessingError):
    """Raised when message comes from blocked user."""
    pass


# Retry Errors
class RetryError(DataikuAgentException):
    """Raised when all retries are exhausted."""
    
    def __init__(
        self,
        message: str,
        attempts: int,
        last_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, details)
        self.attempts = attempts
        self.last_error = last_error


class MaxRetriesExceededError(RetryError):
    """Raised when maximum retries are exceeded."""
    pass


# Service Availability Errors
class ServiceUnavailableError(DataikuAgentException):
    """Raised when a service is unavailable."""
    pass


class HealthCheckError(ServiceUnavailableError):
    """Raised when health check fails."""
    pass


# Error helpers
def is_retryable(error: Exception) -> bool:
    """
    Check if an error is retryable.
    
    Args:
        error: The exception to check
        
    Returns:
        True if the error is retryable, False otherwise
    """
    retryable_errors = (
        RateLimitError,
        ServiceUnavailableError,
        CacheConnectionError,
    )
    
    # Check if it's a retryable error type
    if isinstance(error, retryable_errors):
        return True
    
    # Check for specific HTTP status codes
    if isinstance(error, ExternalAPIError):
        if error.status_code in (429, 500, 502, 503, 504):
            return True
    
    return False


def get_retry_after(error: Exception) -> Optional[int]:
    """
    Get retry-after value from error if available.
    
    Args:
        error: The exception to check
        
    Returns:
        Retry-after value in seconds, or None
    """
    if isinstance(error, RateLimitError):
        return error.retry_after
    
    return None 