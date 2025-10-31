#!/bin/bash

# 8th Harmony - OrchestrateOS Setup Script
# Run this script once to set up your Orchestrate environment

set -e  # Exit on any error

echo "========================================="
echo "8th Harmony - OrchestrateOS Setup"
echo "========================================="
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ This setup script is designed for macOS"
    exit 1
fi

# Check Python version
echo "→ Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "✓ Found Python $PYTHON_VERSION"
echo ""

# Install Python dependencies
echo "→ Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt
    echo "✓ Python dependencies installed"
else
    echo "⚠️  No requirements.txt found, skipping..."
fi
echo ""

# Install Claude Code CLI
echo "→ Checking for Claude Code installation..."
if command -v claude &> /dev/null; then
    echo "✓ Claude Code is already installed"
else
    echo "→ Installing Claude Code..."
    brew install claude

    if [ $? -eq 0 ]; then
        echo "✓ Claude Code installed successfully"
    else
        echo "❌ Failed to install Claude Code"
        echo "   Please install manually: brew install claude"
        exit 1
    fi
fi
echo ""

# Create necessary directories
echo "→ Creating required directories..."
mkdir -p data/canvas
mkdir -p outline_docs_queue
echo "✓ Directories created"
echo ""

# Initialize data files if they don't exist
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

# Check for required credentials
echo "→ Checking credentials..."
if [ ! -f "tools/credentials.py" ]; then
    echo "⚠️  credentials.py not found"
    echo "   You'll need to set up your API credentials:"
    echo "   - Nylas API credentials for email/calendar"
    echo "   - Outline API credentials for document management"
    echo "   - Anthropic API key for Claude"
fi
echo ""

# Start the FastAPI server
echo "========================================="
echo "✓ Setup Complete!"
echo "========================================="
echo ""
echo "To start OrchestrateOS:"
echo "  python3 jarvis.py"
echo ""
echo "The dashboard will be available at:"
echo "  http://localhost:5001"
echo ""
echo "Your custom GPT should be configured to use:"
echo "  http://localhost:5001/get_supported_actions"
echo ""
echo "Happy Orchestrating! 🎵"
