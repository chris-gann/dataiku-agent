# 🚀 GitHub Integration Deployment - Dataiku Agent

This guide shows you how to set up **automatic deployments** from your GitHub repository to Cloud Run. Every time you push to your main branch, your bot will automatically redeploy!

## 🎯 Why GitHub Integration is Better

✅ **Automatic deployments** - Push code → Auto deploy  
✅ **No manual scripts** - No need to run `./deploy.sh`  
✅ **Version history** - Track deployments in Cloud Console  
✅ **Easy rollbacks** - Rollback to any previous commit  
✅ **Team friendly** - Anyone on your team can deploy by pushing  

## 📋 Prerequisites

1. **Push your code to GitHub** (if you haven't already)
2. **Google Cloud account** with billing enabled
3. **Secrets set up** (we'll do this first)

## 🔐 Step 1: Set Up Secrets

First, let's set up your API keys in Google Secret Manager:

```bash
# Set your project
export GOOGLE_CLOUD_PROJECT="your-project-id"

# Run the secrets setup
./setup-secrets.sh
```

This creates secure secrets for:
- Slack Bot Token
- Slack App Token  
- OpenAI API Key
- Brave API Key

## 🔗 Step 2: Connect GitHub Repository

### Option A: Through Google Cloud Console (Recommended)

1. **Go to Cloud Run**: https://console.cloud.google.com/run
2. **Click "Create Service"**
3. **Select "Continuously deploy from a repository"**
4. **Click "Set up with Cloud Build"**
5. **Connect your GitHub repository**:
   - Select GitHub as source
   - Authorize Google Cloud Build
   - Choose your `dataiku_agent` repository
   - Select branch: `main` (or your default branch)
6. **Configure build**:
   - Build type: `Dockerfile`
   - Dockerfile location: `/Dockerfile`
   - Build context: `/` (root directory)

### Option B: Using gcloud CLI

```bash
# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Connect repository (this will open a browser)
gcloud builds triggers create github \
    --repo-name="dataiku_agent" \
    --repo-owner="your-github-username" \
    --branch-pattern="^main$" \
    --build-config="cloudbuild.yaml"
```

## ⚙️ Step 3: Configure the Service

In the Cloud Run setup wizard, configure:

**Service Settings:**
- Service name: `dataiku-agent`
- Region: `us-central1` (or your preferred region)

**Container Settings:**
- Port: `8080`
- Memory: `512 MiB`
- CPU: `1`

**Advanced Settings → Environment Variables:**
- `LOG_LEVEL` = `INFO`

**Advanced Settings → Security:**
- Authentication: `Allow unauthenticated invocations`

**Advanced Settings → Variables & Secrets:**
Add these secrets:
- `SLACK_BOT_TOKEN` → Secret: `slack-bot-token` (latest version)
- `SLACK_APP_TOKEN` → Secret: `slack-app-token` (latest version)  
- `OPENAI_API_KEY` → Secret: `openai-api-key` (latest version)
- `BRAVE_API_KEY` → Secret: `brave-api-key` (latest version)

## 🎉 Step 4: Deploy!

Click **"Create"** and Cloud Build will:

1. **Clone your repository**
2. **Build the Docker image** using your `Dockerfile`
3. **Deploy to Cloud Run**
4. **Set up the trigger** for future pushes

## 🔄 How It Works Going Forward

Now, every time you:
1. **Make changes** to your code
2. **Commit and push** to the main branch
3. **Cloud Build automatically**:
   - Builds a new container image
   - Deploys to Cloud Run
   - Routes traffic to the new version

## 📊 Monitor Your Deployments

### View Build History
```bash
gcloud builds list --limit=10
```

### View Service Status
```bash
gcloud run services describe dataiku-agent --region us-central1
```

### View Logs
```bash
gcloud logs tail --filter="resource.type=cloud_run_revision"
```

## 🛠️ Customizing the Build

You can customize the build process by editing `cloudbuild.yaml`:

```yaml
# Custom build with testing
steps:
  # Run tests first
  - name: 'python:3.11'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        pip install -r requirements.txt
        python -m pytest tests/ || exit 1
  
  # Build and deploy (existing steps)
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/dataiku-agent', '.']
  
  # ... rest of build steps
```

## 🔄 Managing Deployments

### Manual Trigger
Force a deployment without code changes:
```bash
gcloud builds triggers run YOUR_TRIGGER_NAME --branch=main
```

### Rollback to Previous Version
```bash
# List revisions
gcloud run revisions list --service=dataiku-agent --region=us-central1

# Rollback to a specific revision
gcloud run services update-traffic dataiku-agent \
    --to-revisions=REVISION_NAME=100 \
    --region=us-central1
```

### Pause Auto-Deployments
```bash
# Disable the trigger
gcloud builds triggers disable YOUR_TRIGGER_NAME

# Re-enable later
gcloud builds triggers enable YOUR_TRIGGER_NAME
```

## 🚨 Troubleshooting

### Build Failures

1. **Check build logs**:
   ```bash
   gcloud builds list --limit=5
   gcloud builds log BUILD_ID
   ```

2. **Common issues**:
   - Missing `Dockerfile` in repository root
   - Docker build errors (check your `Dockerfile`)
   - Missing secrets (ensure they're created in Secret Manager)

### Deployment Issues

1. **Service not starting**:
   ```bash
   gcloud run services describe dataiku-agent --region us-central1
   ```

2. **Check container logs**:
   ```bash
   gcloud logs tail --filter="resource.type=cloud_run_revision AND resource.labels.service_name=dataiku-agent"
   ```

## 💰 Cost Considerations

**Cloud Build Pricing:**
- First 120 build minutes/day are free
- $0.003 per build minute after that
- Your typical build takes 2-5 minutes

**Storage:**
- Container images stored in Container Registry
- ~$0.05/GB/month (images are typically 100-500MB)

## 🎯 Next Steps

1. **Test the deployment** by pushing a small change
2. **Set up branch protection** in GitHub (optional)
3. **Configure notifications** for build failures
4. **Set up monitoring** alerts in Google Cloud

## 📚 Additional Resources

- [Cloud Build GitHub Integration](https://cloud.google.com/build/docs/automating-builds/github/connect-repo-github)
- [Cloud Run Continuous Deployment](https://cloud.google.com/run/docs/continuous-deployment-with-cloud-build)
- [Managing Build Triggers](https://cloud.google.com/build/docs/automating-builds/github/build-repos-from-github)

---

🎉 **You now have a professional CI/CD pipeline!** Every code push automatically deploys your bot with zero manual intervention.