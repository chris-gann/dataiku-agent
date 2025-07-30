"""
Pytest configuration and fixtures for Dataiku Agent tests.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

from src.core import Config, Environment
from src.core.config import (
    SlackConfig,
    OpenAIConfig,
    BraveSearchConfig,
    CacheConfig,
    SecurityConfig,
    FeatureFlags,
)


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return Config(
        environment=Environment.TEST,
        debug=True,
        app_name="Dataiku Agent Test",
        app_version="test",
        slack=SlackConfig(
            bot_token="xoxb-test-token",
            app_token="xapp-test-token",
            rate_limit_per_minute=60,
            rate_limit_burst=10,
        ),
        openai=OpenAIConfig(
            api_key="sk-test-key",
            model="gpt-4",  # Use GPT-4 for tests since o4-mini might not be available
            max_completion_tokens=100,
        ),
        brave_search=BraveSearchConfig(
            api_key="test-brave-key",
            result_count=5,
        ),
        cache=CacheConfig(
            enabled=True,
            backend="memory",
        ),
        security=SecurityConfig(
            max_message_length=1000,
            verify_slack_signatures=False,  # Disable for tests
        ),
        features=FeatureFlags(
            enable_suggested_prompts=True,
            enable_source_citations=True,
        ),
        data_dir=Path("/tmp/dataiku-agent-test/data"),
        log_dir=Path("/tmp/dataiku-agent-test/logs"),
    )


@pytest.fixture
def mock_slack_client():
    """Create a mock Slack WebClient."""
    client = MagicMock()
    client.assistant_threads_setSuggestedPrompts = MagicMock(return_value={"ok": True})
    client.assistant_threads_setStatus = MagicMock(return_value={"ok": True})
    client.chat_postMessage = MagicMock(return_value={"ok": True, "ts": "1234567890.123456"})
    return client


@pytest.fixture
def mock_brave_service():
    """Create a mock BraveSearchService."""
    service = MagicMock()
    service.search_with_context = MagicMock(return_value=[
        {
            "title": "Test Result 1",
            "snippet": "This is a test search result about Dataiku",
            "url": "https://example.com/1",
            "domain": "example.com",
        },
        {
            "title": "Test Result 2",
            "snippet": "Another test result",
            "url": "https://example.com/2",
            "domain": "example.com",
        }
    ])
    service.test_connection = MagicMock(return_value=True)
    return service


@pytest.fixture
def mock_openai_service():
    """Create a mock OpenAIService."""
    service = MagicMock()
    service.synthesize_answer = MagicMock(
        return_value="This is a test answer about Dataiku. You can find more at https://example.com"
    )
    service.format_for_slack = MagicMock(side_effect=lambda x: x)
    service.test_connection = MagicMock(return_value=True)
    service.get_token_usage = MagicMock(return_value={
        "total_tokens": 100,
        "prompt_tokens": 50,
        "completion_tokens": 50,
        "estimated_cost_usd": 0.01,
    })
    return service


@pytest.fixture
def mock_cache_service():
    """Create a mock CacheService."""
    service = MagicMock()
    service.get_search_results = MagicMock(return_value=None)
    service.set_search_results = MagicMock(return_value=True)
    service.get_synthesis = MagicMock(return_value=None)
    service.set_synthesis = MagicMock(return_value=True)
    service.hash_search_results = MagicMock(return_value="test-hash")
    service.health_check = MagicMock(return_value=True)
    service.get_stats = MagicMock(return_value={
        "enabled": True,
        "backend": "memory",
        "healthy": True,
        "entries": 0,
    })
    return service


@pytest.fixture
def sample_slack_message():
    """Create a sample Slack message."""
    return {
        "type": "message",
        "text": "How do I create a recipe in Dataiku?",
        "user": "U1234567890",
        "channel": "C1234567890",
        "thread_ts": "1234567890.123456",
        "ts": "1234567890.123456",
    }


@pytest.fixture
def sample_assistant_payload():
    """Create a sample assistant thread payload."""
    return {
        "assistant_thread": {
            "context": {
                "channel_id": "C1234567890",
                "thread_ts": "1234567890.123456",
                "user_id": "U1234567890",
            }
        }
    } 