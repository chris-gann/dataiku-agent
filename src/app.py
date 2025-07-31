import os
import logging
import time
import json
import re
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from openai import OpenAI
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import structlog
from flask import Flask, jsonify, request

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

# Configuration (strip whitespace from secrets)
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "").strip()

# AI Model configuration  
# Using o4-mini reasoning model for better quality responses
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "medium")

# Validate required environment variables (no longer need SLACK_APP_TOKEN for HTTP mode)
if not all([SLACK_BOT_TOKEN, OPENAI_API_KEY, BRAVE_API_KEY]):
    logger.error("Missing required environment variables")
    missing = []
    if not SLACK_BOT_TOKEN: missing.append("SLACK_BOT_TOKEN")
    if not OPENAI_API_KEY: missing.append("OPENAI_API_KEY")
    if not BRAVE_API_KEY: missing.append("BRAVE_API_KEY")
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# HTTP mode - no longer need Slack Bolt app

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Brave Search configuration
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_HEADERS = {
    "Accept": "application/json",
    "X-Subscription-Token": BRAVE_API_KEY
}

# HTTP mode - no longer need suggested prompts

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
            "count": 5,  # Reduced from 10 to 5 for faster processing
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
        for result in data.get("web", {}).get("results", [])[:5]:
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
        logger.info("calling_openai_o4_mini", model="o4-mini", reasoning_effort=REASONING_EFFORT)
        
        response = openai_client.chat.completions.create(
            model="o4-mini",  # Using OpenAI's o4-mini reasoning model
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            max_completion_tokens=1500,  # o4-mini uses max_completion_tokens
            reasoning_effort=REASONING_EFFORT  # "low", "medium", or "high"
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


# Removed old assistant handlers - now using HTTP webhooks


# Old assistant handlers removed - replaced with HTTP webhook handlers above


# Create Flask app for Cloud Run HTTP requirements
flask_app = Flask(__name__)

@flask_app.route("/health")
def health_check():
    """Health check endpoint for Cloud Run."""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "service": "dataiku-agent"
    })

@flask_app.route("/")
def root():
    """Root endpoint for Cloud Run."""
    return jsonify({
        "message": "Dataiku Agent is running",
        "status": "active",
        "timestamp": datetime.now().isoformat()
    })

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    """Handle Slack events via HTTP webhooks (replaces Socket Mode)."""
    try:
        # Slack sends URL verification challenges
        if request.json and request.json.get("type") == "url_verification":
            return jsonify({"challenge": request.json.get("challenge")})
        
        # Process the event asynchronously 
        event_data = request.json
        if event_data and event_data.get("event"):
            event = event_data["event"]
            
            # Handle app mentions
            if event.get("type") == "app_mention":
                # Process in background thread for fast response
                processing_thread = threading.Thread(
                    target=handle_app_mention_async,
                    args=(event,),
                    daemon=False
                )
                processing_thread.start()
        
        # Return 200 immediately (required by Slack)
        return "", 200
        
    except Exception as e:
        logger.error("slack_events_error", error=str(e), error_type=type(e).__name__)
        return "", 200  # Still return 200 to avoid retries

def handle_app_mention_async(event):
    """Handle app mention events asynchronously."""
    try:
        user_query = event.get("text", "").strip()
        channel_id = event.get("channel")
        thread_ts = event.get("ts")  # Use event timestamp as thread
        
        # Remove the bot mention from the query
        user_query = re.sub(r'<@[A-Z0-9]+>', '', user_query).strip()
        
        if not user_query:
            return
            
        logger.info("processing_app_mention", query=user_query, channel=channel_id)
        
        # Search and synthesize response
        search_results = search_brave(user_query)
        
        if not search_results:
            response = "I couldn't find any relevant information about your query. Please try rephrasing your question or asking about a different aspect of Dataiku."
        else:
            answer = synthesize_answer(user_query, search_results)
            if not answer or len(answer.strip()) == 0:
                answer = "I found some relevant information about your query. Here are the sources I found:"
            response = format_response_with_sources(answer, search_results)
        
        # Send response to Slack
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=response,
            mrkdwn=True,
            unfurl_links=False,
            unfurl_media=False
        )
        
        logger.info("app_mention_completed", query=user_query)
        
    except Exception as e:
        logger.error("handle_app_mention_failed", error=str(e), error_type=type(e).__name__)


def run_flask_server():
    """Run Flask server for Cloud Run HTTP requirements."""
    try:
        port = int(os.environ.get("PORT", 8080))
        logger.info("starting_http_server", port=port, host="0.0.0.0")
        
        # Use a production WSGI server instead of Flask's dev server
        from werkzeug.serving import make_server
        server = make_server("0.0.0.0", port, flask_app)
        logger.info("flask_server_ready", port=port)
        server.serve_forever()
        
    except Exception as e:
        logger.error("flask_server_failed", error=str(e), error_type=type(e).__name__)
        raise


def main():
    """Main entry point for the application."""
    logger.info("starting_dataiku_agent_http_mode", 
                bot_token_present=bool(SLACK_BOT_TOKEN))
    
    # Run Flask server for HTTP webhook mode (much faster than Socket Mode)
    logger.info("dataiku_agent_starting_http_mode")
    run_flask_server()


if __name__ == "__main__":
    main() 