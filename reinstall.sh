#!/bin/bash

# OrchestrateOS Reinstall Script
# Backs up credentials, pulls fresh code, restores everything

set -e

echo "========================================="
echo "OrchestrateOS Reinstall"
echo "========================================="
echo ""

# 1. Backup credentials if they exist
echo "→ Backing up credentials..."
if [ -f ~/OrchestrateOS/tools/credentials.json ]; then
    cp ~/OrchestrateOS/tools/credentials.json ~/creds_backup.json
    echo "✓ Credentials backed up to ~/creds_backup.json"
else
    echo "⚠️  No existing credentials found (first-time install)"
fi
echo ""

# 2. Remove old installation
echo "→ Removing old installation..."
if [ -d ~/OrchestrateOS ]; then
    rm -rf ~/OrchestrateOS
    echo "✓ Old installation removed"
else
    echo "⚠️  No existing installation found"
fi
echo ""

# 3. Clone fresh repo
echo "→ Cloning fresh OrchestrateOS from GitHub..."
git clone https://github.com/unmistakablecreative/8th-harmony.git ~/OrchestrateOS
cd ~/OrchestrateOS
echo "✓ Fresh code downloaded"
echo ""

# 4. Restore credentials
echo "→ Restoring credentials..."
if [ -f ~/creds_backup.json ]; then
    cp ~/creds_backup.json tools/credentials.json
    rm ~/creds_backup.json
    echo "✓ Credentials restored"
else
    echo "⚠️  No credentials to restore (you'll need to set them up)"
fi
echo ""

# 5. Install Python dependencies
echo "→ Installing Python dependencies..."
python3 -m pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# 6. Create necessary directories
echo "→ Creating required directories..."
mkdir -p data/canvas
mkdir -p outline_docs_queue
mkdir -p semantic_memory
echo "✓ Directories created"
echo ""

# 7. Initialize data files if they don't exist
echo "→ Initializing data files..."
[ -f "data/claude_task_queue.json" ] || echo '[]' > data/claude_task_queue.json
[ -f "data/claude_task_results.json" ] || echo '[]' > data/claude_task_results.json
[ -f "data/automation_state.json" ] || echo '{}' > data/automation_state.json
[ -f "data/execution_log.json" ] || echo '[]' > data/execution_log.json
[ -f "data/working_context.json" ] || echo '{}' > data/working_context.json
[ -f "data/thread_state.json" ] || echo '{}' > data/thread_state.json
[ -f "data/thread_intent.json" ] || echo '{}' > data/thread_intent.json
echo "✓ Data files initialized"
echo ""

# 8. All done!
echo "========================================="
echo "✓ Installation Complete!"
echo "========================================="
echo ""
echo "To start OrchestrateOS:"
echo "  cd ~/OrchestrateOS"
echo "  python3 engine_launcher.py"
echo ""
echo "The dashboard will be available at:"
echo "  http://localhost:5001"
echo ""
echo "Happy Orchestrating! 🎵"
