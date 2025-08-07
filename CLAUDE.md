# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
python src/app.py
```

### Testing
```bash
python -m pytest tests/
```

### Running Individual Tests
```bash
python -m pytest tests/test_app.py
python -m pytest tests/test_quick.py
```

## Architecture Overview

This is a Slack AI assistant that provides Dataiku expertise using a sophisticated multi-service architecture:

### Core Components

**Flask HTTP Server (`src/app.py`)**
- Main entry point for Cloud Run deployment
- Handles Slack webhook events via HTTP
- Delegates to async handlers for processing
- Includes health check endpoint at `/health`

**LangGraph Agent (`src/agents/langgraph_agent.py`)**
- Primary AI orchestration using LangGraph state machine
- Manages complex multi-step workflows for query processing
- Handles search → synthesis → formatting pipeline
- Includes conversation memory and error recovery

**Service Layer**
- `ai_service.py`: OpenAI o4-mini integration with configurable reasoning effort
- `search_service.py`: Brave Search API integration with metadata handling
- `slack_service.py`: Slack API interactions and formatting

### Key Architecture Patterns

**Async Processing**: Uses ThreadPoolExecutor for background processing of Slack events to meet Slack's 3-second response requirement

**State Management**: LangGraph manages complex agent state including:
- Query processing pipeline
- Search result handling
- Confidence scoring
- Error context and recovery

**Service Abstraction**: Clear separation between:
- HTTP handlers (Flask routes)
- Event handlers (Slack-specific logic) 
- Business services (AI, search, formatting)
- Utility functions (text processing, fallbacks)

**Configuration**: Centralized in `core/config.py` with environment variable validation

### Deployment Architecture

**Production**: Google Cloud Run with Docker containerization
- Gunicorn WSGI server with multi-threading
- Health checks and monitoring
- Secret Manager integration for API keys

**Development**: Direct Python execution with Socket Mode for local testing

## Environment Setup

Required environment variables:
- `SLACK_BOT_TOKEN`: Slack Bot User OAuth Token
- `OPENAI_API_KEY`: OpenAI API key
- `BRAVE_API_KEY`: Brave Search API key
- `REASONING_EFFORT`: OpenAI reasoning level (low/medium/high)
- `LOG_LEVEL`: Logging verbosity (default: INFO)

## Testing Strategy

- Unit tests in `tests/unit/`
- Integration tests in `tests/integration/`
- Quick smoke tests in `tests/test_quick.py`
- Main application tests in `tests/test_app.py`

## Key Technical Details

**OpenAI Integration**: Uses o4-mini model with configurable reasoning effort for cost-effective yet sophisticated responses

**Search Strategy**: Brave Search with Dataiku-specific query enhancement and result filtering

**Slack Formatting**: Native mrkdwn formatting with numbered URL references for clean message presentation

**Error Handling**: Multi-layered fallback system with graceful degradation for API failures

**Memory Management**: LangGraph MemorySaver for conversation context retention