"""
Dataiku Assistant for Slack.

This module provides the main assistant class that integrates
all components and handles the Slack assistant functionality.
"""
from typing import Optional

from slack_bolt import App, Assistant, BoltContext
from slack_sdk import WebClient

from ..core.config import Config
from ..core.logging import get_logger
from ..services import BraveSearchService, OpenAIService, CacheService
from .slack_handlers import SlackHandlers

logger = get_logger(__name__)


class DataikuAssistant:
    """Main assistant class that manages all components."""
    
    def __init__(self, config: Config):
        self.config = config
        
        # Initialize services
        self.brave_service = BraveSearchService(config.brave_search)
        self.openai_service = OpenAIService(config.openai)
        self.cache_service = CacheService(config.cache)
        
        # Initialize Slack app
        self.app = App(token=config.slack.bot_token.get_secret_value())
        
        # Initialize assistant
        self.assistant = Assistant()
        
        # Initialize handlers
        self.handlers = SlackHandlers(
            config,
            self.brave_service,
            self.openai_service,
            self.cache_service,
        )
        
        # Set up event handlers
        self._setup_event_handlers()
        
        # Add assistant to app
        self.app.assistant(self.assistant)
        
        logger.info(
            "dataiku_assistant_initialized",
            app_name=config.app_name,
            environment=config.environment.value,
            cache_enabled=config.cache.enabled,
            cache_backend=config.cache.backend,
        )
    
    def _setup_event_handlers(self):
        """Set up all event handlers for the assistant."""
        # Thread started event
        @self.assistant.thread_started
        def handle_thread_started(context: BoltContext, client: WebClient, payload: dict):
            self.handlers.handle_thread_started(context, client, payload)
        
        # User message event
        @self.assistant.user_message
        def handle_user_message(message: dict, context: BoltContext, client: WebClient):
            self.handlers.handle_user_message(message, context, client)
        
        # Thread context changed event
        @self.assistant.thread_context_changed
        def handle_thread_context_changed(context: BoltContext, client: WebClient, payload: dict):
            self.handlers.handle_thread_context_changed(context, client, payload)
        
        # Regular messages (fallback for DMs)
        @self.app.message("")
        def handle_regular_message(message: dict, say):
            """Handle regular messages outside of assistant threads."""
            if message.get("channel_type") == "im":
                say(
                    text=(
                        "Hi! I'm the Dataiku Agent. To get started, please use "
                        "the AI assistant feature by clicking the ⚡ button or "
                        "mentioning me in a channel."
                    ),
                    thread_ts=message.get("thread_ts"),
                    unfurl_links=False,
                    unfurl_media=False,
                )
    
    def test_connections(self) -> dict:
        """
        Test all service connections.
        
        Returns:
            Dictionary with connection status for each service
        """
        results = {
            "brave_search": False,
            "openai": False,
            "cache": False,
        }
        
        # Test Brave Search
        try:
            self.brave_service.test_connection()
            results["brave_search"] = True
        except Exception as e:
            logger.error("brave_search_connection_test_failed", error=str(e))
        
        # Test OpenAI
        try:
            self.openai_service.test_connection()
            results["openai"] = True
        except Exception as e:
            logger.error("openai_connection_test_failed", error=str(e))
        
        # Test cache
        results["cache"] = self.cache_service.health_check()
        
        return results
    
    def get_metrics(self) -> dict:
        """
        Get current metrics from all services.
        
        Returns:
            Dictionary with metrics from each service
        """
        return {
            "openai_token_usage": self.openai_service.get_token_usage(),
            "cache_stats": self.cache_service.get_stats(),
        }
    
    def cleanup(self):
        """Clean up resources."""
        try:
            # Close Brave Search session
            self.brave_service.close()
            
            logger.info("dataiku_assistant_cleanup_completed")
        except Exception as e:
            logger.error("dataiku_assistant_cleanup_failed", error=str(e)) 