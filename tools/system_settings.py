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

def output(data):
    print(json.dumps(data, indent=2))
    sys.exit(0)

def error(message):
    print(json.dumps({"status": "error", "message": message}, indent=2))
    sys.exit(1)

# === Credentials ===
def set_credential(params):
    key, value = params.get("key"), params.get("value")
    if not key or not value:
        error("Missing 'key' or 'value'")
    creds = {}
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
    creds[key] = value
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f, indent=2)
    return {"status": "success", "message": f"Credential '{key}' set."}


def load_credential(key):
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    with open(CREDENTIALS_FILE, "r") as f:
        creds = json.load(f)
    return creds.get(key)



# === CLI Routes ===
def add_cli_route(params):
    name, command = params.get("action_name"), params.get("command")
    if not name or not command:
        error("Missing 'action_name' or 'command'")
    routes = {}
    if os.path.exists(ROUTER_MAP_FILE):
        with open(ROUTER_MAP_FILE, "r") as f:
            routes = json.load(f)
    routes[name] = command
    with open(ROUTER_MAP_FILE, "w") as f:
        json.dump(routes, f, indent=2)
    return {"status": "success", "message": f"CLI route '{name}' added."}

def remove_cli_route(params):
    name = params.get("action_name")
    if not name:
        error("Missing 'action_name'")
    if not os.path.exists(ROUTER_MAP_FILE):
        error("router_map.json not found.")
    with open(ROUTER_MAP_FILE, "r") as f:
        routes = json.load(f)
    if name not in routes:
        error(f"CLI route '{name}' not found.")
    del routes[name]
    with open(ROUTER_MAP_FILE, "w") as f:
        json.dump(routes, f, indent=2)
    return {"status": "success", "message": f"CLI route '{name}' removed."}

def list_cli_routes(_):
    if not os.path.exists(ROUTER_MAP_FILE):
        return {"status": "success", "routes": {}}
    with open(ROUTER_MAP_FILE, "r") as f:
        return {"status": "success", "routes": json.load(f)}

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
    updated = [entry for entry in data if not (entry["tool"] == tool and entry["action"] == action)]

    if len(updated) == len(data):
        return {"status": "error", "message": f"No matching action found for '{tool}.{action}'"}

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
    """Write memory index as a flat list of file paths."""
    with open(MEMORY_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


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
                    parsed = json.load(f)
                    memory[key] = parsed
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


    path = WORKING_MEMORY_PATH
    if not os.path.exists(path):
        return { "status": "error", "message": f"working_memory.json not found at {path}" }

    with open(path, "r") as f:
        memory = json.load(f)

    results = []

    def scan(obj, source_file, parent_key=None):
        if isinstance(obj, dict):
            if obj.get("status") == "pending":
                results.append({
                    "entry_key": parent_key or "(unknown)",
                    "source_file": source_file,
                    "title": obj.get("title", parent_key or "(no title)"),
                    "status": "pending"
                })
            for key, val in obj.items():
                scan(val, source_file, parent_key=key if parent_key is None else parent_key)
        elif isinstance(obj, list):
            for item in obj:
                scan(item, source_file, parent_key)

    for source_file, payload in memory.items():
        if isinstance(payload, dict) and "entries" in payload:
            entries = payload["entries"]
            if isinstance(entries, (dict, list)):
                scan(entries, source_file)

    return {
        "status": "success",
        "suggested_tasks": results
    }


def list_supported_actions(_):
    return {"status": "success", "supported": list(dispatch_map.keys())}


# === Dispatch Map ===
dispatch_map = {
    "set_credential": set_credential,
    "load_credential": load_credential,
    "add_tool": add_tool,
    "remove_tool": remove_tool,
    "list_tools": list_tools,
    "add_action": add_action,
    "remove_action": remove_action,  # ✅ newly added
    "list_actions": list_actions,
    "add_cli_route": add_cli_route,
    "remove_cli_route": remove_cli_route,
    "list_cli_routes": list_cli_routes,
    "add_memory_file": add_memory_file,
    "remove_memory_file": remove_memory_file,
    "list_memory_files": list_memory_files,
    "build_working_memory": build_working_memory,
    "list_supported_actions": list_supported_actions
}




# === Entrypoint ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", required=False)
    args = parser.parse_args()

    try:
        action = args.action
        params = json.loads(args.params) if args.params else {}
        if action not in dispatch_map:
            error(f"Unsupported action '{action}'")
        result = dispatch_map[action](params)
        output(result)
    except Exception as e:
        error(str(e))