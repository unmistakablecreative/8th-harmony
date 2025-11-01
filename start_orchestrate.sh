#!/bin/bash

# OrchestrateOS Startup Script
# Makes starting the system dead simple

set -e

echo "========================================="
echo "🚀 Starting OrchestrateOS"
echo "========================================="
echo ""

# Get the directory where this script lives
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if we're in the right directory
if [ ! -f "jarvis.py" ]; then
    echo "❌ Error: Can't find jarvis.py"
    echo "Make sure you're running this from the OrchestrateOS directory"
    exit 1
fi

# First-time setup: Create alias for easy startup
SHELL_RC=""
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_RC="$HOME/.bash_profile"
fi

if [ -n "$SHELL_RC" ]; then
    # Check if alias already exists
    if ! grep -q "alias start-orchestrate=" "$SHELL_RC" 2>/dev/null; then
        echo ""
        echo "🔧 First-time setup detected!"
        echo "Adding 'start-orchestrate' command to your shell..."
        echo "" >> "$SHELL_RC"
        echo "# OrchestrateOS startup alias" >> "$SHELL_RC"
        echo "alias start-orchestrate=\"$SCRIPT_DIR/start_orchestrate.sh\"" >> "$SHELL_RC"
        echo "✅ Alias added! After this run, you can start OrchestrateOS from anywhere by typing:"
        echo "   start-orchestrate"
        echo ""
        echo "   (You may need to restart your terminal or run: source $SHELL_RC)"
        echo ""
    fi
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Virtual environment not found, creating one..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
    echo ""
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Install/update dependencies if needed
if [ -f "requirements.txt" ]; then
    echo "📚 Checking dependencies..."
    pip install -q -r requirements.txt
    echo "✅ Dependencies up to date"
    echo ""
fi

# Start the FastAPI server
echo "========================================="
echo "✅ OrchestrateOS is starting!"
echo "========================================="
echo ""
echo "Dashboard will be available at:"
echo "  http://localhost:5001"
echo ""
echo "To start the ngrok tunnel, open a NEW terminal and run:"
echo "  ngrok http --domain=bursting-buck-wired.ngrok-free.app 5001"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start uvicorn
uvicorn jarvis:app --host 0.0.0.0 --port 5001 --reload
