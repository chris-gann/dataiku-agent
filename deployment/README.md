# Deployment Files

This folder contains deployment-related files for the Dataiku Agent.

## 📁 Files in this folder:

### `setup-secrets.sh`
Interactive script to securely store your API keys in Google Secret Manager.

**Usage:**
```bash
./deployment/setup-secrets.sh
```

You'll need to provide:
- Slack Bot Token (`xoxb-...`)
- Slack App Token (`xapp-...`) 
- OpenAI API Key (`sk-...`)
- Brave Search API Key

### `GITHUB_DEPLOY.md`
Complete step-by-step guide for setting up GitHub integration with Cloud Run.

This includes:
- Connecting your repository to Cloud Run
- Configuring automatic deployments
- Setting up secrets and environment variables
- Monitoring and troubleshooting

## 🚀 Quick Start

1. **Set up secrets first:**
   ```bash
   ./deployment/setup-secrets.sh
   ```

2. **Follow the GitHub integration guide:**
   ```bash
   cat deployment/GITHUB_DEPLOY.md
   ```

3. **Connect your repo to Cloud Run** using the Google Cloud Console

4. **Push code to trigger automatic deployment!**

## 🔧 Root-level deployment files:

- `Dockerfile` - Container configuration
- `cloudbuild.yaml` - Cloud Build pipeline configuration  
- `.gcloudignore` - Files to exclude from builds

These files must remain in the root directory for Cloud Build to find them.