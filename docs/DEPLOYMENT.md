# Production Deployment Guide

This guide covers deploying Dataiku Agent to production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Configuration](#configuration)
4. [Deployment Options](#deployment-options)
5. [Security Best Practices](#security-best-practices)
6. [Monitoring and Observability](#monitoring-and-observability)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

- Python 3.9+ (recommended: 3.11)
- Redis (optional, for caching)
- Docker (for containerized deployment)
- Valid API keys for:
  - Slack (Bot and App tokens)
  - OpenAI
  - Brave Search

## Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/dataiku-agent.git
cd dataiku-agent
```

### 2. Create Virtual Environment (Non-Docker)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

### Environment Variables

The application can be configured via environment variables or a JSON config file.

Required environment variables:
- `SLACK_BOT_TOKEN`: Your Slack bot token (xoxb-...)
- `SLACK_APP_TOKEN`: Your Slack app token (xapp-...)
- `OPENAI_API_KEY`: Your OpenAI API key
- `BRAVE_API_KEY`: Your Brave Search API key

Optional variables:
- `ENVIRONMENT`: Set to `production` for production deployment
- `REDIS_URL`: Redis connection URL (if using Redis cache)
- `SENTRY_DSN`: Sentry DSN for error tracking
- `LOG_LEVEL`: Logging level (default: INFO)

### JSON Configuration

For production, you can use a JSON config file:

```bash
cp config/production.json.example config/production.json
# Edit config/production.json with your settings
```

Run with config file:
```bash
python -m src.main --config config/production.json
```

## Deployment Options

### Option 1: Docker (Recommended)

#### Build the Image

```bash
docker build -t dataiku-agent:latest .
```

#### Run with Docker

```bash
docker run -d \
  --name dataiku-agent \
  -e SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN \
  -e SLACK_APP_TOKEN=$SLACK_APP_TOKEN \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e BRAVE_API_KEY=$BRAVE_API_KEY \
  -e ENVIRONMENT=production \
  -p 8080:8080 \
  -p 9090:9090 \
  dataiku-agent:latest
```

#### Using Docker Compose

```bash
# Create .env file with your credentials
cp .env.example .env
# Edit .env with your values

# Start services
docker-compose up -d

# View logs
docker-compose logs -f dataiku-agent
```

### Option 2: Systemd Service (Linux)

Create `/etc/systemd/system/dataiku-agent.service`:

```ini
[Unit]
Description=Dataiku Agent for Slack
After=network.target

[Service]
Type=simple
User=dataiku-agent
Group=dataiku-agent
WorkingDirectory=/opt/dataiku-agent
Environment="PATH=/opt/dataiku-agent/venv/bin"
ExecStart=/opt/dataiku-agent/venv/bin/python -m src.main
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/dataiku-agent/data /opt/dataiku-agent/logs

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable dataiku-agent
sudo systemctl start dataiku-agent
```

### Option 3: Kubernetes

See `k8s/` directory for Kubernetes manifests.

```bash
# Create namespace
kubectl create namespace dataiku-agent

# Create secrets
kubectl create secret generic dataiku-agent-secrets \
  --from-literal=slack-bot-token=$SLACK_BOT_TOKEN \
  --from-literal=slack-app-token=$SLACK_APP_TOKEN \
  --from-literal=openai-api-key=$OPENAI_API_KEY \
  --from-literal=brave-api-key=$BRAVE_API_KEY \
  -n dataiku-agent

# Apply manifests
kubectl apply -f k8s/ -n dataiku-agent
```

## Security Best Practices

### 1. API Key Management

- **Never commit API keys** to version control
- Use a secrets management service (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate keys regularly (every 90 days recommended)
- Use separate keys for different environments

### 2. Network Security

- Run the application behind a firewall
- Use TLS/SSL for all external communications
- Restrict health check and metrics endpoints to internal networks only

### 3. Access Control

- Limit bot permissions to only necessary Slack scopes
- Use channel allowlists to restrict where the bot can operate
- Implement user blocklists for suspicious accounts

### 4. Data Protection

- Enable Redis password authentication
- Encrypt sensitive data at rest
- Implement log sanitization to remove sensitive information

### 5. Container Security

- Run containers as non-root user
- Use minimal base images
- Scan images for vulnerabilities regularly
- Keep dependencies updated

## Monitoring and Observability

### Health Checks

The application exposes health check endpoints:

- `GET /health` - Comprehensive health status
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe

### Metrics

Prometheus metrics are exposed at `/metrics` on port 9090.

Key metrics to monitor:
- Request rate and latency
- API call success/failure rates
- Cache hit rates
- Token usage and costs

### Logging

Configure centralized logging:

```bash
# For JSON logs in production
export LOG_LEVEL=INFO
export ENVIRONMENT=production
```

Logs include:
- Request IDs for tracing
- User and channel information
- API response times
- Error details with stack traces

### Alerting

Set up alerts for:
- High error rates (> 5% of requests)
- API rate limit approaching
- Service unavailability
- High token usage/costs

## Troubleshooting

### Common Issues

#### 1. Bot Not Responding

Check:
- Socket Mode connection status
- API tokens are valid
- Bot has correct permissions
- Health check endpoint

```bash
curl http://localhost:8080/health
```

#### 2. Rate Limiting

Symptoms:
- 429 errors in logs
- Slow responses

Solutions:
- Implement caching (Redis)
- Adjust rate limit settings
- Use burst tokens wisely

#### 3. High Costs

Monitor token usage:
```bash
curl http://localhost:9090/metrics | grep openai_tokens
```

Optimize by:
- Reducing `max_completion_tokens`
- Using lower reasoning effort
- Implementing aggressive caching

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
export ENVIRONMENT=development
```

### Performance Tuning

1. **Cache Configuration**
   - Use Redis for production
   - Adjust TTL based on content freshness needs
   - Monitor cache hit rates

2. **Rate Limiting**
   - Configure appropriate limits per service
   - Use burst capacity for spikes
   - Implement backoff strategies

3. **Connection Pooling**
   - Reuse HTTP connections
   - Configure appropriate pool sizes
   - Monitor connection usage

## Backup and Recovery

### Data Backup

Regular backups should include:
- Configuration files
- Redis data (if persistent)
- Logs for compliance

### Disaster Recovery

1. **Multi-region deployment** for high availability
2. **Automated failover** using health checks
3. **Regular disaster recovery drills**

## Compliance and Auditing

- Enable audit logging for all bot actions
- Implement data retention policies
- Regular security audits
- Compliance with data protection regulations (GDPR, etc.)

## Support

For production support:
1. Check health endpoints
2. Review logs for errors
3. Monitor metrics dashboards
4. Contact support team with request IDs 