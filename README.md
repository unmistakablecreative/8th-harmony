# 8th Harmony - OrchestrateOS

Your personal AI execution layer for seamless workflow automation.

## Quick Start

1. **Run the setup script:**
   ```bash
   ./setup.sh
   ```

2. **Start the server:**
   ```bash
   python3 jarvis.py
   ```

3. **Access the dashboard:**
   Open [http://localhost:5001](http://localhost:5001) in your browser

## What's Included

### Tools
- **Outline Editor** - Create and manage documents in Outline
- **Email (Nylas)** - Send, read, and manage emails
- **Calendar (Nylas)** - Manage calendar events and meetings
- **JSON Manager** - Read and write JSON data files
- **Terminal** - Execute terminal commands and scripts
- **System Settings** - Manage system configuration
- **Claude Assistant** - Queue tasks for Claude Code

### Key Files
- `jarvis.py` - FastAPI server and dashboard
- `execution_hub.py` - Tool orchestration and routing
- `system_settings.ndjson` - Tool registry and schemas
- `data/intent_routes.json` - Command shortcuts and workflows
- `data/dashboard_index.json` - Dashboard configuration

## Your Custom GPT

Configure your custom GPT to use this endpoint:
```
http://localhost:5001/get_supported_actions
```

This gives your GPT access to all registered tools and actions.

## Credentials

You'll need to set up:
- Nylas API credentials (email & calendar)
- Outline API credentials (document management)
- Anthropic API key (Claude assistant)

Add these to `tools/credentials.py`

## Support

Questions? Check the main OrchestrateOS docs or reach out to Srinivas.
