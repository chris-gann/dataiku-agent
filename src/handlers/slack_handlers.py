"""
Slack event handlers for processing app mentions, direct messages, and assistant threads.

Handles all Slack webhook events and delegates to appropriate services.
"""

import re
import time
from typing import Dict, Any

from ..core.clients import get_slack_client, get_logger
from ..services.slack_service import set_assistant_status, set_suggested_prompts, set_thread_title

logger = get_logger()

def handle_app_mention_async(event: Dict[str, Any]):
    """Handle app mention events asynchronously using LangGraph agent."""
    start_time = time.time()
    try:
        user_query = event.get("text", "").strip()
        channel_id = event.get("channel")
        thread_ts = event.get("ts")  # Use event timestamp as thread
        
        # Remove the bot mention from the query
        user_query = re.sub(r'<@[A-Z0-9]+>', '', user_query).strip()
        
        if not user_query:
            return
            
        logger.info("processing_app_mention_with_agent", 
                   query=user_query, 
                   channel=channel_id,
                   processing_start_time=start_time)
        
        # Lazy import to avoid circular dependency
        from ..agents.langgraph_agent import get_agent
        
        # Use LangGraph agent to process the query
        agent = get_agent()
        response = agent.process_query(
            query=user_query,
            thread_id=f"{channel_id}_{thread_ts}"
        )
        
        # Send response to Slack
        client = get_slack_client()
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=response,
            mrkdwn=True,
            unfurl_links=False,
            unfurl_media=False
        )
        
        total_duration = time.time() - start_time
        logger.info("app_mention_completed_with_agent", 
                   query=user_query,
                   total_duration_ms=int(total_duration * 1000))
        
    except Exception as e:
        logger.error("handle_app_mention_failed", error=str(e), error_type=type(e).__name__)

def handle_direct_message_async(event: Dict[str, Any]):
    """Handle direct message events asynchronously using LangGraph agent."""
    start_time = time.time()
    try:
        user_query = event.get("text", "").strip()
        channel_id = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")  # Use thread_ts if available
        
        # Ignore bot messages and messages with subtypes (like message edits)
        if event.get("bot_id") or event.get("subtype"):
            return
            
        if not user_query:
            return
            
        logger.info("processing_direct_message_with_agent", 
                   query=user_query, 
                   channel=channel_id,
                   thread_ts=thread_ts,
                   processing_start_time=start_time)
        
        # Set status to show the assistant is working
        if thread_ts:
            set_assistant_status(channel_id, thread_ts, "is thinking...")
        
        # Lazy import to avoid circular dependency
        from ..agents.langgraph_agent import get_agent
        
        # Use LangGraph agent to process the query
        agent = get_agent()
        response = agent.process_query(
            query=user_query,
            thread_id=f"{channel_id}_{thread_ts}"
        )
        
        # Send response to Slack (this will clear the status automatically)
        client = get_slack_client()
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
        
        total_duration = time.time() - start_time
        logger.info("direct_message_completed_with_agent", 
                   query=user_query,
                   total_duration_ms=int(total_duration * 1000))
        
    except Exception as e:
        logger.error("handle_direct_message_failed", error=str(e), error_type=type(e).__name__)
        # Clear status if there was an error
        if 'thread_ts' in locals() and thread_ts:
            set_assistant_status(channel_id, thread_ts, "")

def handle_assistant_thread_started_async(event: Dict[str, Any]):
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
        client = get_slack_client()
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

def handle_assistant_thread_context_changed_async(event: Dict[str, Any]):
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