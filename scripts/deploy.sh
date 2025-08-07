#!/bin/bash

# VM Deployment script for Dataiku Agent
# This script is executed on the VM by Cloud Build for automated deployments

set -e

echo "🚀 Deploying Dataiku Agent to VM..."

# Log deployment start
logger "dataiku-agent: Starting deployment from git"

# Change to application directory
cd /opt/dataiku/dataiku_agent

# Pull latest changes
echo "📦 Pulling latest code from git..."
git fetch origin
git reset --hard origin/main

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Run tests (optional - comment out if you want faster deployments)
echo "🧪 Running tests..."
python -m pytest tests/ -v || {
    echo "⚠️  Tests failed but continuing deployment..."
    logger "dataiku-agent: Tests failed during deployment"
}

# Restart the service
echo "🔄 Restarting dataiku-agent service..."
sudo systemctl restart dataiku-agent

# Check service status
echo "🔍 Checking service status..."
sleep 5
if sudo systemctl is-active --quiet dataiku-agent; then
    echo "✅ Service is running successfully!"
    logger "dataiku-agent: Deployment completed successfully"
else
    echo "❌ Service failed to start!"
    logger "dataiku-agent: Deployment failed - service not running"
    sudo systemctl status dataiku-agent
    exit 1
fi

echo "✅ VM Deployment completed successfully!"
echo ""
echo "🔍 Monitoring commands:"
echo "   Check service: sudo systemctl status dataiku-agent"
echo "   View logs:     sudo journalctl -u dataiku-agent -f"
echo "   Check health:  curl http://localhost:8080/health"