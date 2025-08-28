"""
Main Flask application for the Dataiku Slack AI Assistant.

This is the HTTP webhook server that processes Slack events and delegates
to the appropriate handlers and services.
"""

import time
import queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request, redirect, url_for, make_response

from .core.config import validate_config, PORT, SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, SLACK_REDIRECT_URI
import requests
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

@flask_app.route("/slack/oauth_redirect", methods=["GET"])
def slack_oauth_redirect():
    """Handle Slack OAuth redirect after user authorizes the app.

    Exchanges the temporary authorization code for an access token using oauth.v2.access.
    This enables installs for public distribution. Bot token continues to be used for API calls.
    """
    try:
        error = request.args.get("error")
        if error:
            # User denied or Slack returned an error
            html = f"<html><body><h2>Slack OAuth Failed</h2><p>Error: {error}</p></body></html>"
            return make_response(html, 400)

        code = request.args.get("code")
        if not code:
            html = "<html><body><h2>Slack OAuth Failed</h2><p>Missing authorization code.</p></body></html>"
            return make_response(html, 400)

        if not SLACK_CLIENT_ID or not SLACK_CLIENT_SECRET:
            html = "<html><body><h2>Slack OAuth Not Configured</h2><p>Missing SLACK_CLIENT_ID or SLACK_CLIENT_SECRET on server.</p></body></html>"
            return make_response(html, 500)

        # Determine redirect_uri to send back to Slack for verification (must match Slack settings)
        # Prefer explicit env override, else infer from request host/scheme
        if SLACK_REDIRECT_URI:
            redirect_uri = SLACK_REDIRECT_URI
        else:
            redirect_uri = f"{request.scheme}://{request.host}/slack/oauth_redirect"

        token_url = "https://slack.com/api/oauth.v2.access"
        payload = {
            "client_id": SLACK_CLIENT_ID,
            "client_secret": SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri
        }
        response = requests.post(token_url, data=payload, timeout=15)
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

        ok = bool(data.get("ok"))
        if not ok:
            # Capture safe error fields only
            error_reason = data.get("error") or "unknown_error"
            html = f"<html><body><h2>Slack OAuth Failed</h2><p>Error: {error_reason}</p></body></html>"
            return make_response(html, 400)

        # Optional: you can store installer info (team, enterprise, authed_user) for multi-workspace installs
        # For now, we acknowledge success with a simple page.
        html = "<html><body><h2>✅ Slack app installed successfully</h2><p>You can close this window and return to Slack.</p></body></html>"
        return make_response(html, 200)

    except Exception as e:
        html = f"<html><body><h2>Slack OAuth Error</h2><p>{str(e)}</p></body></html>"
        return make_response(html, 500)

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