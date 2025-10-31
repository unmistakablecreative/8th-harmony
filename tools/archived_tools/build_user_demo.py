import json
import argparse
import os
from grossly_guiding_elk_ngrok_free_app__jit_plugin import executeTask

def load_blueprint(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict) and "entries" in data:
            return list(data["entries"].values())[0]
        return data


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Wrote {path}")


def run(username, blueprint_path):
    steps = load_blueprint(blueprint_path)
    doc_id = None

    for step in steps:
        tool = step.get("tool_name")
        action = step.get("action")
        params = step.get("params", {})

        if action == "create_doc" and tool == "outline_editor":
            result = executeTask({
                "tool_name": tool,
                "action": action,
                "params": params
            })
            doc_id = result.get("data", {}).get("id")

        elif action == "create_json_file":
            write_json(os.path.join("data", params["filename"]), [])

        elif action == "add_json_entry":
            filename = params["filename"]
            filepath = os.path.join("data", filename)
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    content = json.load(f)
            else:
                content = []

            if isinstance(content, list):
                content.append(params["entry_data"])
                write_json(filepath, content)
            else:
                entry_key = params["entry_key"]
                content.setdefault("entries", {})[entry_key] = params["entry_data"]
                write_json(filepath, content)

    write_json(os.path.join("data", f"{username}_custom_instructions.json"), {
        "commands": {
            "Load OrchestrateOS": {
                "run": [
                    {
                        "tool": "grossly_guiding_elk_ngrok_free_app__jit_plugin",
                        "action": "executeTask",
                        "params": {
                            "tool_name": "system_control",
                            "action": "load_orchestrate_os",
                            "params": {}
                        }
                    },
                    {
                        "tool": "grossly_guiding_elk_ngrok_free_app__jit_plugin",
                        "action": "getSupportedActions"
                    },
                    {
                        "tool": "grossly_guiding_elk_ngrok_free_app__jit_plugin",
                        "action": "executeTask",
                        "params": {
                            "tool_name": "outline_editor",
                            "action": "get_doc",
                            "params": {"doc_id": doc_id or "<MISSING_DOC_ID>"}
                        }
                    },
                    {
                        "tool": "grossly_guiding_elk_ngrok_free_app__jit_plugin",
                        "action": "loadMemory"
                    },
                    {
                        "tool": "grossly_guiding_elk_ngrok_free_app__jit_plugin",
                        "action": "executeTask",
                        "id": f"{username}ThreadLog",
                        "params": {
                            "tool_name": "json_manager",
                            "action": "read_json_file",
                            "params": {"filename": f"{username}_thread_log.json"}
                        }
                    },
                    {
                        "tool": "grossly_guiding_elk_ngrok_free_app__jit_plugin",
                        "action": "executeTask",
                        "id": f"{username}IntentRoutes",
                        "params": {
                            "tool_name": "json_manager",
                            "action": "read_json_file",
                            "params": {"filename": f"{username}_intent_routes.json"}
                        }
                    }
                ],
                "post_process": "render_bootloader_with_threadlog",
                "display": {
                    "style": "standard",
                    "theme": "light",
                    "layout": "document",
                    "render_mode": "clean",
                    "source_binding": [
                        f"{username}ThreadLog",
                        f"{username}IntentRoutes"
                    ]
                },
                "instructions": {
                    f"{username}ThreadLog": "Summarize the latest entries as semantic memory context. Explain how this functions as persistent memory across sessions.",
                    f"{username}IntentRoutes": "Render as a table of natural language commands available in this bootloader."
                }
            }
        }
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--blueprint", required=True)
    args = parser.parse_args()
    run(args.user, args.blueprint)