import argparse
import json
import requests
import os

DEFAULT_BLUEPRINT_FILE = "../data/demo_blueprint.json"
DEFAULT_OUTPUT_FILE = "../data/demo_build_log.json"


def load_actions(params):
    path = params.get("blueprint_file", DEFAULT_BLUEPRINT_FILE)
    if not os.path.exists(path):
        return {"status": "error", "message": f"❌ Blueprint file not found: {path}"}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to load blueprint: {str(e)}"}


def generate_instructions_json(username, doc_id):
    """Generate the custom instructions JSON for the user"""
    return {
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
                            "params": {
                                "doc_id": doc_id
                            }
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
                            "params": {
                                "filename": f"{username}_thread_log.json"
                            }
                        }
                    },
                    {
                        "tool": "grossly_guiding_elk_ngrok_free_app__jit_plugin",
                        "action": "executeTask",
                        "id": f"{username}IntentRoutes",
                        "params": {
                            "tool_name": "json_manager",
                            "action": "read_json_file",
                            "params": {
                                "filename": f"{username}_intent_routes.json"
                            }
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
                    f"{username}ThreadLog": f"Summarize the latest entries as semantic memory context. Explain how this functions as {username}'s persistent memory across sessions. Display this as a brief system block beneath the main doc.",
                    f"{username}IntentRoutes": "Render as a table of natural language commands available in this bootloader."
                }
            }
        }
    }


def build_demo(params=None):
    params = params or {}
    username = params.get("username", "test_user")
    
    # Load actions and replace {{username}} placeholders
    actions = load_actions(params)
    if not isinstance(actions, list):
        return {"status": "error", "message": "Blueprint file must be a list of actions."}

    # Replace username placeholders in the entire actions list
    actions_str = json.dumps(actions)
    actions_str = actions_str.replace("{{username}}", username)
    actions = json.loads(actions_str)

    results = []
    doc_id = None

    for step in actions:
        try:
            print(f"➡️  {step['tool_name']}::{step['action']}")
            res = requests.post("http://localhost:5001/execute_task", json=step, timeout=60)
            out = res.json()
            print(f"✅  {out.get('status')} | {out.get('message', '')}")
            
            # Capture doc_id if this was a create_doc action
            if (step.get("tool_name") == "outline_editor" and 
                step.get("action") == "create_doc"):
                if "data" in out and isinstance(out["data"], dict) and "id" in out["data"]:
                    doc_id = out["data"]["id"]
                    print(f"📄  Captured doc_id: {doc_id}")
                elif "id" in out:
                    doc_id = out["id"]
                    print(f"📄  Captured doc_id: {doc_id}")
            
            results.append({"step": step, "response": out})
        except Exception as e:
            print(f"❌  {step['tool_name']}::{step['action']} failed: {str(e)}")
            results.append({"step": step, "error": str(e)})

    # Generate instructions.json if we got a doc_id
    if doc_id:
        try:
            instructions = generate_instructions_json(username, doc_id)
            instructions_file = f"../data/{username}_instructions.json"
            with open(instructions_file, "w") as f:
                json.dump(instructions, f, indent=2)
            print(f"✅  Generated {instructions_file}")
            results.append({
                "step": {"tool_name": "demo_builder", "action": "generate_instructions"}, 
                "response": {"status": "success", "message": f"Created {instructions_file}", "doc_id": doc_id}
            })
        except Exception as e:
            print(f"❌  Failed to generate instructions.json: {str(e)}")
            results.append({
                "step": {"tool_name": "demo_builder", "action": "generate_instructions"}, 
                "error": str(e)
            })

    with open(params.get("log_file", DEFAULT_OUTPUT_FILE), "w") as f:
        json.dump(results, f, indent=2)

    return {"status": "success", "message": f"Demo build complete for {username}.", "steps": len(results), "doc_id": doc_id}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", type=str)
    args = parser.parse_args()

    if args.action == "build_demo":
        parsed = json.loads(args.params) if args.params else {}
        result = build_demo(parsed)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "error", "message": f"Unknown action: {args.action}"}, indent=2))