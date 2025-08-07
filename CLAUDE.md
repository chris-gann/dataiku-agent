# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

This is a **Slack AI Assistant for Dataiku** that provides real-time answers about Dataiku by combining Brave Search API results with OpenAI o4-mini reasoning model synthesis. The application has migrated from Socket Mode to HTTP webhooks for better scalability and Cloud Run compatibility.

### Key Components

- **Flask HTTP Server** (`src/app.py`): Main application server handling Slack webhooks
- **Slack Integration**: Uses HTTP webhooks instead of Socket Mode for production deployment
- **Search Integration**: Brave Search API for real-time web search
- **AI Synthesis**: OpenAI o4-mini reasoning model for intelligent response generation
- **Cloud Deployment**: Google Cloud Run with Docker containerization

### Core Workflow

1. Slack sends events via HTTP webhooks to `/slack/events`
2. Events are processed asynchronously using ThreadPoolExecutor
3. User queries trigger Brave Search for relevant Dataiku information
4. OpenAI o4-mini synthesizes responses from search results
5. Formatted responses are sent back to Slack with numbered URL references

## Development Commands

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables (copy from env.example)
cp env.example .env
# Edit .env with your API keys

# Run in development mode
python src/app.py
```

### Testing
```bash
# Run all tests
python -m pytest tests/

# Run specific test categories
python -m pytest tests/unit/
python -m pytest tests/integration/
```

### Production Deployment
```bash
# Build Docker image
docker build -t dataiku-agent .

# Run with Gunicorn (production)
gunicorn --config gunicorn.conf.py src.app:application

# Deploy to Google Cloud Run (see deployment/ folder for scripts)
./deployment/setup-secrets.sh  # One-time setup
# Push to GitHub for automatic deployment
```

### Context7 MCP
- Always use the Context7 MCP when working with external code libraries to retrieve the most up-to-date documentation

## Code Structure

### Main Application (`src/app.py`)
- **Lazy Loading**: Heavy imports (OpenAI, Slack SDK) are loaded only when needed
- **Async Processing**: Uses ThreadPoolExecutor for non-blocking webhook responses
- **Error Handling**: Comprehensive fallback responses for API failures
- **Structured Logging**: Uses structlog for production-ready logging

### Key Functions
- `search_brave()`: Handles Brave Search API calls with retry logic
- `synthesize_answer()`: Uses OpenAI o4-mini for response generation
- `format_response_with_sources()`: Converts URLs to numbered Slack hyperlinks
- `generate_fallback_response()`: Provides intelligent fallbacks for common Dataiku issues

### Slack Event Handlers
- `handle_assistant_thread_started_async()`: Sets up AI assistant threads
- `handle_direct_message_async()`: Processes DMs with status updates
- `handle_app_mention_async()`: Handles @mentions in channels

## Environment Variables

Required:
- `SLACK_BOT_TOKEN`: Bot User OAuth Token (xoxb-...)
- `OPENAI_API_KEY`: OpenAI API key for o4-mini model
- `BRAVE_API_KEY`: Brave Search API key

Optional:
- `REASONING_EFFORT`: OpenAI reasoning effort ("low", "medium", "high", default: "medium")
- `LOG_LEVEL`: Logging level (default: "INFO")
- `PORT`: Server port (default: 8080)

## Deployment Configuration

### Docker (`Dockerfile`)
- Uses Python 3.11-slim for optimal performance
- Non-root user for security
- Pre-compiled bytecode for faster startup
- Health check endpoint at `/health`

### Gunicorn (`gunicorn.conf.py`)
- Multi-worker, multi-threaded configuration
- Optimized for Cloud Run environment
- Request timeouts and memory management
- Structured logging integration

### Slack App Configuration (`manifest.json`)
- HTTP webhook event subscriptions (not Socket Mode)
- AI Assistant API permissions
- Required OAuth scopes for bot functionality

## Performance Optimizations

The codebase includes several performance enhancements documented in `PERFORMANCE_OPTIMIZATIONS.md`:

- Lazy loading of heavy dependencies
- Async webhook processing with immediate ACKs
- Query sanitization and intelligent fallbacks
- Retry logic with exponential backoff
- Docker image optimization with bytecode compilation

## Integration Notes

- **No package.json**: This is a Python project, not Node.js
- **Flask-based**: Uses Flask for HTTP server, not Express
- **Cloud Run Ready**: Configured for Google Cloud Run deployment
- **Slack AI Native**: Uses Slack's AI Assistant APIs for enhanced UX
- **Search-Powered**: Relies on external search rather than static knowledge base

## Common Development Tasks

### Adding New Fallback Responses
Edit the `generate_fallback_response()` function in `src/app.py` to handle new error patterns or common user queries.

### Modifying AI Responses
Update the `SYSTEM_PROMPT` constant to change how the AI assistant responds and formats answers.

### Slack Event Handling
Add new event handlers by:
1. Adding the event type to `manifest.json`
2. Creating an async handler function
3. Adding the handler to the `/slack/events` endpoint

### Search Enhancement
Modify `search_brave()` parameters or add query preprocessing in `sanitize_search_query()` for better search results.