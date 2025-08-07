#!/bin/bash

# Deploy script for testing performance optimizations
# This script deploys the performance branch to Cloud Run for testing

set -e

echo "🚀 Deploying Dataiku Agent Performance Optimizations..."

# Get the current git branch
CURRENT_BRANCH=$(git branch --show-current)
echo "📍 Current branch: $CURRENT_BRANCH"

if [ "$CURRENT_BRANCH" != "performance" ]; then
    echo "⚠️  Warning: You're not on the 'performance' branch!"
    echo "   Current branch: $CURRENT_BRANCH"
    echo "   Expected branch: performance"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Deployment cancelled"
        exit 1
    fi
fi

# Check if we have uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Warning: You have uncommitted changes!"
    echo "   Please commit your changes before deploying"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Deployment cancelled"
        exit 1
    fi
fi

# Get project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: No Google Cloud project configured"
    echo "   Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "📦 Building and deploying to project: $PROJECT_ID"

# Submit the build
echo "🔨 Starting Cloud Build..."
gcloud builds submit --config cloudbuild.yaml

echo "✅ Deployment completed successfully!"
echo ""
echo "🔍 Monitoring commands:"
echo "   View logs:    gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=dataiku-agent' --limit=50 --format='table(timestamp,textPayload)'"
echo "   Check status: gcloud run services describe dataiku-agent --region=us-west1"
echo "   View URL:     gcloud run services describe dataiku-agent --region=us-west1 --format='value(status.url)'"
echo ""
echo "📊 Performance testing tips:"
echo "   1. Check time_to_ack_ms in logs (should be < 1000ms)"
echo "   2. Monitor total_duration_ms for end-to-end processing"
echo "   3. Watch for cold start indicators (new instanceId in logs)"
echo "   4. Test concurrent requests to verify improved throughput"
echo ""
echo "🎯 Key improvements in this deployment:"
echo "   ✓ Gunicorn production server (vs Flask dev server)"
echo "   ✓ Optimized Cloud Run configuration (concurrency: 4, min-instances: 2)"
echo "   ✓ Immediate ACK pattern with background processing"
echo "   ✓ Enhanced performance logging and monitoring"
echo "   ✓ Optimized Docker image for faster cold starts"
echo "   ✓ Retry logic for external API calls"