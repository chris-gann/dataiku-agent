#!/bin/bash
set -e

# Dataiku Agent - Google Secret Manager Setup Script
# This script helps you create the required secrets for the Dataiku Agent

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-""}

echo -e "${BLUE}🔑 Dataiku Agent - Secret Manager Setup${NC}"
echo "=========================================="

# Check if PROJECT_ID is set
if [[ -z "$PROJECT_ID" ]]; then
    echo -e "${RED}❌ Error: GOOGLE_CLOUD_PROJECT environment variable is not set${NC}"
    echo "Please run: export GOOGLE_CLOUD_PROJECT=your-project-id"
    exit 1
fi

echo -e "${BLUE}📋 Project ID: ${PROJECT_ID}${NC}"
echo ""

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ Error: gcloud CLI is not installed${NC}"
    echo "Please install it from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Set the project
gcloud config set project $PROJECT_ID

# Enable Secret Manager API
echo -e "${YELLOW}🔌 Enabling Secret Manager API...${NC}"
gcloud services enable secretmanager.googleapis.com

# Function to create a secret
create_secret() {
    local secret_name=$1
    local secret_description=$2
    local example_value=$3
    
    echo -e "${YELLOW}🔐 Setting up secret: ${secret_name}${NC}"
    echo "Description: $secret_description"
    
    if gcloud secrets describe $secret_name &> /dev/null; then
        echo -e "${GREEN}✅ Secret '$secret_name' already exists${NC}"
        read -p "Do you want to update it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Skipping $secret_name"
            return
        fi
    else
        echo -e "${BLUE}📝 Creating new secret: $secret_name${NC}"
        gcloud secrets create $secret_name --replication-policy="automatic"
    fi
    
    echo "Example format: $example_value"
    echo -e "${YELLOW}Please enter your $secret_name value (input will be hidden):${NC}"
    read -s secret_value
    echo
    
    if [[ -n "$secret_value" ]]; then
        echo "$secret_value" | gcloud secrets versions add $secret_name --data-file=-
        echo -e "${GREEN}✅ Secret '$secret_name' has been set${NC}"
    else
        echo -e "${RED}❌ No value provided for $secret_name${NC}"
    fi
    
    echo ""
}

# Create all required secrets
echo -e "${BLUE}📚 We need to create 4 secrets for your Dataiku Agent:${NC}"
echo ""

create_secret "slack-bot-token" \
    "Bot User OAuth Token from your Slack app" \
    "xoxb-YOUR-BOT-TOKEN-HERE"

create_secret "slack-app-token" \
    "App-Level Token for Socket Mode from your Slack app" \
    "xapp-YOUR-APP-TOKEN-HERE"

create_secret "openai-api-key" \
    "OpenAI API key for o4-mini model" \
    "sk-YOUR-OPENAI-KEY-HERE"

create_secret "brave-api-key" \
    "Brave Search API key" \
    "BSA-YOUR-BRAVE-KEY-HERE"

echo -e "${GREEN}🎉 Secret setup completed!${NC}"
echo "================================="
echo ""
echo -e "${YELLOW}💡 Next steps:${NC}"
echo "  1. Run ./deploy.sh to deploy your bot to Cloud Run"
echo "  2. Your secrets are now securely stored in Google Secret Manager"
echo "  3. The Cloud Run service will automatically access these secrets"
echo ""
echo -e "${BLUE}🔍 To view your secrets later:${NC}"
echo "  gcloud secrets list"
echo "  gcloud secrets versions list <secret-name>"
echo ""
echo -e "${BLUE}🗑️  To delete a secret:${NC}"
echo "  gcloud secrets delete <secret-name>"
echo ""