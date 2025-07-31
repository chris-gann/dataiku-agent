# Dataiku Agent - Slack AI Assistant

A Slack-native AI assistant that provides accurate, up-to-date answers about Dataiku by combining Brave Search API results with OpenAI synthesis.

## Features

- 🤖 **AI-powered responses** - Uses OpenAI o4-mini reasoning model to synthesize answers from web search results
- 🔍 **Real-time web search** - Fetches current information using Brave Search API
- 💬 **Native Slack AI experience** - Leverages Slack's AI Apps & Assistants features
- ⚡ **Suggested prompts** - Provides helpful starter questions
- 📊 **Status indicators** - Shows "Searching the web..." while processing
- 🎨 **Rich Slack formatting** - Uses mrkdwn formatting with bold, italics, code blocks, and lists
- 🔗 **Numbered URL links** - Converts URLs to numbered hyperlinks like [1], [2], [3] for clean presentation
- 📎 **No link previews** - Disables Slack's automatic link unfurling for cleaner message appearance
- 🚀 **Socket Mode** - Easy local development without public URLs
- 🧠 **Advanced reasoning** - o4-mini's efficient reasoning capabilities for complex Dataiku questions

## Prerequisites

- Python 3.8+
- Slack workspace with admin permissions
- API keys for:
  - Slack (Bot and App tokens)
  - OpenAI API
  - Brave Search API

## Quick Start

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd dataiku-agent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click "Create New App"
2. Choose "From a manifest" 
3. Select your workspace
4. **Important**: The manifest editor has both YAML and JSON tabs. Use the appropriate tab:
   - For YAML: Copy the contents of `manifest.yml`
   - For JSON: Copy the contents of `manifest.json`
5. Paste the content in the correct tab
6. Review and create the app

### 4. Configure Tokens

After creating the app:

1. Go to **OAuth & Permissions** and install the app to your workspace
2. Copy the **Bot User OAuth Token** (starts with `xoxb-`)
3. Go to **Basic Information** (in the left sidebar)
4. Scroll down to **App-Level Tokens** section
5. Click **Generate Token and Scopes**
6. Give your token a name (e.g., "socket-mode-token")
7. Add the `connections:write` scope
8. Click **Generate**
9. Copy the **App-Level Token** (starts with `xapp-`)

### 5. Get API Keys

- **OpenAI**: Get your API key from [platform.openai.com](https://platform.openai.com)
- **Brave Search**: Get your API key from [brave.com/search/api](https://brave.com/search/api/)

### 6. Configure Environment

Create a `.env` file based on `env.example`:

```bash
cp env.example .env
```

Edit `.env` and add your tokens:

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
OPENAI_API_KEY=sk-your-openai-key
BRAVE_API_KEY=your-brave-api-key
```

### 7. Run the Bot

```bash
python src/app.py
```

You should see:
```
2025-01-XX ... starting_dataiku_agent bot_token_present=true app_token_present=true
2025-01-XX ... dataiku_agent_ready
```

## Usage

### In Slack

1. **Direct Message**: Message the bot directly
2. **Channel**: Add the bot to a channel and use the ⚡ AI assistant button
3. **Thread**: The bot will respond in AI assistant threads with:
   - Real-time status updates
   - Synthesized answers
   - Source citations
   - Suggested follow-up questions

### Example Questions

- "How do I build a visual recipe in Dataiku?"
- "What are the best practices for managing datasets in Dataiku?"
- "How can I schedule a scenario to run daily?"
- "Where can I find Dataiku plugins?"

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Slack     │────▶│  Dataiku    │────▶│   Brave     │
│   Client    │     │   Agent     │     │   Search    │
└─────────────┘     └─────────────┘     └─────────────┘
                            │                    
                            ▼                    
                    ┌─────────────┐              
                    │   OpenAI    │              
                    │ o4-mini Model│              
                    └─────────────┘              
```

### Key Components

- **Slack Bolt Framework**: Handles events and WebSocket connections
- **Assistant Class**: Manages AI thread interactions
- **Brave Search Integration**: Fetches relevant web results
- **OpenAI Integration**: Synthesizes coherent answers
- **Error Handling**: Graceful fallbacks for API failures

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token | Yes |
| `SLACK_APP_TOKEN` | App-Level Token for Socket Mode | Yes |
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `BRAVE_API_KEY` | Brave Search API key | Yes |
| `LOG_LEVEL` | Logging level (default: INFO) | No |
| `O3_REASONING_EFFORT` | o4-mini reasoning effort: "low", "medium", or "high" (default: medium) | No |

### Customization

You can customize the bot by modifying:

- **Suggested prompts**: Edit `SUGGESTED_PROMPTS` in `src/app.py`
- **System prompt**: Modify `SYSTEM_PROMPT` for different response styles
- **Search parameters**: Adjust Brave Search params in `search_brave()`
- **OpenAI model**: Change the model in `synthesize_answer()` (currently using o4-mini with medium reasoning effort)

## Deployment

### Google Cloud Run (Recommended)

**Two deployment options:**

#### GitHub Integration (Recommended)
Automatic deployments on every push to GitHub:

1. Set up secrets: `./deployment/setup-secrets.sh`
2. Connect your GitHub repo to Cloud Run in the console
3. Push code → Auto deploy! 🚀

See [deployment/GITHUB_DEPLOY.md](deployment/GITHUB_DEPLOY.md) for step-by-step instructions.

### Deployment Features

- 🐳 **Containerized**: Docker-based deployment
- 🔐 **Secure secrets**: Google Secret Manager integration
- 📊 **Monitoring**: Built-in logging and health checks
- 💰 **Cost-effective**: Scales to zero when idle
- 🚀 **Easy updates**: Single command redeployment

### Deployment Files

- `deployment/setup-secrets.sh` - Configure API keys securely
- `deployment/GITHUB_DEPLOY.md` - GitHub integration deployment guide
- `Dockerfile` - Container configuration
- `cloudbuild.yaml` - Cloud Build configuration

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Logging

The app uses structured logging with `structlog`. Logs include:
- Request/response timings
- Error details
- API usage metrics

### Error Handling

The bot handles:
- Brave Search quota limits
- OpenAI API errors
- Slack rate limits
- Network timeouts

## Troubleshooting

### Bot not responding

1. Check that Socket Mode is connected (look for "dataiku_agent_ready" in logs)
2. Verify the bot is added to the channel/conversation
3. Ensure all tokens are correctly set in `.env`

### API Errors

- **Brave Search**: Check your API quota at brave.com/search/api
- **OpenAI**: Verify your API key has credits. Note: o4-mini costs $1.10/1M input tokens, $4.40/1M output tokens
- **Slack**: Check rate limits (usually 20 req/sec)

### Debug Mode

Enable debug logging:
```env
LOG_LEVEL=DEBUG
```

## Security Considerations

- Never commit `.env` files
- Rotate tokens regularly
- Use environment-specific credentials
- Monitor API usage and costs

## Future Enhancements

- [ ] Streaming responses for faster feedback
- [ ] Caching frequent queries
- [ ] Integration with Dataiku APIs
- [ ] Custom knowledge base/RAG
- [ ] Analytics dashboard
- [ ] Multi-workspace support

## License

[Your License]

## Support

For issues or questions:
- Create an issue in this repository
- Contact: Chris Gannon

---

Built with ❤️ for the Dataiku community 