"""
Main Flask application for the Dataiku Slack AI Assistant.

This is the HTTP webhook server that processes Slack events and delegates
to the appropriate handlers and services.
"""

import time
import queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request

from .core.config import validate_config, PORT
from .core.clients import get_logger
from .handlers.slack_handlers import (
    handle_app_mention_async,
    handle_direct_message_async,
    handle_assistant_thread_started_async,
    handle_assistant_thread_context_changed_async
)

# Validate configuration at startup
validate_config()

# Configure logging
logger = get_logger()

# Create Flask app for Cloud Run HTTP requirements
flask_app = Flask(__name__)

# Initialize thread pool for background processing
thread_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dataiku-worker")

# Task queue for background processing (in-memory for simplicity)
task_queue = queue.Queue(maxsize=1000)

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
    request_start_time = time.time()
    try:
        event_data = request.json
        logger.info("received_slack_event", 
                   event_type=event_data.get("type") if event_data else "no_data",
                   has_event=bool(event_data and event_data.get("event")),
                   event_subtype=event_data.get("event", {}).get("type") if event_data and event_data.get("event") else "none",
                   request_start_time=request_start_time)
        
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
                # Process in background thread pool for fast response
                thread_pool.submit(handle_assistant_thread_started_async, event)
            elif event.get("type") == "assistant_thread_context_changed":
                logger.info("handling_assistant_thread_context_changed",
                           channel_id=event.get("assistant_thread", {}).get("channel_id"))
                # Process context change (lightweight operation)
                thread_pool.submit(handle_assistant_thread_context_changed_async, event)
            # Handle app mentions and direct messages
            elif event.get("type") == "app_mention":
                logger.info("handling_app_mention", text=event.get("text"))
                # Process in background thread pool for fast response
                thread_pool.submit(handle_app_mention_async, event)
            elif event.get("type") == "message" and event.get("channel_type") == "im":
                logger.info("handling_direct_message", text=event.get("text"))
                # Process direct messages in background thread pool
                thread_pool.submit(handle_direct_message_async, event)
            else:
                logger.info("ignoring_event_type", 
                           event_type=event.get("type"),
                           channel_type=event.get("channel_type"),
                           subtype=event.get("subtype"))
        
        # Return 200 immediately (required by Slack) - this is our ACK
        ack_time = time.time()
        time_to_ack_ms = int((ack_time - request_start_time) * 1000)
        logger.info("slack_event_ack_sent", 
                   time_to_ack_ms=time_to_ack_ms,
                   background_tasks_queued=True)
        return "", 200
        
    except Exception as e:
        ack_time = time.time()
        time_to_ack_ms = int((ack_time - request_start_time) * 1000)
        logger.error("slack_events_error", 
                    error=str(e), 
                    error_type=type(e).__name__,
                    time_to_ack_ms=time_to_ack_ms)
        return "", 200  # Still return 200 to avoid retries

# For Gunicorn, we need to expose the Flask app as 'application'
application = flask_app

def main():
    """Main entry point for the application (used when running with Gunicorn)."""
    logger.info("starting_dataiku_agent_http_mode")
    logger.info("dataiku_agent_ready_for_gunicorn")
    return application

if __name__ == "__main__":
    # This is for development only - production uses Gunicorn
    logger.warning("running_in_development_mode_use_gunicorn_for_production")
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)