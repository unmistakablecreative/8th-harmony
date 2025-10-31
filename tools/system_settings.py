# ✅ REFACTORED system_settings.py — fully Execution Hub–compatible, handles .md files, returns consistent output

import os
import json
import argparse
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TOOLS_DIR, ".."))

SETTINGS_FILE = os.path.join(ROOT_DIR, "system_settings.ndjson")
CREDENTIALS_FILE = os.path.join(TOOLS_DIR, "credentials.json")
MEMORY_INDEX_FILE = os.path.join(ROOT_DIR, "memory_index.json")
ROUTER_MAP_FILE = os.path.join(TOOLS_DIR, "router_map.json")
WORKING_MEMORY_PATH = os.path.join(ROOT_DIR, "data", "working_memory.json")
DASHBOARD_INDEX_PATH = os.path.join(ROOT_DIR, "data", "dashboard_index.json")

def output(data):
    print(json.dumps(data, indent=2))
    sys.exit(0)

def error(message):
    print(json.dumps({"status": "error", "message": message}, indent=2))
    sys.exit(1)

# === Credentials ===
def set_credential(params):
    import os
    import json
    import re

    value = params.get("value")
    script_path = params.get("script_path")

    if not value:
        return {"status": "error", "message": "❌ Missing 'value' in params"}
    if not script_path:
        return {"status": "error", "message": "❌ Missing 'script_path' in params"}
    
    # Handle both absolute and relative paths
    if not os.path.isabs(script_path):
        script_path = os.path.join(os.getcwd(), script_path)
    
    if not os.path.exists(script_path):
        return {"status": "error", "message": f"❌ Script not found: {script_path}"}

    expected_keys = set()

    try:
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()

        # ✅ Targeted pattern matching - only catch specific credential access patterns
        patterns = [
            # load_credential("key") or load_credential('key') - most reliable
            r'load_credential\([\'"]([a-zA-Z0-9_]{3,40})[\'"]\)',
            
            # creds.get("key") or creds.get('key') - reliable
            r'creds\.get\([\'"]([a-zA-Z0-9_]{3,40})[\'"]\)',
            
            # creds["key"] or creds['key'] - reliable
            r'creds\[[\'"]([a-zA-Z0-9_]{3,40})[\'"]\]',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match and len(match) >= 5:
                    # Filter out ONLY overly generic single-word keys
                    if match.lower() not in ['api_key', 'token', 'secret', 'access_token', 'key', 'value', 'creds', 'credential']:
                        # If it has an underscore OR ends with common suffixes, it's valid
                        if '_' in match or any(match.lower().endswith(suffix) for suffix in ['_api_key', '_token', '_secret', '_key', 'api_key', 'token', 'secret']):
                            expected_keys.add(match)

    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to parse script: {str(e)}"}

    if not expected_keys:
        return {
            "status": "error",
            "message": "❌ No credential keys found in script. Supported patterns: load_credential(), creds.get(), creds[]"
        }

    # === Inject into credentials.json ===
    creds_path = os.path.join(os.path.dirname(script_path), "credentials.json")
    if not os.path.exists(creds_path):
        # Try the tools directory as fallback
        creds_path = "tools/credentials.json"
        if not os.path.exists(creds_path):
            creds_path = "credentials.json"
    
    creds = {}
    if os.path.exists(creds_path):
        try:
            with open(creds_path, "r") as f:
                creds = json.load(f)
        except:
            creds = {}

    # Set all found keys to the same value
    for key in expected_keys:
        creds[key] = value

    with open(creds_path, "w") as f:
        json.dump(creds, f, indent=2)

    return {
        "status": "success",
        "keys_set": list(expected_keys),
        "credentials_file": creds_path,
        "message": f"✅ Credential injected into: {', '.join(expected_keys)}"
    }



def load_credential(key):
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    with open(CREDENTIALS_FILE, "r") as f:
        creds = json.load(f)
    return creds.get(key)


# === Tool Registry ===
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return []
    with open(SETTINGS_FILE, "r") as f:
        return [json.loads(line) for line in f if line.strip()]

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        for entry in data:
            f.write(json.dumps(entry) + "\n")

def add_tool(params):
    tool, path = params.get("tool"), params.get("path")
    if not tool or not path:
        error("Missing 'tool' or 'path'")

    entry = {
        "tool": tool,
        "action": "__tool__",
        "script_path": path
    }

    # ✅ Optional lock flags
    if "locked" in params:
        entry["locked"] = params["locked"]
    if "referral_unlock_cost" in params:
        entry["referral_unlock_cost"] = params["referral_unlock_cost"]

    data = load_settings()
    data.append(entry)
    save_settings(data)

    return {"status": "success", "message": f"Tool '{tool}' registered."}


def remove_tool(params):
    tool = params.get("tool")
    if not tool:
        error("Missing 'tool'")
    data = load_settings()
    updated = [d for d in data if d["tool"] != tool]
    save_settings(updated)
    return {"status": "success", "message": f"Tool '{tool}' and all actions removed."}

def list_tools(_):
    return {"status": "success", "tools": [d for d in load_settings() if d["action"] == "__tool__"]}


def add_action(params):
    required = ["tool", "action", "script", "params", "example"]
    if not all(k in params for k in required):
        error("Missing one of: tool, action, script, params, example")
    
    data = load_settings()
    
    # Add the new action
    data.append({
        "tool": params["tool"],
        "action": params["action"],
        "script_path": params["script"],
        "params": params["params"],
        "example": params["example"]
    })
    
    # 🔧 Sort all actions: first by tool, then by action name
    data.sort(key=lambda x: (x["tool"], x["action"]))
    
    save_settings(data)
    
    return {"status": "success", "message": f"Action '{params['action']}' added to '{params['tool']}'."}

def remove_action(params):
    tool = params.get("tool")
    action = params.get("action")
    if not tool or not action:
        error("Missing 'tool' or 'action'")
    data = load_settings()
    updated = [d for d in data if not (d["tool"] == tool and d["action"] == action)]
    save_settings(updated)
    return {"status": "success", "message": f"Action '{action}' removed from tool '{tool}'."}


def list_actions(params):
    tool = params.get("tool")
    all_actions = [d for d in load_settings() if d["action"] != "__tool__"]
    return {"status": "success", "actions": [a for a in all_actions if a["tool"] == tool] if tool else all_actions}


# === Memory Index ===

def load_memory_index():
    """Load memory_index.json and return the 'entries' list. Compatible with schema and legacy list fallback."""
    if not os.path.exists(MEMORY_INDEX_FILE):
        return []
    try:
        with open(MEMORY_INDEX_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict) and "entries" in data:
                return data["entries"]
            elif isinstance(data, list):
                return data  # legacy fallback
    except Exception:
        return []
    return []

def save_memory_index(index):
    """Always write valid schema: { 'entries': [ ... ] }"""
    with open(MEMORY_INDEX_FILE, "w") as f:
        json.dump({"entries": index}, f, indent=2)

def add_memory_file(params):
    path = params.get("path")
    if not path:
        error("Missing 'path'")
    index = load_memory_index()
    if path not in index:
        index.append(path)
        save_memory_index(index)
    return {"status": "success", "message": f"Memory file '{path}' added."}

def remove_memory_file(params):
    path = params.get("path")
    if not path:
        error("Missing 'path'")
    index = load_memory_index()
    if path in index:
        index.remove(path)
        save_memory_index(index)
        return {"status": "success", "message": f"Memory file '{path}' removed."}
    return {"status": "error", "message": f"File '{path}' not found in memory index."}

def list_memory_files(_):
    return {"status": "success", "memory_files": load_memory_index()}

def build_working_memory(_):
    index = load_memory_index()
    memory = {}

    for rel_path in index:
        key = rel_path if not rel_path.startswith("/") else os.path.relpath(rel_path, ROOT_DIR)
        abs_path = os.path.join(ROOT_DIR, rel_path) if not os.path.isabs(rel_path) else rel_path

        if not os.path.exists(abs_path):
            memory[key] = f"<<ERROR: File not found — {rel_path}>>"
            continue

        try:
            with open(abs_path, "r") as f:
                if abs_path.endswith(".ndjson"):
                    memory[key] = [json.loads(line) for line in f if line.strip()]
                elif abs_path.endswith(".json"):
                    memory[key] = json.load(f)
                else:
                    memory[key] = f.read()
        except Exception as e:
            memory[key] = f"<<ERROR: {str(e)}>>"

    os.makedirs(os.path.dirname(WORKING_MEMORY_PATH), exist_ok=True)
    with open(WORKING_MEMORY_PATH, "w") as f:
        json.dump(memory, f, indent=2)

    return {
        "status": "success",
        "message": f"Working memory rebuilt clean at {WORKING_MEMORY_PATH}"
    }


# === Dashboard Index Management ===

def load_dashboard_index():
    """Load dashboard_index.json"""
    if not os.path.exists(DASHBOARD_INDEX_PATH):
        return {"dashboard_items": [], "config": {}}
    try:
        with open(DASHBOARD_INDEX_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"dashboard_items": [], "config": {}}

def save_dashboard_index(data):
    """Save dashboard_index.json"""
    os.makedirs(os.path.dirname(DASHBOARD_INDEX_PATH), exist_ok=True)
    with open(DASHBOARD_INDEX_PATH, "w") as f:
        json.dump(data, f, indent=2)

def add_dashboard_item(params):
    """
    Add new dashboard item
    Required: key, source, display_type, formatter
    Optional: file (if source=file), tool/action/params (if source=tool_action), 
              priority, limit, description, enabled
    """
    key = params.get("key")
    source = params.get("source")
    
    if not key or not source:
        return {"status": "error", "message": "Missing 'key' or 'source'"}
    
    if source not in ["file", "tool_action"]:
        return {"status": "error", "message": "source must be 'file' or 'tool_action'"}
    
    dashboard = load_dashboard_index()
    
    # Check if key already exists
    if any(item.get("key") == key for item in dashboard["dashboard_items"]):
        return {"status": "error", "message": f"Dashboard item '{key}' already exists"}
    
    # Build new item
    new_item = {
        "key": key,
        "source": source,
        "display_type": params.get("display_type", "raw"),
        "formatter": params.get("formatter", "passthrough"),
        "priority": params.get("priority", len(dashboard["dashboard_items"]) + 1),
        "enabled": params.get("enabled", True)
    }
    
    # Add source-specific fields
    if source == "file":
        if "file" not in params:
            return {"status": "error", "message": "Missing 'file' path for file source"}
        new_item["file"] = params["file"]
        
        # Validate file exists
        file_path = os.path.join(ROOT_DIR, params["file"])
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"File not found: {params['file']}"}
    
    elif source == "tool_action":
        if "tool" not in params or "action" not in params:
            return {"status": "error", "message": "Missing 'tool' or 'action' for tool_action source"}
        new_item["tool"] = params["tool"]
        new_item["action"] = params["action"]
        new_item["params"] = params.get("params", {})
        
        # Validate tool/action exists in registry
        settings = load_settings()
        tool_exists = any(
            s.get("tool") == params["tool"] and s.get("action") == params["action"]
            for s in settings
        )
        if not tool_exists:
            return {"status": "error", "message": f"Tool action '{params['tool']}.{params['action']}' not found in registry"}
    
    # Optional fields
    if "limit" in params:
        new_item["limit"] = params["limit"]
    if "description" in params:
        new_item["description"] = params["description"]
    
    dashboard["dashboard_items"].append(new_item)
    
    # Sort by priority
    dashboard["dashboard_items"].sort(key=lambda x: x.get("priority", 999))
    
    save_dashboard_index(dashboard)
    
    return {
        "status": "success",
        "message": f"✅ Dashboard item '{key}' added",
        "item": new_item
    }

def remove_dashboard_item(params):
    """Remove dashboard item by key"""
    key = params.get("key")
    if not key:
        return {"status": "error", "message": "Missing 'key'"}
    
    dashboard = load_dashboard_index()
    original_count = len(dashboard["dashboard_items"])
    
    dashboard["dashboard_items"] = [
        item for item in dashboard["dashboard_items"] 
        if item.get("key") != key
    ]
    
    if len(dashboard["dashboard_items"]) == original_count:
        return {"status": "error", "message": f"Dashboard item '{key}' not found"}
    
    save_dashboard_index(dashboard)
    
    return {
        "status": "success",
        "message": f"✅ Dashboard item '{key}' removed"
    }

def update_dashboard_item(params):
    """
    Update existing dashboard item
    Required: key
    Optional: Any field to update (source, file, tool, action, display_type, formatter, priority, etc.)
    """
    key = params.get("key")
    if not key:
        return {"status": "error", "message": "Missing 'key'"}
    
    dashboard = load_dashboard_index()
    item_found = False
    
    for item in dashboard["dashboard_items"]:
        if item.get("key") == key:
            item_found = True
            
            # Update all provided fields except 'key'
            for param_key, param_value in params.items():
                if param_key != "key":
                    item[param_key] = param_value
            
            # Validate if source changed
            if "source" in params:
                source = params["source"]
                if source == "file" and "file" not in item:
                    return {"status": "error", "message": "Cannot change to file source without 'file' field"}
                elif source == "tool_action" and ("tool" not in item or "action" not in item):
                    return {"status": "error", "message": "Cannot change to tool_action source without 'tool' and 'action' fields"}
            
            break
    
    if not item_found:
        return {"status": "error", "message": f"Dashboard item '{key}' not found"}
    
    # Re-sort by priority
    dashboard["dashboard_items"].sort(key=lambda x: x.get("priority", 999))
    
    save_dashboard_index(dashboard)
    
    return {
        "status": "success",
        "message": f"✅ Dashboard item '{key}' updated"
    }

def reorder_dashboard(params):
    """
    Bulk reorder dashboard items by priority
    Accepts: {"ordering": [{"key": "intent_routes", "priority": 1}, ...]}
    """
    ordering = params.get("ordering")
    if not ordering or not isinstance(ordering, list):
        return {"status": "error", "message": "Missing or invalid 'ordering' list"}
    
    dashboard = load_dashboard_index()
    
    # Create priority map
    priority_map = {item["key"]: item["priority"] for item in ordering}
    
    # Update priorities
    for item in dashboard["dashboard_items"]:
        if item["key"] in priority_map:
            item["priority"] = priority_map[item["key"]]
    
    # Sort by new priorities
    dashboard["dashboard_items"].sort(key=lambda x: x.get("priority", 999))
    
    save_dashboard_index(dashboard)
    
    return {
        "status": "success",
        "message": f"✅ Reordered {len(priority_map)} dashboard items"
    }

def list_dashboard_items(_):
    """Return full dashboard configuration"""
    dashboard = load_dashboard_index()
    return {
        "status": "success",
        "dashboard": dashboard
    }

def toggle_dashboard_item(params):
    """Enable or disable dashboard item without deleting"""
    key = params.get("key")
    enabled = params.get("enabled")
    
    if not key:
        return {"status": "error", "message": "Missing 'key'"}
    if enabled is None:
        return {"status": "error", "message": "Missing 'enabled' (true/false)"}
    
    dashboard = load_dashboard_index()
    item_found = False
    
    for item in dashboard["dashboard_items"]:
        if item.get("key") == key:
            item["enabled"] = enabled
            item_found = True
            break
    
    if not item_found:
        return {"status": "error", "message": f"Dashboard item '{key}' not found"}
    
    save_dashboard_index(dashboard)
    
    status_text = "enabled" if enabled else "disabled"
    return {
        "status": "success",
        "message": f"✅ Dashboard item '{key}' {status_text}"
    }


# === Existing Functions Continue Below ===

def install_tool(params):
    import ast
    import os

    ROOT_DIR = os.getcwd()
    script_path = params.get("script_path")
    if not script_path:
        return {"status": "error", "message": "Missing 'script_path'"}

    abs_path = os.path.join(ROOT_DIR, script_path)
    if not os.path.exists(abs_path):
        return {"status": "error", "message": f"Script path not found: {abs_path}"}

    module_name = os.path.splitext(os.path.basename(abs_path))[0]

    tool_entry = {
        "tool": module_name,
        "action": "__tool__",
        "script_path": script_path
    }

    settings = load_settings()
    settings.append(tool_entry)

    try:
        with open(abs_path, "r") as f:
            code = f.read()
    except Exception as e:
        return {"status": "error", "message": f"Failed to read script: {str(e)}"}

    def extract_actions_with_params(script_text):
        tree = ast.parse(script_text)
        actions = []

        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef)
                and not node.name.startswith("_")
                and node.name != "main"
            ):
                param_keys = set()

                for child in ast.walk(node):
                    # Match: params.get("key")
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr == "get"
                        and isinstance(child.func.value, ast.Name)
                        and child.func.value.id == "params"
                    ):
                        if child.args and isinstance(child.args[0], ast.Str):
                            param_keys.add(child.args[0].s)

                    # Match: params["key"]
                    elif (
                        isinstance(child, ast.Subscript)
                        and isinstance(child.value, ast.Name)
                        and child.value.id == "params"
                        and isinstance(child.slice, ast.Constant)
                        and isinstance(child.slice.value, str)
                    ):
                        param_keys.add(child.slice.value)

                actions.append({
                    "action": node.name,
                    "params": sorted(param_keys)
                })

        return actions

    extracted = extract_actions_with_params(code)
    actions = []
    for act in extracted:
        actions.append({
            "tool": module_name,
            "action": act["action"],
            "script_path": script_path,
            "params": act["params"],
            "example": {
                "tool_name": module_name,
                "action": act["action"],
                "params": {k: f"<{k}>" for k in act["params"]}
            }
        })

    settings.extend(actions)
    save_settings(settings)

    return {
        "status": "success",
        "message": f"✅ Installed tool '{module_name}' with {len(actions)} actions.",
        "actions": [a["action"] for a in actions]
    }


def list_supported_actions(_):
    data = load_settings()
    return {"status": "success", "supported_actions": data}


def refresh_orchestrate_runtime(_):
    import os
    import requests
    import json
    import ast
    from pathlib import Path

    ROOT_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = ROOT_DIR / "data"
    TOOLS_DIR = ROOT_DIR / "tools"
    SETTINGS_PATH = ROOT_DIR / "system_settings.ndjson"

    BASE_RAW = "https://raw.githubusercontent.com/unmistakablecreative/orchestrate-core-runtime/main/"
    GITHUB_API_TOOLS = "https://api.github.com/repos/unmistakablecreative/orchestrate-core-runtime/contents/tools"

    results = []
    updated = 0
    new_actions = []

    # === Refresh app store and updates ===
    data_files = {
        "data/orchestrate_app_store.json": DATA_DIR / "orchestrate_app_store.json",
        "data/update_messages.json": DATA_DIR / "update_messages.json"
    }

    for remote_path, local_path in data_files.items():
        try:
            url = BASE_RAW + remote_path
            response = requests.get(url)
            response.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(response.text)
            results.append(f"✅ Refreshed {remote_path}")
        except Exception as e:
            results.append(f"❌ Failed to refresh {remote_path}: {e}")

    # === Load app store metadata ===
    try:
        with open(DATA_DIR / "orchestrate_app_store.json", "r") as f:
            app_store = json.load(f).get("entries", {})
    except Exception as e:
        app_store = {}
        results.append(f"❌ Failed to load app store: {e}")

    # === Ensure credentials.json exists ===
    creds_path = TOOLS_DIR / "credentials.json"
    if not creds_path.exists():
        creds_path.write_text("{}")
        results.append("🛡️ Created blank credentials.json")
    else:
        results.append("⏭️ Skipped credentials.json (already exists)")

    # === Load existing settings
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, "r") as f:
            existing_lines = f.readlines()
        try:
            settings = [json.loads(line) for line in existing_lines]
        except Exception as e:
            results.append(f"❌ Failed to parse system_settings.ndjson: {e}")
            settings = []
    else:
        settings = []

    existing_keys = {(s["tool"], s["action"]) for s in settings}

    # === Helper: extract function defs ===
    def extract_actions(path):
        with open(path, "r") as f:
            tree = ast.parse(f.read())
        return [
            {"action": node.name, "params": [arg.arg for arg in node.args.args if arg.arg != "_"]}
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
        ]

    # === Pull and process tool scripts ===
    try:
        tool_entries = requests.get(GITHUB_API_TOOLS).json()
        for entry in tool_entries:
            name = entry.get("name", "")
            if not name.endswith(".py") or name == "credentials.json":
                continue

            tool_name = name.replace(".py", "")
            is_marketplace = tool_name in app_store
            is_free = app_store.get(tool_name, {}).get("referral_unlock_cost", 1) == 0

            # ✅ Skip locked marketplace tools (don't even download them)
            if is_marketplace and not is_free:
                results.append(f"⏭️ Skipped locked marketplace tool: {tool_name}")
                continue

            # ✅ Only download allowed tools
            try:
                tool_code = requests.get(entry["download_url"]).text
                tool_path = TOOLS_DIR / name
                tool_path.write_text(tool_code)
                results.append(f"🔁 Updated tool: {name}")
                updated += 1

                # === Extract + register actions
                actions = extract_actions(tool_path)
                for act in actions:
                    key = (tool_name, act["action"])
                    if key not in existing_keys:
                        entry_obj = {
                            "tool": tool_name,
                            "action": act["action"],
                            "script_path": f"tools/{name}",
                            "params": act["params"]
                        }
                        settings.append(entry_obj)
                        existing_keys.add(key)
                        new_actions.append(f"{tool_name}.{act['action']}")

            except Exception as e:
                results.append(f"❌ Failed to process {name}: {e}")
    except Exception as e:
        results.append(f"❌ Could not fetch tools list: {e}")

    # === Save merged system_settings.ndjson ===
    try:
        with open(SETTINGS_PATH, "w") as f:
            for entry in settings:
                f.write(json.dumps(entry) + "\n")
        results.append(f"✅ Saved merged system_settings.ndjson with {len(settings)} actions")
    except Exception as e:
        results.append(f"❌ Failed to write system_settings.ndjson: {e}")

    summary = f"🧩 {updated} tools updated | ➕ {len(new_actions)} new actions registered"
    results.append(summary)

    return {
        "status": "complete" if updated or new_actions else "noop",
        "messages": results
    }


def register_engine(params):
    """
    Register a new background engine script to engine_registry.json
    so it gets launched automatically on server startup.
    Accepts: {"engine_path": "filename.py"}
    """
    import os, json
    path = "data/engine_registry.json"
    engine_path = params.get("engine_path")

    if not engine_path:
        return {"status": "error", "message": "❌ Missing 'engine_path' in params."}

    if not os.path.exists(path):
        engines = {"engines": [engine_path]}
    else:
        with open(path, "r", encoding="utf-8") as f:
            engines = json.load(f)
        if engine_path not in engines.get("engines", []):
            engines["engines"].append(engine_path)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(engines, f, indent=2)

    return {"status": "success", "message": f"✅ Engine '{engine_path}' registered."}


def update_action(params):
    tool = params.get("tool")
    action = params.get("action")
    if not tool or not action:
        return {"status": "error", "message": "Missing 'tool' or 'action'"}

    data = load_settings()
    updated = False

    for entry in data:
        if entry.get("tool") == tool and entry.get("action") == action:
            for k, v in params.items():
                if k not in ["tool", "action"]:
                    entry[k] = v
            updated = True
            break

    if not updated:
        return {"status": "error", "message": f"Action '{action}' not found for tool '{tool}'"}

    save_settings(data)
    return {
        "status": "success",
        "message": f"Action '{action}' for tool '{tool}' updated."
    }


def update_custom_instructions(params):
    """
    Update custom_instructions.json with clean nested updates.
    Perfect for modifying commands, addendums, instructions, etc.
    """
    import os
    import json
    
    path = "data/custom_instructions.json"
    updates = params.get("content", {})
    
    try:
        with open(path, "r") as f:
            existing = json.load(f)
    except FileNotFoundError:
        existing = {"commands": {}}
    
    def deep_merge(target, source):
        """Recursively merge source into target, preserving existing structure"""
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                deep_merge(target[key], value)
            else:
                target[key] = value
    
    # Merge the updates into existing structure
    deep_merge(existing, updates)
    
    # Write back to file
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    
    return {
        "status": "success", 
        "message": f"✅ Updated custom_instructions.json",
        "structure": "nested"
    }



def add_to_memory(params):
    """
    Adds or updates a memory entry in data/working_memory.json.
    Accepts a params dict with 'entry_key' and 'entry_data'.
    """
    import os, json
    path = "data/working_memory.json"

    entry_key = params["entry_key"]
    entry_data = params["entry_data"]

    if os.path.exists(path):
        with open(path, "r") as f:
            memory = json.load(f)
    else:
        memory = {}

    memory[entry_key] = entry_data

    with open(path, "w") as f:
        json.dump(memory, f, indent=2)

    return {"status": "success", "message": f"Entry '{entry_key}' added to memory."}


def get_working_memory(params):
    """
    Returns the full contents of data/working_memory.json.
    Accepts an unused params dict for tool compatibility.
    """
    import os, json
    path = "data/working_memory.json"

    if not os.path.exists(path):
        return {"status": "success", "memory": {}}

    with open(path, "r") as f:
        memory = json.load(f)

    return {"status": "success", "memory": memory}


def clear_memory(params):
    """
    Clears all entries in data/working_memory.json by resetting to an empty dict.
    Accepts a dummy params dict for compatibility.
    """
    import json
    path = "data/working_memory.json"

    with open(path, "w") as f:
        json.dump({}, f, indent=2)

    return {"status": "success", "message": "Working memory cleared."}

def activate_intent(params):
    import os
    import json
    import time
    
    intent_key = params.get("intent_key")
    if not intent_key:
        return {"status": "error", "message": "Missing 'intent_key'"}
    
    registry_path = os.path.join(ROOT_DIR, "data", "intent_registry.json")
    if not os.path.exists(registry_path):
        return {"status": "error", "message": "Intent registry not found"}
    
    with open(registry_path, "r") as f:
        registry = json.load(f)
    
    if intent_key not in registry:
        return {
            "status": "error", 
            "message": f"Intent '{intent_key}' not found",
            "available_intents": list(registry.keys())
        }
    
    intent_config = registry[intent_key]
    
    thread_intent = {
        "active": True,
        "intent": intent_key,
        "allowed_tools": intent_config["allowed_tools"],
        "description": intent_config["description"],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "violations_count": 0
    }
    
    intent_path = os.path.join(ROOT_DIR, "data", "thread_intent.json")
    os.makedirs(os.path.dirname(intent_path), exist_ok=True)
    with open(intent_path, "w") as f:
        json.dump(thread_intent, f, indent=2)
    
    return {
        "status": "success",
        "intent": intent_key,
        "allowed_tools": intent_config["allowed_tools"],
        "message": f"✅ Intent '{intent_key}' activated. Tool access restricted."
    }


def deactivate_intent(params):
    import os
    import json
    import time
    
    thread_intent = {
        "active": False,
        "intent": "free_work",
        "allowed_tools": "*",
        "description": "No restrictions",
        "deactivated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "violations_count": 0
    }
    
    intent_path = os.path.join(ROOT_DIR, "data", "thread_intent.json")
    with open(intent_path, "w") as f:
        json.dump(thread_intent, f, indent=2)
    
    return {
        "status": "success",
        "message": "✅ Intent lock deactivated. All tools available."
    }


def get_active_intent(params):
    import os
    import json
    
    intent_path = os.path.join(ROOT_DIR, "data", "thread_intent.json")
    
    if not os.path.exists(intent_path):
        return {
            "status": "success",
            "active": False,
            "intent": "free_work",
            "message": "No active intent lock"
        }
    
    with open(intent_path, "r") as f:
        intent = json.load(f)
    
    return {
        "status": "success",
        **intent
    }


def list_available_intents(params):
    import os
    import json
    
    registry_path = os.path.join(ROOT_DIR, "data", "intent_registry.json")
    
    if not os.path.exists(registry_path):
        return {"status": "error", "message": "Intent registry not found"}
    
    with open(registry_path, "r") as f:
        registry = json.load(f)
    
    return {
        "status": "success",
        "intents": registry,
        "count": len(registry)
    }

# === Dispatcher Functions (Phase 1 Refactor) ===

def manage_tool(params):
    """
    Unified tool management dispatcher.
    Operations: add, remove, list
    """
    operation = params.get("operation")

    if operation == "add":
        return add_tool(params)
    elif operation == "remove":
        return remove_tool(params)
    elif operation == "list":
        return list_tools(params)
    else:
        return {
            "status": "error",
            "message": f"Invalid operation: {operation}. Valid operations: add, remove, list"
        }

def manage_action(params):
    """
    Unified action management dispatcher.
    Operations: add, remove, list, update
    """
    operation = params.get("operation")

    if operation == "add":
        return add_action(params)
    elif operation == "remove":
        return remove_action(params)
    elif operation == "list":
        return list_actions(params)
    elif operation == "update":
        return update_action(params)
    else:
        return {
            "status": "error",
            "message": f"Invalid operation: {operation}. Valid operations: add, remove, list, update"
        }

def manage_dashboard(params):
    """
    Unified dashboard management dispatcher.
    Operations: add, remove, update, reorder, list, toggle
    """
    operation = params.get("operation")

    if operation == "add":
        return add_dashboard_item(params)
    elif operation == "remove":
        return remove_dashboard_item(params)
    elif operation == "update":
        return update_dashboard_item(params)
    elif operation == "reorder":
        return reorder_dashboard(params)
    elif operation == "list":
        return list_dashboard_items(params)
    elif operation == "toggle":
        return toggle_dashboard_item(params)
    else:
        return {
            "status": "error",
            "message": f"Invalid operation: {operation}. Valid operations: add, remove, update, reorder, list, toggle"
        }

def manage_intent(params):
    """
    Unified intent management dispatcher.
    Operations: activate, deactivate, get_active, list
    """
    operation = params.get("operation")

    if operation == "activate":
        return activate_intent(params)
    elif operation == "deactivate":
        return deactivate_intent(params)
    elif operation == "get_active":
        return get_active_intent(params)
    elif operation == "list":
        return list_available_intents(params)
    else:
        return {
            "status": "error",
            "message": f"Invalid operation: {operation}. Valid operations: activate, deactivate, get_active, list"
        }

def manage_memory(params):
    """
    Unified memory management dispatcher.
    Operations: add, remove, list, clear
    """
    operation = params.get("operation")

    if operation == "add":
        return add_memory_file(params)
    elif operation == "remove":
        return remove_memory_file(params)
    elif operation == "list":
        return list_memory_files(params)
    elif operation == "clear":
        return clear_memory(params)
    else:
        return {
            "status": "error",
            "message": f"Invalid operation: {operation}. Valid operations: add, remove, list, clear"
        }

def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'set_credential':
        result = set_credential(params)
    elif args.action == 'load_credential':
        result = load_credential(params)
    elif args.action == 'add_tool':
        result = add_tool(params)
    elif args.action == 'remove_tool':
        result = remove_tool(params)
    elif args.action == 'list_tools':
        result = list_tools(params)
    elif args.action == 'add_action':
        result = add_action(params)
    elif args.action == 'remove_action':
        result = remove_action(params)
    elif args.action == 'list_actions':
        result = list_actions(params)
    elif args.action == 'add_memory_file':
        result = add_memory_file(params)
    elif args.action == 'remove_memory_file':
        result = remove_memory_file(params)
    elif args.action == 'list_memory_files':
        result = list_memory_files(params)
    elif args.action == 'build_working_memory':
        result = build_working_memory(params)
    elif args.action == 'list_supported_actions':
        result = list_supported_actions(params)
    elif args.action == 'refresh_orchestrate_runtime':
        result = refresh_orchestrate_runtime(params)
    elif args.action == 'install_tool':
        result = install_tool(params)
    elif args.action == 'register_engine':
        result = register_engine(params)
    elif args.action == 'update_action':
        result = update_action(params)
    elif args.action == 'update_custom_instructions':
        result = update_custom_instructions(params)
    elif args.action == 'add_dashboard_item':
        result = add_dashboard_item(params)
    elif args.action == 'remove_dashboard_item':
        result = remove_dashboard_item(params)
    elif args.action == 'update_dashboard_item':
        result = update_dashboard_item(params)
    elif args.action == 'reorder_dashboard':
        result = reorder_dashboard(params)
    elif args.action == 'list_dashboard_items':
        result = list_dashboard_items(params)
    elif args.action == 'toggle_dashboard_item':
        result = toggle_dashboard_item(params)
    elif args.action == 'add_to_memory':
        result = add_to_memory(params)
    elif args.action == 'get_working_memory':
        result = get_working_memory(params)
    elif args.action == 'clear_memory':
        result = clear_memory(params)
    elif args.action == 'activate_intent':
        result = activate_intent(params)
    elif args.action == 'deactivate_intent':
        result = deactivate_intent(params)
    elif args.action == 'get_active_intent':
        result = get_active_intent(params)
    elif args.action == 'list_available_intents':
        result = list_available_intents(params)
    elif args.action == 'manage_tool':
        result = manage_tool(params)
    elif args.action == 'manage_action':
        result = manage_action(params)
    elif args.action == 'manage_dashboard':
        result = manage_dashboard(params)
    elif args.action == 'manage_intent':
        result = manage_intent(params)
    elif args.action == 'manage_memory':
        result = manage_memory(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()