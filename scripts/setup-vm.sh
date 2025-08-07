#!/bin/bash
# VM Setup Script for Dataiku Agent
# Run this script on the VM after it's created

set -e

echo "Starting VM setup for Dataiku Agent..."

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3.11 python3.11-venv python3-pip git nginx supervisor curl

# Create application user
sudo adduser --system --group --shell /bin/bash --home /opt/dataiku dataiku

# Create application directory
sudo mkdir -p /opt/dataiku
sudo chown dataiku:dataiku /opt/dataiku

# Switch to application user and setup
sudo -u dataiku bash << 'EOF'
cd /opt/dataiku

# Clone the repository (you'll need to replace with your repo URL)
echo "Please clone your repository manually:"
echo "git clone https://github.com/YOUR_USERNAME/dataiku_agent.git"
echo "Or upload your files to /opt/dataiku/dataiku_agent/"

# For now, create the directory structure
mkdir -p dataiku_agent
cd dataiku_agent

# Create virtual environment when code is available
# python3.11 -m venv venv
# source venv/bin/activate
# pip install -r requirements.txt
EOF

echo "VM setup complete!"
echo "Next steps:"
echo "1. Clone your repository to /opt/dataiku/dataiku_agent/"
echo "2. Run the environment setup script"
echo "3. Configure the systemd service"