"""
OpenAI API service.

This module provides a service for interacting with the OpenAI API
with proper error handling, retries, and prompt management.
"""
import asyncio
import time
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime

from openai import OpenAI, OpenAIError
from openai.types.chat import ChatCompletionMessage

from ..core.config import OpenAIConfig
from ..core.exceptions import (
    OpenAIAPIError,
    OpenAIRateLimitError,
    ValidationError,
)
from ..core.logging import get_logger, log_performance
from ..utils.retry import retry_with_backoff, RetryConfig

logger = get_logger(__name__)


class OpenAIService:
    """Service for interacting with OpenAI API."""
    
    # System prompts
    DATAIKU_EXPERT_PROMPT = """You are a helpful Dataiku expert assistant. You provide accurate, concise answers based on the search results provided.

Format your response using Slack's mrkdwn formatting:
- Use *bold* for important terms and headings (single asterisks, NOT double)
- Use _italic_ for emphasis (underscores)
- Use `code` for technical terms, file names, and UI elements (backticks)
- Use bullet points with • for lists
- Use numbered lists when showing steps (1. 2. 3.)
- Use > for quotes or important notes
- Keep paragraphs short and scannable

CRITICAL FORMATTING RULES:
- For bold text, use *single asterisks* NOT **double asterisks**
- When including URLs, write them as plain URLs (like https://example.com) - do NOT format them as links
- The system will automatically convert URLs to numbered clickable links

Focus on being helpful, clear, and accurate in your responses about Dataiku's features, capabilities, and usage."""
    
    def __init__(self, config: OpenAIConfig):
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key.get_secret_value(),
            max_retries=0,  # We handle retries ourselves
        )
        
        # Token tracking for cost estimation
        self._total_tokens_used = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
    
    @retry_with_backoff(
        max_attempts=3,
        retry_exceptions=(OpenAIError,),
    )
    @log_performance(logger, "openai_synthesis")
    def synthesize_answer(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Use OpenAI to synthesize an answer from search results.
        
        Args:
            query: The user's question
            search_results: List of search results to synthesize from
            system_prompt: Custom system prompt (defaults to DATAIKU_EXPERT_PROMPT)
            max_tokens: Maximum tokens for completion
            temperature: Temperature for response generation
            
        Returns:
            Synthesized answer
            
        Raises:
            OpenAIAPIError: If API returns an error
            OpenAIRateLimitError: If rate limit is exceeded
        """
        # Build context from search results
        context = self._build_context(search_results)
        
        # Create the user message
        user_message = self._create_synthesis_prompt(query, context)
        
        # Use provided or default system prompt
        if system_prompt is None:
            system_prompt = self.DATAIKU_EXPERT_PROMPT
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        logger.info(
            "openai_synthesis_request",
            model=self.config.model,
            reasoning_effort=self.config.reasoning_effort.value,
            query_preview=query[:100],
            context_length=len(context),
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_completion_tokens=max_tokens or self.config.max_completion_tokens,
                temperature=temperature or self.config.temperature,
                reasoning_effort=self.config.reasoning_effort.value,
            )
            
            # Extract answer
            answer = response.choices[0].message.content
            
            # Track token usage
            if response.usage:
                self._track_token_usage(response.usage)
            
            logger.info(
                "openai_synthesis_success",
                model=self.config.model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                answer_length=len(answer) if answer else 0,
            )
            
            return answer or "I couldn't generate a response. Please try again."
            
        except Exception as e:
            if "rate_limit_exceeded" in str(e).lower():
                # Extract retry-after if available
                retry_after = self._extract_retry_after(str(e))
                raise OpenAIRateLimitError(
                    "OpenAI API rate limit exceeded",
                    retry_after=retry_after,
                )
            
            logger.error(
                "openai_synthesis_error",
                error=str(e),
                error_type=type(e).__name__,
                model=self.config.model,
            )
            
            raise OpenAIAPIError(
                f"OpenAI API error: {str(e)}",
                details={"model": self.config.model, "error": str(e)}
            )
    
    def _build_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Build context string from search results."""
        context_parts = []
        
        for i, result in enumerate(search_results, 1):
            # Skip AI summary results
            if result.get("type") == "ai_summary":
                continue
            
            context_parts.append(f"Result {i}:")
            context_parts.append(f"Title: {result.get('title', 'N/A')}")
            context_parts.append(f"Content: {result.get('snippet', 'N/A')}")
            context_parts.append(f"URL: {result.get('url', 'N/A')}")
            
            # Add extra snippets if available
            if "extra_snippets" in result:
                for snippet in result["extra_snippets"][:2]:
                    context_parts.append(f"Additional info: {snippet}")
            
            context_parts.append("")  # Empty line between results
        
        return "\n".join(context_parts)
    
    def _create_synthesis_prompt(self, query: str, context: str) -> str:
        """Create the synthesis prompt for OpenAI."""
        return f"""Based on the following search results, please answer this question: {query}

Search Results:
{context}

Please provide a helpful, accurate answer based on these search results. Include relevant URLs from the search results naturally within your response text. Format your response using Slack mrkdwn formatting for better readability."""
    
    def _track_token_usage(self, usage: Any) -> None:
        """Track token usage for cost estimation."""
        self._total_tokens_used += usage.total_tokens
        self._total_prompt_tokens += usage.prompt_tokens
        self._total_completion_tokens += usage.completion_tokens
    
    def _extract_retry_after(self, error_message: str) -> Optional[int]:
        """Extract retry-after value from error message."""
        import re
        
        # Try to extract seconds from error message
        match = re.search(r'retry after (\d+) seconds', error_message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Default to 60 seconds if not found
        return 60
    
    def get_token_usage(self) -> Dict[str, int]:
        """
        Get current token usage statistics.
        
        Returns:
            Dictionary with token usage data
        """
        return {
            "total_tokens": self._total_tokens_used,
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens,
            "estimated_cost_usd": self._estimate_cost(),
        }
    
    def _estimate_cost(self) -> float:
        """Estimate cost based on token usage."""
        # Pricing for o4-mini (as of the model's release)
        # $1.10 per 1M input tokens, $4.40 per 1M output tokens
        input_cost = (self._total_prompt_tokens / 1_000_000) * 1.10
        output_cost = (self._total_completion_tokens / 1_000_000) * 4.40
        
        return round(input_cost + output_cost, 4)
    
    def test_connection(self) -> bool:
        """
        Test if the OpenAI API is accessible.
        
        Returns:
            True if API is accessible
            
        Raises:
            OpenAIAPIError: If connection test fails
        """
        try:
            # Make a minimal completion request
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "You are a test assistant."},
                    {"role": "user", "content": "Reply with 'OK'"}
                ],
                max_completion_tokens=10,
                reasoning_effort="low",  # Use low effort for testing
            )
            
            return bool(response.choices)
            
        except Exception as e:
            logger.error("openai_connection_test_failed", error=str(e))
            raise OpenAIAPIError(f"Connection test failed: {str(e)}")
    
    async def synthesize_answer_stream(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream the synthesis response.
        
        Note: This is a placeholder for future streaming support.
        o4-mini doesn't support streaming yet, so this simulates it.
        
        Args:
            Same as synthesize_answer
            
        Yields:
            Response chunks
        """
        # Get the full response
        full_response = self.synthesize_answer(
            query,
            search_results,
            system_prompt,
            max_tokens,
            temperature,
        )
        
        # Simulate streaming by yielding chunks
        chunk_size = 50
        for i in range(0, len(full_response), chunk_size):
            yield full_response[i:i + chunk_size]
            await asyncio.sleep(0.05)  # Small delay to simulate streaming
    
    def format_for_slack(self, text: str) -> str:
        """
        Ensure text is properly formatted for Slack.
        
        Args:
            text: The text to format
            
        Returns:
            Slack-formatted text
        """
        import re
        
        # Fix double asterisks to single asterisks
        text = re.sub(r'\*\*([^\*]+?)\*\*', r'*\1*', text)
        
        # Ensure code blocks are properly formatted
        text = re.sub(r'```(\w+)?\n', r'```\n', text)
        
        return text 