import os
import logging
import time
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from openai import OpenAI
from slack_bolt import App, Assistant, BoltContext
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import structlog

# Load environment variables
load_dotenv()

# Configure structured logging
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

logger = structlog.get_logger()

# Configuration
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")

# o4-mini reasoning effort level: "low", "medium", or "high"
# Higher effort = better reasoning but higher cost and latency
O3_REASONING_EFFORT = os.environ.get("O3_REASONING_EFFORT", "medium")

# Validate required environment variables
if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, OPENAI_API_KEY, BRAVE_API_KEY]):
    logger.error("Missing required environment variables")
    missing = []
    if not SLACK_BOT_TOKEN: missing.append("SLACK_BOT_TOKEN")
    if not SLACK_APP_TOKEN: missing.append("SLACK_APP_TOKEN")
    if not OPENAI_API_KEY: missing.append("OPENAI_API_KEY")
    if not BRAVE_API_KEY: missing.append("BRAVE_API_KEY")
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# Initialize Slack app with assistant
app = App(token=SLACK_BOT_TOKEN)
assistant = Assistant()

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Brave Search configuration
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_HEADERS = {
    "Accept": "application/json",
    "X-Subscription-Token": BRAVE_API_KEY
}

# Suggested prompts for the assistant
SUGGESTED_PROMPTS = [
    "How to schedule a scenario in Dataiku?",
    "What is a recipe in Dataiku?",
    "Where to find plugins in Dataiku?"
]

# System prompt for OpenAI
SYSTEM_PROMPT = """You are a helpful Dataiku expert assistant. You provide accurate, concise answers based on the search results provided.

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


def search_brave(query: str) -> List[Dict[str, Any]]:
    """
    Search Brave for the given query and return top results.
    
    Args:
        query: The search query
        
    Returns:
        List of search results with title, snippet, and URL
    """
    start_time = time.time()
    try:
        params = {
            "q": f"{query} Dataiku",  # Add Dataiku to focus results
            "count": 10,
            "source": "web",
            "ai": "true"
        }
        
        response = requests.get(
            BRAVE_SEARCH_URL,
            headers=BRAVE_HEADERS,
            params=params,
            timeout=5
        )
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        # Extract web results
        for result in data.get("web", {}).get("results", [])[:10]:
            results.append({
                "title": result.get("title", ""),
                "snippet": result.get("description", ""),
                "url": result.get("url", "")
            })
        
        logger.info(
            "brave_search_completed",
            query=query,
            result_count=len(results),
            duration_ms=int((time.time() - start_time) * 1000)
        )
        
        return results
        
    except requests.exceptions.RequestException as e:
        logger.error("brave_search_failed", error=str(e), query=query)
        raise


def synthesize_answer(query: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Use OpenAI to synthesize an answer from search results.
    
    Args:
        query: The user's question
        search_results: List of search results from Brave
        
    Returns:
        Synthesized answer from OpenAI
    """
    start_time = time.time()
    
    # Build context from search results
    context_parts = []
    for i, result in enumerate(search_results, 1):
        context_parts.append(f"Result {i}:")
        context_parts.append(f"Title: {result['title']}")
        context_parts.append(f"Content: {result['snippet']}")
        context_parts.append(f"URL: {result['url']}")
        context_parts.append("")
    
    context = "\n".join(context_parts)
    
    # Create the user message with context
    user_message = f"""Based on the following search results, please answer this question: {query}

Search Results:
{context}

Please provide a helpful, accurate answer based on these search results. Include relevant URLs from the search results naturally within your response text. Format your response using Slack mrkdwn formatting for better readability."""

    try:
        logger.info("calling_openai_o4_mini", model="o4-mini", reasoning_effort=O3_REASONING_EFFORT)
        
        response = openai_client.chat.completions.create(
            model="o4-mini",  # Using OpenAI's o4-mini reasoning model
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            max_completion_tokens=1500,  # o4-mini uses max_completion_tokens like o3
            # o4-mini supports reasoning effort levels: low, medium, high
            reasoning_effort=O3_REASONING_EFFORT
        )
        
        answer = response.choices[0].message.content
        
        logger.info(
            "openai_synthesis_completed",
            query=query,
            duration_ms=int((time.time() - start_time) * 1000),
            tokens_used=response.usage.total_tokens if response.usage else 0,
            answer_preview=answer[:100] if answer else "None"
        )
        
        return answer
        
    except Exception as e:
        logger.error("openai_o4_mini_failed", error=str(e), query=query, error_type=type(e).__name__)
        return None


def format_urls_as_numbered_links(text: str) -> str:
    """
    Replace URLs in text with numbered Slack-formatted hyperlinks.
    
    Args:
        text: The input text containing URLs
        
    Returns:
        Text with URLs replaced by numbered links like [1], [2], etc.
    """
    # Pattern to match plain URLs (not already in Slack format)
    # This pattern avoids matching URLs that are already in <URL|text> format
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
        # Create Slack-formatted link: <url|[number]>
        slack_link = f"<{url}|[{i}]>"
        # Replace all occurrences of this URL
        result = result.replace(url, slack_link)
    
    return result


def format_response_with_sources(answer: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Format the response with Slack formatting and numbered URL links.
    
    Args:
        answer: The synthesized answer
        search_results: The search results (not used but kept for compatibility)
        
    Returns:
        Slack-formatted answer with numbered URL links
    """
    if not answer:
        return answer
    
    # Fix double asterisks to single asterisks for proper Slack bold formatting
    # Replace **text** with *text* (but not if already single asterisks)
    formatted_answer = re.sub(r'\*\*([^\*]+?)\*\*', r'*\1*', answer)
    
    # Format URLs as numbered links
    formatted_answer = format_urls_as_numbered_links(formatted_answer)
    
    return formatted_answer


@assistant.thread_started
def handle_thread_started(context: BoltContext, client: WebClient, payload: dict):
    """
    Handle when a new assistant thread is started.
    Set suggested prompts for the user.
    """
    try:
        thread_context = payload.get("assistant_thread", {}).get("context", {})
        channel_id = thread_context.get("channel_id")
        thread_ts = thread_context.get("thread_ts")
        
        if channel_id and thread_ts:
            # Set suggested prompts
            client.assistant_threads_setSuggestedPrompts(
                channel_id=channel_id,
                thread_ts=thread_ts,
                prompts=[{"title": prompt, "message": prompt} for prompt in SUGGESTED_PROMPTS]
            )
            
            logger.info(
                "thread_started",
                channel_id=channel_id,
                thread_ts=thread_ts
            )
            
    except SlackApiError as e:
        logger.error("failed_to_set_suggested_prompts", error=str(e))


@assistant.user_message
def handle_user_message(message, context: BoltContext, client: WebClient):
    """
    Handle user messages in assistant threads.
    This is where we process user messages and generate responses.
    """
    start_time = time.time()
    
    try:
        user_query = message.get("text", "").strip()
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts")
        
        if not user_query:
            logger.warning("empty_user_query", message=message)
            return
            
        logger.info("processing_user_message", query=user_query, channel=channel_id)
        
        # Set status to "Searching the web..."
        client.assistant_threads_setStatus(
            channel_id=channel_id,
            thread_ts=thread_ts,
            status="Searching the web..."
        )
        
        try:
            # Search Brave
            search_results = search_brave(user_query)
            
            if not search_results:
                # No results found
                response = "I couldn't find any relevant information about your query. Please try rephrasing your question or asking about a different aspect of Dataiku."
            else:
                # Update status
                client.assistant_threads_setStatus(
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    status="Analyzing results..."
                )
                
                # Synthesize answer with better error handling
                answer = synthesize_answer(user_query, search_results)
                
                # Ensure we have an answer
                if not answer or len(answer.strip()) == 0:
                    logger.warning("empty_answer_from_synthesis")
                    answer = "I found some relevant information about your query. Here are the sources I found:"
                
                # Format with sources
                response = format_response_with_sources(answer, search_results)
            
            # Post the response
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=response,
                mrkdwn=True,
                unfurl_links=False,  # Disable automatic link previews
                unfurl_media=False   # Disable automatic media previews
            )
            
            # Clear status
            client.assistant_threads_setStatus(
                channel_id=channel_id,
                thread_ts=thread_ts,
                status=""
            )
            
            # Log success
            logger.info(
                "query_processed",
                query=user_query,
                total_duration_ms=int((time.time() - start_time) * 1000),
                result_count=len(search_results) if search_results else 0
            )
            
        except requests.exceptions.RequestException:
            # Brave API error
            error_msg = "I'm having trouble searching the web right now. Please try again in a moment."
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=error_msg,
                unfurl_links=False,
                unfurl_media=False
            )
            client.assistant_threads_setStatus(
                channel_id=channel_id,
                thread_ts=thread_ts,
                status=""
            )
            
        except Exception as e:
            # OpenAI or other error
            logger.error("query_processing_failed", error=str(e), query=user_query)
            error_msg = "I encountered an error while processing your request. Please try again."
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=error_msg,
                unfurl_links=False,
                unfurl_media=False
            )
            client.assistant_threads_setStatus(
                channel_id=channel_id,
                thread_ts=thread_ts,
                status=""
            )
            
    except SlackApiError as e:
        logger.error("slack_api_error", error=str(e))


@assistant.thread_context_changed
def handle_thread_context_changed(context: BoltContext, client: WebClient, payload: dict):
    """
    Handle when the context changes in an assistant thread.
    This is used for tracking context changes, not for processing messages.
    """
    try:
        thread_context = payload.get("assistant_thread", {}).get("context", {})
        channel_id = thread_context.get("channel_id")
        thread_ts = thread_context.get("thread_ts")
        
        logger.info(
            "thread_context_changed",
            channel_id=channel_id,
            thread_ts=thread_ts
        )
        
    except Exception as e:
        logger.error("thread_context_changed_error", error=str(e))


# Add the assistant to the app
app.assistant(assistant)

# Health check endpoint for Cloud Run
@app.route("/health")
def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Handle regular messages (fallback)
@app.message("")
def handle_message(message, say):
    """
    Handle regular messages outside of assistant threads.
    This is a fallback for direct messages.
    """
    if message.get("channel_type") == "im":
        say(
            text="Hi! I'm the Dataiku Agent. To get started, please use the AI assistant feature by clicking the ⚡ button or mentioning me in a channel.",
            thread_ts=message.get("thread_ts"),
            unfurl_links=False,
            unfurl_media=False
        )


def main():
    """Main entry point for the application."""
    logger.info("starting_dataiku_agent", 
                bot_token_present=bool(SLACK_BOT_TOKEN),
                app_token_present=bool(SLACK_APP_TOKEN))
    
    # Start the app with Socket Mode
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    
    logger.info("dataiku_agent_ready")
    handler.start()


if __name__ == "__main__":
    main() 