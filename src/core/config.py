"""
Configuration management for the Dataiku Agent.

Centralizes environment variable handling and application settings.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Core API Keys (strip whitespace from secrets)
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "").strip()

# AI Model configuration
REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "medium")

# Server configuration
PORT = int(os.environ.get("PORT", 8080))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Brave Search configuration
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_HEADERS = {
    "Accept": "application/json",
    "X-Subscription-Token": BRAVE_API_KEY
}

# Validate required environment variables
def validate_config():
    """Validate that all required environment variables are present."""
    missing = []
    if not SLACK_BOT_TOKEN:
        missing.append("SLACK_BOT_TOKEN")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not BRAVE_API_KEY:
        missing.append("BRAVE_API_KEY")
    
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# System prompt for OpenAI (unified)
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