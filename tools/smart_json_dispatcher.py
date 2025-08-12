import os
import datetime
from tools import json_manager

def resolve_nested_key_path(data, key_path):
    keys = str(key_path).split('.')
    ref = data
    for k in keys[:-1]:
        ref = ref.setdefault(k, {})
    return ref, keys[-1]

def orchestrate_write(filename, entry_key, entry_data, strategy="smart"):
    filename = str(filename)
    manager = JSONManager(filename)

    base_data = manager.read_file()
    if not isinstance(base_data, dict):
        return {"error": "❌ Invalid JSON structure in file."}
    if not isinstance(entry_data, dict):
        return {"error": "❌ entry_data must be a dictionary."}

    try:
        parent, last_key = resolve_nested_key_path(base_data.get("entries", {}), entry_key)
    except Exception as e:
        return {"error": f"❌ Failed to resolve key path: {e}"}

    if last_key in parent:
        if strategy == "overwrite":
            parent[last_key] = entry_data
        elif strategy == "merge":
            if isinstance(parent[last_key], dict) and isinstance(entry_data, dict):
                parent[last_key].update(entry_data)
            else:
                parent[last_key] = entry_data
        elif strategy == "smart":
            if isinstance(parent[last_key], dict) and isinstance(entry_data, dict):
                parent[last_key].update(entry_data)
            else:
                parent[last_key] = entry_data
    else:
        parent[last_key] = entry_data

    try:
        manager.add_entry("entries", base_data["entries"])
        return {
            "status": "✅ Entry written successfully",
            "target": entry_key,
            "filename": filename
        }
    except Exception as e:
        return {"error": f"❌ Failed to write: {e}"}