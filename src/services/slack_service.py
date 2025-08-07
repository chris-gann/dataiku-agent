"""
Slack API service for assistant status and thread management.

Provides helper functions for Slack's AI Assistant API features.
"""

from ..core.clients import get_slack_client, get_logger

logger = get_logger()

def set_assistant_status(channel_id, thread_ts, status):
    """Set the status for an AI assistant thread."""
    try:
        slack_client = get_slack_client()
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
            
        slack_client = get_slack_client()
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
        slack_client = get_slack_client()
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