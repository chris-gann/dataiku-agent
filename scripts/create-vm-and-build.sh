#!/bin/bash

# Script to create GCP VM and set up Cloud Build for automated deployments
# Run this script locally to set up your infrastructure

set -e

echo "🚀 Setting up GCP VM and Cloud Build for Dataiku Agent..."

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI not found. Please install Google Cloud SDK."
    exit 1
fi

# Get project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: No Google Cloud project configured"
    echo "   Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo "📍 Using project: $PROJECT_ID"

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable compute.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable iap.googleapis.com

# Create firewall rules
echo "🔥 Creating firewall rules..."
gcloud compute firewall-rules create allow-dataiku-agent \
  --allow tcp:8080 \
  --source-ranges 0.0.0.0/0 \
  --description "Allow traffic to Dataiku agent" \
  --quiet || echo "Firewall rule already exists"

gcloud compute firewall-rules create allow-ssh \
  --allow tcp:22 \
  --source-ranges 0.0.0.0/0 \
  --description "Allow SSH access" \
  --quiet || echo "SSH firewall rule already exists"

# Create VM instance
echo "💻 Creating VM instance..."
gcloud compute instances create dataiku-agent-vm \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --machine-type=e2-medium \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-standard \
  --tags=http-server,https-server \
  --zone=us-central1-a \
  --metadata=startup-script='#!/bin/bash
apt update
apt install -y python3.11 python3.11-venv python3-pip git nginx supervisor curl
' \
  --quiet || echo "VM already exists"

# Wait for VM to be ready
echo "⏳ Waiting for VM to be ready..."
sleep 30

# Get VM external IP
VM_IP=$(gcloud compute instances describe dataiku-agent-vm \
  --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "🌐 VM External IP: $VM_IP"

# Create Cloud Build trigger
echo "🏗️  Creating Cloud Build trigger..."
gcloud builds triggers create github \
  --repo-name=dataiku_agent \
  --repo-owner=$(git config user.name) \
  --branch-pattern="^main$" \
  --build-config=cloudbuild.yaml \
  --description="Auto-deploy Dataiku Agent to VM on main branch push" \
  --quiet || echo "Build trigger may already exist"

echo ""
echo "✅ Infrastructure setup complete!"
echo ""
echo "🔧 Next steps to complete setup:"
echo ""
echo "1. SSH into the VM and run initial setup:"
echo "   gcloud compute ssh dataiku-agent-vm --zone=us-central1-a"
echo ""
echo "2. On the VM, run these commands:"
echo "   # Create application user"
echo "   sudo adduser --system --group --shell /bin/bash --home /opt/dataiku dataiku"
echo "   sudo mkdir -p /opt/dataiku && sudo chown dataiku:dataiku /opt/dataiku"
echo ""
echo "   # Switch to dataiku user and clone repo"
echo "   sudo -u dataiku -i"
echo "   cd /opt/dataiku"
echo "   git clone https://github.com/YOUR_USERNAME/dataiku_agent.git"
echo "   cd dataiku_agent"
echo ""
echo "   # Set up Python environment"
echo "   python3.11 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install -r requirements.txt"
echo ""
echo "   # Create environment file"
echo "   cp .env.example .env  # Edit with your API keys"
echo ""
echo "   # Exit dataiku user and install systemd service"
echo "   exit"
echo "   sudo cp /opt/dataiku/dataiku_agent/scripts/dataiku-agent.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable dataiku-agent"
echo "   sudo systemctl start dataiku-agent"
echo ""
echo "3. Configure Cloud Build to access your VM:"
echo "   # Grant Cloud Build SSH access"
echo "   gcloud projects add-iam-policy-binding $PROJECT_ID \\"
echo "     --member=serviceAccount:$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')@cloudbuild.gserviceaccount.com \\"
echo "     --role=roles/compute.instanceAdmin.v1"
echo ""
echo "   gcloud projects add-iam-policy-binding $PROJECT_ID \\"
echo "     --member=serviceAccount:$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')@cloudbuild.gserviceaccount.com \\"
echo "     --role=roles/iam.serviceAccountUser"
echo ""
echo "4. Update your Slack app webhook URL to: http://$VM_IP:8080/slack/events"
echo ""
echo "5. Test the deployment:"
echo "   git push origin main  # This should trigger auto-deployment"
echo ""
echo "🔍 Useful commands:"
echo "   VM Status:    gcloud compute instances list"
echo "   SSH to VM:    gcloud compute ssh dataiku-agent-vm --zone=us-central1-a"
echo "   Build logs:   gcloud builds log --stream"
echo "   VM health:    curl http://$VM_IP:8080/health"