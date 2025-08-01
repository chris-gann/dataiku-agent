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

# Initialize Slack Web API client for AI Assistant methods
slack_client = WebClient(token=SLACK_BOT_TOKEN)

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

CRITICAL URL RULES:
- When referencing URLs, you can use numbered references like [1], [2] which will be converted to clickable links
- ALWAYS use complete URLs from the search results (full https://domain.com/path format)
- NEVER use partial URLs or relative paths - always complete URLs
- You can write either "Check out https://doc.dataiku.com" OR "Check out [1]" (if URL 1 is https://doc.dataiku.com)
- For bold text, use *single asterisks* NOT **double asterisks**

Focus on being helpful, clear, and accurate in your responses about Dataiku's features, capabilities, and usage."""


# AI Assistant API Helper Functions
def set_assistant_status(channel_id, thread_ts, status):
    """Set the status for an AI assistant thread."""
    try:
        response = slack_client.api_call(
            "assistant.threads.setStatus",
            json={
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "status": status
            }
        )
        if not response["ok"]:
            logger.error("Failed to set assistant status", error=response.get("error"))
        return response
    except Exception as e:
        logger.error("Error setting assistant status", error=str(e))
        return None

def set_suggested_prompts(channel_id, thread_ts, prompts, title=None):
    """Set suggested prompts for an AI assistant thread."""
    try:
        payload = {
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "prompts": prompts
        }
        if title:
            payload["title"] = title
            
        response = slack_client.api_call(
            "assistant.threads.setSuggestedPrompts",
            json=payload
        )
        if not response["ok"]:
            logger.error("Failed to set suggested prompts", error=response.get("error"))
        return response
    except Exception as e:
        logger.error("Error setting suggested prompts", error=str(e))
        return None

def set_thread_title(channel_id, thread_ts, title):
    """Set the title for an AI assistant thread."""
    try:
        response = slack_client.api_call(
            "assistant.threads.setTitle",
            json={
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "title": title
            }
        )
        if not response["ok"]:
            logger.error("Failed to set thread title", error=response.get("error"))
        return response
    except Exception as e:
        logger.error("Error setting thread title", error=str(e))
        return None


def sanitize_search_query(query: str) -> str:
    """
    Sanitize user query for search API.
    
    Args:
        query: Raw user query
        
    Returns:
        Cleaned query suitable for search
    """
    # Remove line breaks and replace with spaces
    cleaned = re.sub(r'\s*\n\s*', ' ', query)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Remove special characters that can cause API issues
    cleaned = re.sub(r'[*#@$%^&(){}[\]|\\:;"\'<>?/+=~`]', ' ', cleaned)
    
    # If it's an error message, extract the key parts
    if "error" in cleaned.lower() or "not allowed" in cleaned.lower():
        # Extract key error concepts
        error_keywords = []
        if "not allowed" in cleaned.lower():
            error_keywords.append("not allowed")
        if "prediction" in cleaned.lower():
            error_keywords.append("prediction models")
        if "visual machine learning" in cleaned.lower():
            error_keywords.append("visual machine learning")
        if "profile" in cleaned.lower():
            error_keywords.append("user profile permissions")
            
        if error_keywords:
            cleaned = " ".join(error_keywords)
    
    # Truncate if too long (API limits)
    max_length = 100
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rsplit(' ', 1)[0]  # Cut at word boundary
    
    return cleaned.strip()


def generate_fallback_response(query: str) -> str:
    """
    Generate intelligent fallback responses for common Dataiku issues when search fails.
    
    Args:
        query: User's original query
        
    Returns:
        Helpful fallback response
    """
    query_lower = query.lower()
    
    # Permission and profile issues
    if any(phrase in query_lower for phrase in ["not allowed", "permission", "profile", "visual machine learning", "prediction model"]):
        return """🔒 **Dataiku User Profile & Permissions Issue**

This error occurs when your user profile doesn't have the necessary permissions for Visual Machine Learning features.

**Immediate Solutions:**
• Contact your Dataiku administrator to request a profile upgrade
• Ask to be assigned to a group with "Data Scientist" or "ML Practitioner" permissions
• Check if your organization has Visual ML licenses available

**Profile Types in Dataiku:**
• **Reader**: Can view projects and dashboards
• **Analyst**: Can create basic recipes and datasets  
• **Data Scientist**: Can use Visual ML, code recipes, and advanced features
• **Admin**: Full platform access

**Common Causes:**
• License limitations in your Dataiku instance
• Restrictive user group assignments
• Organization policy restrictions

💡 **Tip**: Most Visual ML features require "Data Scientist" level permissions or higher."""

    # Authentication issues
    elif any(phrase in query_lower for phrase in ["authentication", "login", "access denied", "unauthorized"]):
        return """🔐 **Dataiku Authentication Issue**

**Common Solutions:**
• Clear browser cache and cookies for Dataiku
• Try logging in with incognito/private browsing mode
• Check with your admin about LDAP/SSO configuration
• Verify your username and password are correct
• Check if your account has been deactivated

**If using SSO:**
• Ensure you're accessing Dataiku through the correct SSO portal
• Contact your IT team about SSO token expiration"""

    # Dataset/connection issues  
    elif any(phrase in query_lower for phrase in ["dataset", "connection", "cannot connect", "data source"]):
        return """📊 **Dataiku Dataset/Connection Issue**

**Troubleshooting Steps:**
• Check dataset connection settings in the dataset settings page
• Verify database credentials and network connectivity
• Test the connection using "Test & Get Schema"
• Check if the source system is available and accessible
• Review connection logs for detailed error messages

**Common Causes:**
• Expired database credentials
• Network/firewall restrictions
• Source system maintenance or downtime
• Changed schema or table structure"""

    # Recipe/job failures
    elif any(phrase in query_lower for phrase in ["recipe failed", "job failed", "build failed", "error in recipe"]):
        return """⚙️ **Dataiku Recipe/Job Failure**

**Debugging Steps:**
• Check the job logs for detailed error messages
• Review the recipe configuration and input datasets
• Verify all required columns are present in input data
• Check for data quality issues (nulls, formatting, etc.)
• Ensure sufficient compute resources are available

**Common Solutions:**
• Refresh input dataset schemas
• Clear recipe cache and rebuild
• Check SQL syntax in SQL recipes
• Verify Python/R code syntax in code recipes"""

    # Performance issues
    elif any(phrase in query_lower for phrase in ["slow", "performance", "timeout", "hanging"]):
        return """⚡ **Dataiku Performance Issue**

**Optimization Tips:**
• Use dataset sampling for large datasets during development
• Add appropriate filters to reduce data volume
• Consider using database pushdown for SQL operations
• Check cluster resource allocation
• Review recipe memory and CPU settings

**For Visual Recipes:**
• Use "Limit" step to work with smaller datasets
• Optimize Join operations (use appropriate join types)
• Consider partitioning large datasets"""

    # General fallback
    else:
        return f"""🤖 **Dataiku Assistant - Search Temporarily Unavailable**

I'm having trouble searching for specific information about your query right now, but here are some general resources that might help:

**Quick Help:**
• Check the Dataiku Documentation: https://doc.dataiku.com/
• Visit Dataiku Community: https://community.dataiku.com/
• Contact your Dataiku administrator for account-specific issues
• Try rephrasing your question with more specific terms

**Your Query:** `{query[:200]}{'...' if len(query) > 200 else ''}`

Please try asking again in a few minutes, or contact your Dataiku administrator if this is urgent."""


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
        # Sanitize the query before searching
        clean_query = sanitize_search_query(query)
        logger.info("query_sanitized", original=query[:100], sanitized=clean_query)
        
        params = {
            "q": f"{clean_query} Dataiku",  # Add Dataiku to focus results
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

Please provide a helpful, accurate answer based on these search results. 

IMPORTANT URL INSTRUCTIONS:
- When referencing URLs from the search results, you can use either complete URLs OR numbered references like [1], [2]
- If using numbered references, make sure they correspond to actual URLs from the search results above
- NEVER use partial URLs like "dataiku.com/product/" - always use complete URLs from search results
- Numbered references will be automatically converted to clickable Slack hyperlinks

Format your response using Slack mrkdwn formatting for better readability."""

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
    # Enhanced pattern to match complete URLs (not already in Slack format)
    # This pattern avoids matching URLs that are already in <URL|text> format
    url_pattern = r'(?<!<)https?://[^\s<>"\'`|]+(?:\.[a-zA-Z]{2,}|:[0-9]+)[^\s<>"\'`|]*[^\s<>"\'`|.,!?;)](?!\|)'
    
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


def convert_numbered_refs_to_links(text: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Convert numbered references like [1], [2] to proper Slack hyperlinks using search results.
    
    Args:
        text: Text containing numbered references
        search_results: List of search results with URLs
        
    Returns:
        Text with numbered references converted to Slack hyperlinks
    """
    if not search_results:
        return text
    
    # Create mapping of numbers to URLs
    url_map = {}
    for i, result in enumerate(search_results, 1):
        url = result.get('url', '')
        if url:
            url_map[i] = url
    
    # Pattern to find numbered references like [1], [2], etc.
    def replace_numbered_ref(match):
        ref_num = int(match.group(1))
        if ref_num in url_map:
            url = url_map[ref_num]
            return f"<{url}|[{ref_num}]>"
        else:
            # Keep the original reference if no URL found
            return match.group(0)
    
    # Replace numbered references with Slack hyperlinks
    result = re.sub(r'\[(\d+)\]', replace_numbered_ref, text)
    
    return result


def format_response_with_sources(answer: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Format the response with Slack formatting and numbered URL links.
    
    Args:
        answer: The synthesized answer
        search_results: The search results to map numbered references to actual URLs
        
    Returns:
        Slack-formatted answer with numbered URL links
    """
    if not answer:
        return answer
    
    # Fix double asterisks to single asterisks for proper Slack bold formatting
    # Replace **text** with *text* (but not if already single asterisks)
    formatted_answer = re.sub(r'\*\*([^\*]+?)\*\*', r'*\1*', answer)
    
    # Convert numbered references to proper Slack hyperlinks using search results
    formatted_answer = convert_numbered_refs_to_links(formatted_answer, search_results)
    
    # Also handle any remaining plain URLs
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
        event_data = request.json
        logger.info("received_slack_event", 
                   event_type=event_data.get("type") if event_data else "no_data",
                   has_event=bool(event_data and event_data.get("event")),
                   event_subtype=event_data.get("event", {}).get("type") if event_data and event_data.get("event") else "none")
        
        # Slack sends URL verification challenges
        if event_data and event_data.get("type") == "url_verification":
            logger.info("handling_url_verification")
            return jsonify({"challenge": event_data.get("challenge")})
        
        # Process the event asynchronously 
        if event_data and event_data.get("event"):
            event = event_data["event"]
            logger.info("processing_event", event_type=event.get("type"), event_data=event)
            
            # Handle AI Assistant events
            if event.get("type") == "assistant_thread_started":
                logger.info("handling_assistant_thread_started", 
                           channel_id=event.get("assistant_thread", {}).get("channel_id"))
                # Process in background thread for fast response
                processing_thread = threading.Thread(
                    target=handle_assistant_thread_started_async,
                    args=(event,),
                    daemon=False
                )
                processing_thread.start()
            elif event.get("type") == "assistant_thread_context_changed":
                logger.info("handling_assistant_thread_context_changed",
                           channel_id=event.get("assistant_thread", {}).get("channel_id"))
                # Process context change (lightweight operation)
                processing_thread = threading.Thread(
                    target=handle_assistant_thread_context_changed_async,
                    args=(event,),
                    daemon=False
                )
                processing_thread.start()
            # Handle app mentions and direct messages
            elif event.get("type") == "app_mention":
                logger.info("handling_app_mention", text=event.get("text"))
                # Process in background thread for fast response
                processing_thread = threading.Thread(
                    target=handle_app_mention_async,
                    args=(event,),
                    daemon=False
                )
                processing_thread.start()
            elif event.get("type") == "message" and event.get("channel_type") == "im":
                logger.info("handling_direct_message", text=event.get("text"))
                # Process direct messages in background thread
                processing_thread = threading.Thread(
                    target=handle_direct_message_async,
                    args=(event,),
                    daemon=False
                )
                processing_thread.start()
            else:
                logger.info("ignoring_event_type", 
                           event_type=event.get("type"),
                           channel_type=event.get("channel_type"),
                           subtype=event.get("subtype"))
        
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
        
        # Search and synthesize response with fallback for search failures
        try:
            search_results = search_brave(user_query)
        except Exception as search_error:
            logger.error("search_failed_using_fallback", error=str(search_error))
            # Provide intelligent fallback response for common Dataiku issues
            response = generate_fallback_response(user_query)
            search_results = []
        
        if not search_results and not hasattr(locals(), 'response'):
            response = "I couldn't find any relevant information about your query. Please try rephrasing your question or asking about a different aspect of Dataiku."
        elif search_results:
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


def handle_direct_message_async(event):
    """Handle direct message events asynchronously."""
    try:
        user_query = event.get("text", "").strip()
        channel_id = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")  # Use thread_ts if available
        
        # Ignore bot messages and messages with subtypes (like message edits)
        if event.get("bot_id") or event.get("subtype"):
            return
            
        if not user_query:
            return
            
        logger.info("processing_direct_message", 
                   query=user_query, 
                   channel=channel_id,
                   thread_ts=thread_ts)
        
        # Set status to show the assistant is working
        if thread_ts:
            set_assistant_status(channel_id, thread_ts, "is searching for information...")
        
        # Search and synthesize response with fallback for search failures
        try:
            search_results = search_brave(user_query)
        except Exception as search_error:
            logger.error("search_failed_using_fallback", error=str(search_error))
            # Provide intelligent fallback response for common Dataiku issues
            response = generate_fallback_response(user_query)
            search_results = []
        
        # Update status to show synthesis
        if thread_ts:
            set_assistant_status(channel_id, thread_ts, "is analyzing results...")
        
        if not search_results and not hasattr(locals(), 'response'):
            response = "I couldn't find any relevant information about your query. Please try rephrasing your question or asking about a different aspect of Dataiku."
        elif search_results:
            answer = synthesize_answer(user_query, search_results)
            if not answer or len(answer.strip()) == 0:
                answer = "I found some relevant information about your query. Here are the sources I found:"
            response = format_response_with_sources(answer, search_results)
        
        # Send response to Slack (this will clear the status automatically)
        client = WebClient(token=SLACK_BOT_TOKEN)
        chat_response = client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,  # Ensure proper threading
            text=response,
            mrkdwn=True,
            unfurl_links=False,
            unfurl_media=False
        )
        
        # If this is a new thread and we have AI Assistant features enabled,
        # set a helpful title for the conversation
        if chat_response.get("ok") and not event.get("thread_ts"):
            # This is a new thread, set a title
            new_thread_ts = chat_response.get("ts")
            if new_thread_ts:
                # Create a short title from the query
                title = user_query[:50] + "..." if len(user_query) > 50 else user_query
                set_thread_title(channel_id, new_thread_ts, f"Q: {title}")
        
        logger.info("direct_message_completed", query=user_query)
        
    except Exception as e:
        logger.error("handle_direct_message_failed", error=str(e), error_type=type(e).__name__)
        # Clear status if there was an error
        if 'thread_ts' in locals() and thread_ts:
            set_assistant_status(channel_id, thread_ts, "")


def handle_assistant_thread_started_async(event):
    """Handle assistant thread started events asynchronously."""
    try:
        assistant_thread = event.get("assistant_thread", {})
        channel_id = assistant_thread.get("channel_id")
        thread_ts = assistant_thread.get("thread_ts")
        context = assistant_thread.get("context", {})
        
        if not channel_id or not thread_ts:
            logger.error("missing_assistant_thread_data", event=event)
            return
            
        logger.info("processing_assistant_thread_started", 
                   channel_id=channel_id, 
                   thread_ts=thread_ts,
                   context=context)
        
        # Send welcome message
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="👋 Hi! I'm your Dataiku AI assistant. I can help you with questions about Dataiku's features, best practices, and troubleshooting.",
            mrkdwn=True
        )
        
        # Set suggested prompts to help users get started
        suggested_prompts = [
            {
                "title": "Getting Started",
                "message": "How do I create my first project in Dataiku?"
            },
            {
                "title": "Data Preparation",
                "message": "What are the best practices for data preparation in Dataiku?"
            },
            {
                "title": "Machine Learning",
                "message": "How do I build and deploy a machine learning model?"
            },
            {
                "title": "Visual Recipes",
                "message": "What are visual recipes and how do I use them?"
            }
        ]
        
        set_suggested_prompts(
            channel_id=channel_id,
            thread_ts=thread_ts,
            prompts=suggested_prompts,
            title="Here are some things I can help you with:"
        )
        
        logger.info("assistant_thread_started_completed", 
                   channel_id=channel_id, 
                   thread_ts=thread_ts)
        
    except Exception as e:
        logger.error("handle_assistant_thread_started_failed", 
                    error=str(e), 
                    error_type=type(e).__name__)


def handle_assistant_thread_context_changed_async(event):
    """Handle assistant thread context changed events asynchronously."""
    try:
        assistant_thread = event.get("assistant_thread", {})
        channel_id = assistant_thread.get("channel_id")
        thread_ts = assistant_thread.get("thread_ts")
        context = assistant_thread.get("context", {})
        
        logger.info("processing_assistant_thread_context_changed", 
                   channel_id=channel_id, 
                   thread_ts=thread_ts,
                   context=context)
        
        # Context changes are mainly for tracking - no immediate action needed
        # This could be used to provide channel-specific suggestions in the future
        
        logger.info("assistant_thread_context_changed_completed", 
                   channel_id=channel_id, 
                   thread_ts=thread_ts)
        
    except Exception as e:
        logger.error("handle_assistant_thread_context_changed_failed", 
                    error=str(e), 
                    error_type=type(e).__name__)


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