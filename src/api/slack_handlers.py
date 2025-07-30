"""
Slack event handlers for Dataiku Agent.

This module handles all Slack events and messages with proper
validation, rate limiting, and error handling.
"""
import re
from typing import Dict, Any, List, Optional

from slack_bolt import BoltContext
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..core.config import Config
from ..core.exceptions import (
    ValidationError,
    EmptyQueryError,
    InvalidChannelError,
    BlockedUserError,
    SlackAPIError,
)
from ..core.logging import get_logger, LogContext
from ..utils.validation import validate_message, validate_channel
from ..utils.rate_limiter import RateLimiter, RateLimitConfig
from ..services import BraveSearchService, OpenAIService, CacheService

logger = get_logger(__name__)

# Suggested prompts for the assistant
SUGGESTED_PROMPTS = [
    {
        "title": "Schedule a scenario",
        "message": "How do I schedule a scenario to run daily in Dataiku?"
    },
    {
        "title": "What is a recipe?",
        "message": "What is a recipe in Dataiku and how do I create one?"
    },
    {
        "title": "Find plugins",
        "message": "Where can I find and install plugins in Dataiku?"
    },
    {
        "title": "Connect to database",
        "message": "How do I connect Dataiku to a PostgreSQL database?"
    },
    {
        "title": "Create a dashboard",
        "message": "How can I create a dashboard in Dataiku?"
    },
]


class SlackHandlers:
    """Handles Slack events and messages."""
    
    def __init__(
        self,
        config: Config,
        brave_service: BraveSearchService,
        openai_service: OpenAIService,
        cache_service: CacheService,
    ):
        self.config = config
        self.brave_service = brave_service
        self.openai_service = openai_service
        self.cache_service = cache_service
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            RateLimitConfig(
                max_requests=config.slack.rate_limit_per_minute,
                window_seconds=60,
                burst_size=config.slack.rate_limit_burst,
            )
        )
    
    def handle_thread_started(
        self,
        context: BoltContext,
        client: WebClient,
        payload: dict
    ) -> None:
        """
        Handle when a new assistant thread is started.
        Set suggested prompts for the user.
        """
        try:
            thread_context = payload.get("assistant_thread", {}).get("context", {})
            channel_id = thread_context.get("channel_id")
            thread_ts = thread_context.get("thread_ts")
            
            if not channel_id or not thread_ts:
                logger.warning("missing_thread_context", payload=payload)
                return
            
            # Set suggested prompts if enabled
            if self.config.features.enable_suggested_prompts:
                try:
                    client.assistant_threads_setSuggestedPrompts(
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        prompts=SUGGESTED_PROMPTS[:3],  # Show top 3
                    )
                except SlackApiError as e:
                    logger.error(
                        "failed_to_set_suggested_prompts",
                        error=str(e),
                        error_code=e.response.get("error"),
                    )
            
            logger.info(
                "thread_started",
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=thread_context.get("user_id"),
            )
            
        except Exception as e:
            logger.error(
                "thread_started_handler_error",
                error=str(e),
                error_type=type(e).__name__,
            )
    
    def handle_user_message(
        self,
        message: Dict[str, Any],
        context: BoltContext,
        client: WebClient,
    ) -> None:
        """
        Handle user messages in assistant threads.
        This is where we process queries and generate responses.
        """
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts")
        user_id = message.get("user")
        
        # Create log context for this request
        with LogContext(
            logger,
            channel_id=channel_id,
            thread_ts=thread_ts,
            user_id=user_id,
        ):
            try:
                # Validate message
                validated_data = validate_message(message, self.config.security)
                
                # Validate channel
                validate_channel(channel_id, self.config.security)
                
                # Check rate limit
                self.rate_limiter.acquire(user_id, wait=False)
                
                # Process the message
                self._process_user_query(
                    validated_data["text"],
                    channel_id,
                    thread_ts,
                    user_id,
                    client,
                )
                
            except (EmptyQueryError, ValidationError) as e:
                logger.warning("invalid_user_message", error=str(e))
                # Don't respond to invalid messages
                
            except (InvalidChannelError, BlockedUserError) as e:
                logger.warning("unauthorized_message", error=str(e))
                # Don't respond to unauthorized messages
                
            except Exception as e:
                logger.error(
                    "user_message_handler_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                
                # Send error message to user
                self._send_error_message(
                    client,
                    channel_id,
                    thread_ts,
                    "I encountered an error while processing your request. Please try again."
                )
    
    def _process_user_query(
        self,
        query: str,
        channel_id: str,
        thread_ts: str,
        user_id: str,
        client: WebClient,
    ) -> None:
        """Process the user's query and generate a response."""
        try:
            # Set initial status
            self._set_thread_status(client, channel_id, thread_ts, "Searching the web...")
            
            # Check cache for search results
            cached_results = self.cache_service.get_search_results(query, "Dataiku")
            
            if cached_results:
                search_results = cached_results
                logger.info("using_cached_search_results", query=query)
            else:
                # Search Brave
                search_results = self.brave_service.search_with_context(
                    query,
                    "Dataiku",
                    freshness="pm",  # Past month for recent content
                )
                
                # Cache the results
                self.cache_service.set_search_results(
                    query,
                    search_results,
                    "Dataiku",
                    ttl=3600,  # 1 hour
                )
            
            if not search_results:
                response = self._create_no_results_message(query)
            else:
                # Update status
                self._set_thread_status(client, channel_id, thread_ts, "Analyzing results...")
                
                # Check cache for synthesis
                results_hash = self.cache_service.hash_search_results(search_results)
                cached_synthesis = self.cache_service.get_synthesis(query, results_hash)
                
                if cached_synthesis:
                    answer = cached_synthesis
                    logger.info("using_cached_synthesis", query=query)
                else:
                    # Synthesize answer
                    answer = self.openai_service.synthesize_answer(query, search_results)
                    
                    # Cache the synthesis
                    self.cache_service.set_synthesis(
                        query,
                        results_hash,
                        answer,
                        ttl=3600,  # 1 hour
                    )
                
                # Format response
                response = self._format_response(answer, search_results)
            
            # Send response
            self._send_response(client, channel_id, thread_ts, response)
            
            # Clear status
            self._set_thread_status(client, channel_id, thread_ts, "")
            
            # Log success metrics
            logger.info(
                "query_processed_successfully",
                query=query,
                result_count=len(search_results) if search_results else 0,
                response_length=len(response),
            )
            
        except Exception as e:
            logger.error(
                "query_processing_failed",
                error=str(e),
                error_type=type(e).__name__,
                query=query,
            )
            
            # Clear status
            self._set_thread_status(client, channel_id, thread_ts, "")
            
            # Send appropriate error message
            if "rate_limit" in str(e).lower():
                error_msg = "I'm receiving too many requests right now. Please try again in a moment."
            elif "api" in str(e).lower():
                error_msg = "I'm having trouble accessing external services. Please try again later."
            else:
                error_msg = "I encountered an error while processing your request. Please try again."
            
            self._send_error_message(client, channel_id, thread_ts, error_msg)
    
    def _format_response(
        self,
        answer: str,
        search_results: List[Dict[str, Any]]
    ) -> str:
        """Format the response with proper Slack formatting."""
        if not answer:
            return self._create_no_results_message("")
        
        # Format URLs as numbered links
        formatted_answer = self._format_urls_as_numbered_links(answer)
        
        # Ensure proper Slack formatting
        formatted_answer = self.openai_service.format_for_slack(formatted_answer)
        
        # Add source citations if enabled
        if self.config.features.enable_source_citations:
            sources = self._extract_top_sources(
                search_results,
                self.config.features.max_sources_to_show
            )
            if sources:
                formatted_answer += "\n\n*Sources:*\n"
                for i, source in enumerate(sources, 1):
                    formatted_answer += f"{i}. {source['title']} - {source['domain']}\n"
        
        return formatted_answer
    
    def _format_urls_as_numbered_links(self, text: str) -> str:
        """Replace URLs in text with numbered Slack-formatted hyperlinks."""
        # Pattern to match plain URLs (not already in Slack format)
        url_pattern = r'(?<!<)https?://[^\s<>"\'`|]+[^\s<>"\'`|.,!?;)](?!\|)'
        
        # Find all URLs
        urls = re.findall(url_pattern, text)
        
        if not urls:
            return text
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        # Replace each unique URL with a numbered Slack link
        result = text
        for i, url in enumerate(unique_urls, 1):
            slack_link = f"<{url}|[{i}]>"
            result = result.replace(url, slack_link)
        
        return result
    
    def _extract_top_sources(
        self,
        search_results: List[Dict[str, Any]],
        max_sources: int
    ) -> List[Dict[str, str]]:
        """Extract top sources from search results."""
        sources = []
        
        for result in search_results[:max_sources]:
            if result.get("type") == "ai_summary":
                continue
            
            sources.append({
                "title": result.get("title", "Untitled"),
                "url": result.get("url", ""),
                "domain": result.get("domain", ""),
            })
        
        return sources
    
    def _create_no_results_message(self, query: str) -> str:
        """Create a message when no results are found."""
        return (
            "I couldn't find any relevant information about your query. "
            "Please try rephrasing your question or asking about a different "
            "aspect of Dataiku.\n\n"
            "*Tips for better results:*\n"
            "• Be specific about the Dataiku feature or component\n"
            "• Include version information if relevant\n"
            "• Try breaking complex questions into simpler parts"
        )
    
    def _set_thread_status(
        self,
        client: WebClient,
        channel_id: str,
        thread_ts: str,
        status: str
    ) -> None:
        """Set the thread status message."""
        try:
            client.assistant_threads_setStatus(
                channel_id=channel_id,
                thread_ts=thread_ts,
                status=status,
            )
        except SlackApiError as e:
            logger.warning(
                "failed_to_set_thread_status",
                error=str(e),
                status=status,
            )
    
    def _send_response(
        self,
        client: WebClient,
        channel_id: str,
        thread_ts: str,
        text: str
    ) -> None:
        """Send a response message."""
        try:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=text,
                mrkdwn=True,
                unfurl_links=False,
                unfurl_media=False,
            )
        except SlackApiError as e:
            logger.error(
                "failed_to_send_response",
                error=str(e),
                error_code=e.response.get("error"),
            )
            raise SlackAPIError(
                f"Failed to send response: {e.response.get('error')}",
                status_code=e.response.status_code,
            )
    
    def _send_error_message(
        self,
        client: WebClient,
        channel_id: str,
        thread_ts: str,
        error_message: str
    ) -> None:
        """Send an error message to the user."""
        try:
            self._send_response(client, channel_id, thread_ts, f"❌ {error_message}")
        except Exception as e:
            logger.error("failed_to_send_error_message", error=str(e))
    
    def handle_thread_context_changed(
        self,
        context: BoltContext,
        client: WebClient,
        payload: dict
    ) -> None:
        """Handle when the context changes in an assistant thread."""
        try:
            thread_context = payload.get("assistant_thread", {}).get("context", {})
            channel_id = thread_context.get("channel_id")
            thread_ts = thread_context.get("thread_ts")
            
            logger.info(
                "thread_context_changed",
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
            
        except Exception as e:
            logger.error(
                "thread_context_changed_error",
                error=str(e),
                error_type=type(e).__name__,
            ) 