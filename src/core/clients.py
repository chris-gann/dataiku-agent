"""
Lazy-loaded client management for OpenAI, Slack, and structured logging.

Provides singleton clients that are initialized only when first accessed.
"""

import structlog
from .config import OPENAI_API_KEY, SLACK_BOT_TOKEN

# Global client instances (lazy-loaded)
_openai_client = None
_slack_client = None
_structlog_configured = False

def get_openai_client():
    """Get or create the OpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client

def get_slack_client():
    """Get or create the Slack WebClient."""
    global _slack_client
    if _slack_client is None:
        from slack_sdk import WebClient
        _slack_client = WebClient(token=SLACK_BOT_TOKEN)
    return _slack_client

def get_logger():
    """Get or configure structured logging."""
    global _structlog_configured
    if not _structlog_configured:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
        _structlog_configured = True
    return structlog.get_logger()