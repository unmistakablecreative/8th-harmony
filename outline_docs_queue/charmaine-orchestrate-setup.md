# Setting Up Your OrchestrateOS Upgrade

## Before We Start

You're getting a completely refreshed version of OrchestrateOS with:
- 6 core tools (down from 40+)
- Clean slate - no old data or clutter
- Automated setup script
- Updated dashboard with only what you need

## What You'll Need

1. **API Credentials** (we'll set these up together):
   - Nylas API credentials (for email & calendar)
   - Outline API credentials (for document management)
   - Anthropic API key (for Claude)

2. **Your Mac** with:
   - Python 3.8 or higher (you likely already have this)
   - Homebrew installed (for Claude Code CLI)

## Setup Steps

### 1. Get the Code

Clone your personal OrchestrateOS repository:

```bash
git clone https://github.com/unmistakablecreative/8th-harmony.git
cd 8th-harmony
```

### 2. Run the Setup Script

This one command does everything - installs dependencies, sets up Claude Code CLI, creates necessary directories:

```bash
./setup.sh
```

If you get a "permission denied" error, run:
```bash
chmod +x setup.sh
./setup.sh
```

### 3. Add Your Credentials

We'll add your API credentials to `tools/credentials.py`. I'll help you with this part in person - it's just copying and pasting a few keys.

### 4. Start OrchestrateOS

```bash
python3 jarvis.py
```

The dashboard will open at: **http://localhost:5001**

### 5. Configure Your Custom GPT

Update your custom GPT to point to:
```
http://localhost:5001/get_supported_actions
```

This gives your GPT access to all 6 tools we've set up for you.

## Your 6 Core Tools

### 1. **Outline Editor** - Document Management
- Create docs from queue
- Search docs
- Update existing docs
- List all docs

### 2. **Email (Nylas)** - Email Operations
- Check recent emails
- Send emails
- Reply to messages
- Search your inbox
- Delete emails

### 3. **Calendar (Nylas)** - Schedule Management
- List upcoming events
- Book new events
- Delete events
- See all your calendars

### 4. **JSON Manager** - Data File Operations
- Read JSON files
- Add/update/delete entries
- Search entries
- List all entries

### 5. **Terminal** - File & Command Operations
- Run terminal commands
- Read/write text files
- List files in directories
- Find files by keyword

### 6. **Claude Assistant** - Task Queue for Claude Code
- Assign tasks to Claude
- Check task status
- Get task results
- Process queue

## How to Use It

### Via the Dashboard (http://localhost:5001)

The dashboard shows all your available commands. Just click to execute, or use them as reference for what's possible.

### Via Your Custom GPT

Just talk naturally to your GPT:
- "Check my email"
- "Create an Outline doc about [topic]"
- "What's on my calendar this week?"
- "Send an email to [person] about [topic]"

Your GPT knows how to route these requests to the right tools.

## What's Different from Last Time

### Cleaner
- Removed 2,035 files you weren't using
- Only 6 tools instead of 40+
- Fresh data files - no old execution logs

### Faster Setup
- One command (`./setup.sh`) does everything
- No manual dependency installation
- Auto-installs Claude Code CLI

### Better Intent Routing
- Updated to match the latest tool implementations
- All schemas are correct and tested
- Dashboard shows exactly what you can do

## File Structure

```
8th-harmony/
├── setup.sh              # Run this first
├── jarvis.py             # FastAPI server (starts dashboard)
├── execution_hub.py      # Routes commands to tools
├── system_settings.ndjson # Tool registry
├── data/
│   ├── intent_routes.json    # Dashboard commands
│   ├── claude_task_queue.json
│   ├── execution_log.json
│   └── working_context.json
└── tools/
    ├── outline_editor.py
    ├── nylas_inboxv2.py
    ├── nylas_calendar.py
    ├── json_manager.py
    ├── terminal_tool.py
    ├── system_settings.py
    └── claude_assistant.py
```

## Troubleshooting

### "Command not found: python3"
Try `python --version` - you might have Python installed as `python` instead of `python3`.

### "Permission denied" on setup.sh
Run: `chmod +x setup.sh` then try again.

### Dashboard won't load
Make sure jarvis.py is running. You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:5001
```

### Custom GPT can't connect
- Make sure jarvis.py is running
- Try accessing http://localhost:5001/get_supported_actions in your browser
- You should see a JSON response with all available tools

## Next Steps After Setup

1. **Test each tool** - Use the dashboard to verify everything works
2. **Configure your GPT** - Point it to the new endpoint
3. **Try a workflow** - "Check my email and create an Outline doc summarizing anything important"

## Getting Help

If something breaks or you're not sure how to do something:
1. Check the execution log: `data/execution_log.json`
2. Ask your GPT - it has access to all the tool documentation
3. Text me - I can debug remotely or we can hop on a call

---

**Welcome to your upgraded OrchestrateOS. Let's make some magic happen.**