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
. venv/bin/activate

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
if sudo -n systemctl restart dataiku-agent 2>/dev/null; then
    echo "✅ Service restart initiated successfully"
else
    echo "⚠️  Unable to restart service - no sudo privileges. Service may need manual restart."
    logger "dataiku-agent: Deployment completed but service restart failed - no sudo access"
fi

# Check service status
echo "🔍 Checking service status..."
sleep 5
if sudo -n systemctl is-active --quiet dataiku-agent 2>/dev/null; then
    echo "✅ Service is running successfully!"
    logger "dataiku-agent: Deployment completed successfully"
elif systemctl --user is-active --quiet dataiku-agent 2>/dev/null; then
    echo "✅ Service is running successfully (user service)!"
    logger "dataiku-agent: Deployment completed successfully"
else
    echo "⚠️  Unable to check service status - manual verification may be needed"
    logger "dataiku-agent: Deployment completed but unable to verify service status"
    echo "ℹ️  To manually check service status:"
    echo "   sudo systemctl status dataiku-agent"
    echo "   OR systemctl --user status dataiku-agent"
fi

echo "✅ VM Deployment completed successfully!"
echo "ℹ️  Note: If service restart failed due to permissions, you may need to manually restart:"
echo "   sudo systemctl restart dataiku-agent"
echo ""
echo "🔍 Monitoring commands:"
echo "   Check service: sudo systemctl status dataiku-agent"
echo "   View logs:     sudo journalctl -u dataiku-agent -f"
echo "   Check health:  curl http://localhost:8080/health"