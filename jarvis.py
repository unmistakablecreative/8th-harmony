from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import subprocess, json, os, logging

from tools import json_manager
from tools.smart_json_dispatcher import orchestrate_write
from system_guard import validate_action, ContractViolation

# ✅ Modular engine launcher (pulls from engine_registry.json)
from tools.engine_launcher import launch_all_engines

app = FastAPI()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 🔒 System paths
SYSTEM_REGISTRY = os.path.join(BASE_DIR, "system_settings.ndjson")
WORKING_MEMORY_PATH = os.path.join(BASE_DIR, "data/working_memory.json")
EXEC_HUB_PATH = os.path.join(BASE_DIR, "execution_hub.py")
DASHBOARD_INDEX_PATH = os.path.join(BASE_DIR, "data/dashboard_index.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 📦 Static mounts
app.mount(
    "/semantic_memory",
    StaticFiles(directory=os.path.join(BASE_DIR, "semantic_memory")),
    name="semantic_memory"
)

app.mount(
    "/landing_page_template_thumbnails",
    StaticFiles(directory=os.path.join(BASE_DIR, "landing_page_template_thumbnails")),
    name="landing_page_template_thumbnails"
)

# 🚀 Startup: Launch all engines dynamically
@app.on_event("startup")
def start_all_engines():
    try:
        launch_all_engines()
    except Exception as e:
        logging.error(f"🚨 Failed to launch engines: {e}")

# 🛠 Run a tool action via subprocess
def run_script(tool_name, action, params):
    command = [
        "python3", EXEC_HUB_PATH, "execute_task", "--params", json.dumps({
            "tool_name": tool_name,
            "action": action,
            "params": params
        })
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": "Execution failed", "details": str(e)}

# 🎯 Execute a tool via HTTP POST
@app.post("/execute_task")
async def execute_task(request: Request):
    try:
        request_data = await request.json()
        tool_name = request_data.get("tool_name")
        action_name = request_data.get("action")
        params = request_data.get("params", {})

        if not tool_name or not action_name:
            raise HTTPException(status_code=400, detail="Missing tool_name or action.")

        # 🧠 Handle orchestrate reset
        if tool_name == "system_control" and action_name == "load_orchestrate_os":
            result = subprocess.run(
                ["python3", EXEC_HUB_PATH, "load_orchestrate_os"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return json.loads(result.stdout.strip())

        # ✨ Smart dispatcher override
        if tool_name == "json_manager" and action_name == "orchestrate_write":
            return orchestrate_write(**params)

        # 🔒 Validate + execute
        params = validate_action(tool_name, action_name, params)
        result = run_script(tool_name, action_name, params)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result)

        return result

    except ContractViolation as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": "Execution failed",
            "details": str(e)
        })

# 🚀 Load dashboard data dynamically from dashboard_index.json
def load_dashboard_data():
    """Load dashboard using config-driven approach"""
    try:
        # Load dashboard configuration
        with open(DASHBOARD_INDEX_PATH, 'r', encoding='utf-8') as f:
            dashboard_config = json.load(f)
        
        dashboard_data = {}
        
        # Process each dashboard item
        for item in dashboard_config.get("dashboard_items", []):
            key = item.get("key")
            source_type = item.get("source")
            
            try:
                if source_type == "file":
                    # Load from file
                    filepath = os.path.join(BASE_DIR, item.get("file"))
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        dashboard_data[key] = data
                        
                elif source_type == "tool_action":
                    # Load from tool execution
                    tool_name = item.get("tool")
                    action = item.get("action")
                    params = item.get("params", {})
                    result = run_script(tool_name, action, params)
                    dashboard_data[key] = result
                    
            except Exception as e:
                dashboard_data[key] = {"error": f"Could not load {key}: {str(e)}"}
        
        # Format the data for display using config
        formatted_output = format_dashboard_display(dashboard_data, dashboard_config)
        
        return {
            "status": "success", 
            "dashboard_data": formatted_output
        }
        
    except Exception as e:
        return {"error": f"Failed to load dashboard: {str(e)}"}

def format_dashboard_display(data, config):
    """Convert JSON data to formatted output based on config"""
    formatted = {}
    
    for item in config.get("dashboard_items", []):
        key = item.get("key")
        formatter = item.get("formatter")
        display_type = item.get("display_type")
        
        if key not in data:
            continue
            
        raw_data = data[key]
        
        # Apply formatter
        if formatter == "intent_routes_table":
            formatted[key] = format_intent_routes(raw_data)
        elif formatter == "calendar_list":
            formatted[key] = format_calendar_events(raw_data)
        elif formatter == "thread_log_list":
            formatted[key] = format_thread_log(raw_data, item.get("limit", 5))
        elif formatter == "ideas_list":
            formatted[key] = format_ideas_reminders(raw_data, item.get("limit", 10))
        else:
            # Default: just pass through
            formatted[key] = raw_data
    
    return formatted

# 📊 Individual formatters
def format_intent_routes(data):
    """Format intent routes as table + full data"""
    if not isinstance(data, dict):
        return {"display_table": "No data", "entries": {}}
    
    routes_data = data.get("entries", {})
    intent_table = "| Icon | Intent | Description | Tool | Action |\n|------|--------|-------------|------|--------|\n"
    
    for key, route in routes_data.items():
        if isinstance(route, dict):
            icon = route.get("icon", "") or route.get("updates", {}).get("icon", "") or route.get("update", {}).get("icon", "") or "🔧"
            intent = route.get("intent", key)
            description = route.get("description", "")[:60]
            tool_name = route.get("tool_name", "")
            action = route.get("action", "")
            intent_table += f"| {icon} | {intent} | {description} | {tool_name} | {action} |\n"
    
    return {
        "display_table": intent_table,
        "entries": routes_data
    }

def format_calendar_events(data):
    """Format calendar events as list"""
    events = []
    
    if isinstance(data, dict):
        if "events" in data:
            events = data["events"]
        elif "data" in data:
            events = data["data"]
    elif isinstance(data, list):
        events = data
    
    if events:
        cal_list = "📅 **Calendar Events:**\n\n"
        for event in events[:5]:
            title = event.get("title", "No title")
            when = event.get("when", {})
            start_time = when.get("start_time", when.get("start", ""))
            if isinstance(start_time, (int, float)):
                start_time = datetime.fromtimestamp(start_time).strftime("%m/%d %H:%M")
            cal_list += f"• **{start_time}**: {title}\n"
        return cal_list
    else:
        return "📅 **Calendar Events:** No upcoming events"

def format_thread_log(data, limit=5):
    """Format thread log as list"""
    if not isinstance(data, dict):
        return "📋 **Thread Log:** No entries"
    
    entries_data = data.get("entries", data)
    if entries_data:
        thread_list = "📋 **Thread Log:**\n\n"
        for key, entry in list(entries_data.items())[-limit:]:
            status = entry.get("status", "unknown").upper()
            goal = entry.get("context_goal", key)[:60]
            thread_list += f"• **{status}**: {goal}\n"
        return thread_list
    else:
        return "📋 **Thread Log:** No entries"

def format_ideas_reminders(data, limit=10):
    """Format ideas and reminders as list"""
    if not isinstance(data, dict):
        return "💡 **Ideas & Reminders:** No entries"
    
    entries_data = data.get("entries", data)
    if entries_data:
        ideas_list = "💡 **Ideas & Reminders:**\n\n"
        for key, item in list(entries_data.items())[-limit:]:
            if isinstance(item, dict):
                item_type = item.get("type", "idea")
                title = item.get("title", item.get("content", key))[:60]
                ideas_list += f"• **{item_type.title()}**: {title}\n"
            else:
                ideas_list += f"• **Idea**: {str(item)[:60]}\n"
        return ideas_list
    else:
        return "💡 **Ideas & Reminders:** No entries"

# 📖 Return supported tool/actions ONLY
@app.get("/get_supported_actions")
def get_supported_actions():
    """Returns registry with param schemas only - no example bloat"""
    try:
        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]
        
        lean_actions = []
        
        for entry in entries:
            if entry.get("action") == "__tool__":
                continue
            
            lean_entry = {
                "tool": entry.get("tool"),
                "action": entry.get("action"),
                "params": entry.get("params", []),
                "description": entry.get("description", "")[:100]  # Slightly longer
            }
            
            lean_actions.append(lean_entry)
        
        return {
            "status": "success",
            "supported_actions": lean_actions,
            "total": len(lean_actions)
        }
        
    except Exception as e:
        logging.error(f"Failed to load registry: {e}")
        raise HTTPException(status_code=500, detail="Could not load registry.")


# 📋 Get dashboard files on demand
@app.get("/get_dashboard_file/{file_key}")
def get_dashboard_file(file_key: str):
    """Load specific dashboard files when needed or full dashboard"""
    
    # Special case: full dashboard
    if file_key == "full_dashboard":
        dashboard = load_dashboard_data()
        return dashboard
    
    # Individual files
    file_map = {
        "phrase_promotions": "data/phrase_insight_promotions.json",
        "runtime_contract": "orchestrate_runtime_contract.json", 
        "tool_build_protocol": "data/tool_build_protocol.json",
        "podcast_prep_rules": "podcast_prep_guidelines.json",
        "thread_log_full": "data/thread_log.json",
        "ideas_and_reminders_full": "data/ideas_reminders.json"
    }
    
    if file_key not in file_map:
        raise HTTPException(status_code=404, detail=f"File key '{file_key}' not found")
    
    try:
        filepath = file_map[file_key]
        abs_path = os.path.join(BASE_DIR, filepath)
        
        with open(abs_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return {
            "status": "success",
            "file_key": file_key,
            "data": data
        }
        
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": f"Could not load {file_key}",
            "details": str(e)
        })


# 📖 Return supported tool/actions ONLY
@app.get("/get_supported_actions")
def get_supported_actions(offset: int = 0, limit: int = 50):
    """Return actions in chunks - auto-paginate"""
    try:
        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]
        
        lean_actions = []
        for entry in entries:
            if entry.get("action") == "__tool__":
                continue
            
            lean_entry = {
                "tool": entry.get("tool"),
                "action": entry.get("action"),
                "params": entry.get("params", []),
                "description": entry.get("description", "")[:100]
            }
            lean_actions.append(lean_entry)
        
        # Paginate
        total = len(lean_actions)
        paginated = lean_actions[offset:offset+limit]
        
        return {
            "status": "success",
            "supported_actions": paginated,
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "returned": len(paginated),
                "has_more": (offset + limit) < total,
                "next_offset": offset + limit if (offset + limit) < total else None
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 🧠 Load working memory
@app.post("/load_memory")
def load_memory():
    """Build real-time contract cache WITHOUT bloated examples"""
    try:
        # Load persistent working memory
        memory_path = os.path.join(BASE_DIR, "data/working_memory.json")
        working_memory = {}
        if os.path.exists(memory_path):
            with open(memory_path, "r") as f:
                working_memory = json.load(f)
        
        # Load param corrections from JSON file
        corrections_path = os.path.join(BASE_DIR, "data/param_corrections.json")
        with open(corrections_path, "r") as f:
            param_corrections = json.load(f)
        
        # Build LEAN contract cache from registry
        with open(SYSTEM_REGISTRY, "r") as f:
            registry_entries = [json.loads(line.strip()) for line in f if line.strip()]
        
        contract_cache = {}
        for entry in registry_entries:
            if entry.get("action") != "__tool__":
                tool_action = f"{entry['tool']}.{entry['action']}"
                contract_cache[tool_action] = {
                    "required_params": entry.get("params", []),
                    # NO EXAMPLE - GPT can construct payload from params list
                    "description": entry.get("description", "")[:100]  # Truncated
                }
        
        return {
            "status": "success",
            "working_memory": working_memory,
            "contract_cache": contract_cache,
            "param_corrections": param_corrections,
            "loaded_contracts": len(contract_cache),
            "memory_entries": len(working_memory),
            "refresh_timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": f"Failed to build contract cache: {str(e)}"}

# 🔌 Health check
@app.get("/")
def root():
    return {"status": "Jarvis core is online."}