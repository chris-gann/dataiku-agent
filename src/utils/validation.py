"""
Input validation and sanitization utilities.

This module provides functions to validate and sanitize user input
to prevent security issues and ensure data integrity.
"""
import re
import html
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from ..core.exceptions import (
    ValidationError,
    MessageTooLongError,
    EmptyQueryError,
    InvalidChannelError,
    BlockedUserError,
)
from ..core.config import SecurityConfig
from ..core.logging import get_logger

logger = get_logger(__name__)

# Regex patterns
URL_PATTERN = re.compile(
    r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}'
    r'\b[-a-zA-Z0-9()@:%_\+.~#?&/=]*'
)

EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)

SLACK_USER_ID_PATTERN = re.compile(r'^U[A-Z0-9]{8,}$')
SLACK_CHANNEL_ID_PATTERN = re.compile(r'^[CDG][A-Z0-9]{8,}$')
SLACK_WORKSPACE_ID_PATTERN = re.compile(r'^T[A-Z0-9]{8,}$')

# Dangerous patterns to block
SQL_INJECTION_PATTERNS = [
    r'(\b(union|select|insert|update|delete|drop|create|alter|exec|execute)\b.*\b(from|where|table|database)\b)',
    r'(\'|\"|;|--|\*|/\*|\*/|xp_|sp_)',
    r'(\b(and|or)\b.*=.*)',
]

XSS_PATTERNS = [
    r'<script[^>]*>.*?</script>',
    r'javascript:',
    r'on\w+\s*=',
    r'<iframe[^>]*>',
    r'<object[^>]*>',
    r'<embed[^>]*>',
]


def sanitize_input(text: str, max_length: Optional[int] = None) -> str:
    """
    Sanitize user input to prevent XSS and other attacks.
    
    Args:
        text: The input text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text
        
    Raises:
        MessageTooLongError: If text exceeds max_length
    """
    if not text:
        return ""
    
    # Trim whitespace
    text = text.strip()
    
    # Check length
    if max_length and len(text) > max_length:
        raise MessageTooLongError(
            f"Message exceeds maximum length of {max_length} characters",
            max_length=max_length,
            actual_length=len(text)
        )
    
    # HTML escape
    text = html.escape(text)
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Normalize whitespace
    text = ' '.join(text.split())
    
    return text


def validate_message(
    message: Dict[str, Any],
    security_config: SecurityConfig
) -> Dict[str, Any]:
    """
    Validate a Slack message.
    
    Args:
        message: The message dictionary from Slack
        security_config: Security configuration
        
    Returns:
        Validated message data
        
    Raises:
        ValidationError: If validation fails
        EmptyQueryError: If message text is empty
        MessageTooLongError: If message is too long
        BlockedUserError: If user is blocked
    """
    # Extract message data
    text = message.get("text", "").strip()
    user_id = message.get("user", "")
    channel_id = message.get("channel", "")
    
    # Check if message is empty
    if not text:
        raise EmptyQueryError("Message text is empty")
    
    # Validate user ID format
    if not SLACK_USER_ID_PATTERN.match(user_id):
        raise ValidationError(f"Invalid Slack user ID format: {user_id}")
    
    # Check if user is blocked
    if user_id in security_config.blocked_users:
        raise BlockedUserError(f"User {user_id} is blocked")
    
    # Sanitize and validate message text
    try:
        sanitized_text = sanitize_input(text, security_config.max_message_length)
    except MessageTooLongError:
        raise
    
    # Check for malicious patterns
    if _contains_malicious_patterns(text):
        logger.warning(
            "malicious_pattern_detected",
            user_id=user_id,
            channel_id=channel_id,
            text_preview=text[:50],
        )
        raise ValidationError("Message contains potentially malicious content")
    
    return {
        "text": sanitized_text,
        "user_id": user_id,
        "channel_id": channel_id,
        "original_text": text,
    }


def validate_channel(
    channel_id: str,
    security_config: SecurityConfig
) -> bool:
    """
    Validate if a channel is allowed.
    
    Args:
        channel_id: The Slack channel ID
        security_config: Security configuration
        
    Returns:
        True if channel is allowed
        
    Raises:
        InvalidChannelError: If channel is not allowed
    """
    # Validate channel ID format
    if not SLACK_CHANNEL_ID_PATTERN.match(channel_id):
        raise InvalidChannelError(f"Invalid Slack channel ID format: {channel_id}")
    
    # Check allowed channels regex if configured
    if security_config.allowed_channels_regex:
        pattern = re.compile(security_config.allowed_channels_regex)
        if not pattern.match(channel_id):
            raise InvalidChannelError(
                f"Channel {channel_id} is not in allowed channels list"
            )
    
    return True


def validate_url(url: str) -> bool:
    """
    Validate if a URL is safe.
    
    Args:
        url: The URL to validate
        
    Returns:
        True if URL is valid and safe
    """
    if not url:
        return False
    
    # Check URL format
    if not URL_PATTERN.match(url):
        return False
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    
    # Check scheme
    if parsed.scheme not in ('http', 'https'):
        return False
    
    # Check for localhost/private IPs
    hostname = parsed.hostname
    if hostname:
        if hostname in ('localhost', '127.0.0.1', '0.0.0.0'):
            return False
        
        # Check for private IP ranges
        if _is_private_ip(hostname):
            return False
    
    return True


def validate_api_response(response: Dict[str, Any], expected_fields: List[str]) -> bool:
    """
    Validate API response structure.
    
    Args:
        response: The API response
        expected_fields: List of expected fields
        
    Returns:
        True if response is valid
        
    Raises:
        ValidationError: If response is invalid
    """
    if not isinstance(response, dict):
        raise ValidationError("API response is not a dictionary")
    
    # Check for expected fields
    missing_fields = [field for field in expected_fields if field not in response]
    if missing_fields:
        raise ValidationError(f"Missing required fields: {missing_fields}")
    
    return True


def _contains_malicious_patterns(text: str) -> bool:
    """
    Check if text contains malicious patterns.
    
    Args:
        text: The text to check
        
    Returns:
        True if malicious patterns are found
    """
    text_lower = text.lower()
    
    # Check SQL injection patterns
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    # Check XSS patterns
    for pattern in XSS_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    return False


def _is_private_ip(hostname: str) -> bool:
    """
    Check if hostname is a private IP address.
    
    Args:
        hostname: The hostname to check
        
    Returns:
        True if hostname is a private IP
    """
    import ipaddress
    
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_reserved or ip.is_loopback
    except ValueError:
        # Not an IP address
        return False


def validate_search_query(query: str) -> str:
    """
    Validate and sanitize search query.
    
    Args:
        query: The search query
        
    Returns:
        Sanitized query
        
    Raises:
        ValidationError: If query is invalid
    """
    if not query:
        raise ValidationError("Search query cannot be empty")
    
    # Remove excessive whitespace
    query = ' '.join(query.split())
    
    # Check length
    if len(query) > 500:
        raise ValidationError("Search query is too long")
    
    # Remove special characters that might break search
    query = re.sub(r'[<>\"\'`]', '', query)
    
    # Check for remaining content
    if not query.strip():
        raise ValidationError("Search query contains only special characters")
    
    return query


class InputValidator:
    """
    Helper class for validating multiple inputs.
    """
    
    def __init__(self, security_config: SecurityConfig):
        self.security_config = security_config
        self.errors: List[str] = []
    
    def validate(self, validations: List[tuple]) -> bool:
        """
        Run multiple validations.
        
        Args:
            validations: List of (validation_func, args, error_message) tuples
            
        Returns:
            True if all validations pass
        """
        self.errors.clear()
        
        for validation_func, args, error_message in validations:
            try:
                if not validation_func(*args):
                    self.errors.append(error_message)
            except Exception as e:
                self.errors.append(f"{error_message}: {str(e)}")
        
        return len(self.errors) == 0
    
    def get_errors(self) -> List[str]:
        """Get list of validation errors."""
        return self.errors.copy() 