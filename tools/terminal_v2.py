import os
import json
import difflib
import importlib
import sys

__tool__ = "terminal_tool"

PROTECTED_FILES = {
    "system_settings.ndjson": "system_settings",
    "intent_routes.json": "json_manager",
    "master_index.json": "json_manager",
    "working_memory.json": "json_manager",
    "session_tracker.json": "json_manager",
    "orchestrate_guardrails.json": "json_manager"
}

SAFE_EXTENSIONS = (
    ".py", ".json", ".md", ".txt", ".csv", ".tsv", ".yaml", ".yml", ".html", ".env"
)

def _reject_if_protected(path, mode="write"):
    if os.path.basename(path) in PROTECTED_FILES:
        raise PermissionError(f"⛔ Use `{PROTECTED_FILES[os.path.basename(path)]}` to {mode} this file.")

def read_file_text(params):
    path = params["path"]
    _reject_if_protected(path, "read")
    with open(path, "r") as f:
        return {"status": "success", "content": f.read()}

def write_file_text(params):
    path = params["path"]
    _reject_if_protected(path, "write")
    with open(path, "w") as f:
        f.write(params["content"])
    return {"status": "written", "path": path}


def find_file(params):
    """
    Search for files whose names contain the given keyword(s).
    Matches are token-based so separators like underscores or dashes don't block a match.
    
    Parameters:
      - keyword (str): text to search for (required)
      - search_path (str): directory to search in (default: ".")
      - case_sensitive (bool): whether search is case sensitive (default: False)
      - max_results (int): limit number of results returned (default: 50)
    """
    import subprocess
    from pathlib import Path

    keyword = params.get("keyword")
    if not keyword:
        return {"status": "error", "message": "Missing required parameter: 'keyword'"}

    search_path = params.get("search_path", ".")
    case_sensitive = params.get("case_sensitive", False)
    max_results = params.get("max_results", 50)

    if not Path(search_path).exists():
        return {"status": "error", "message": f"Search path not found: {search_path}"}

    try:
        results = []
        tokens = keyword.split()  # split on spaces into tokens
        if not case_sensitive:
            tokens = [t.lower() for t in tokens]

        # Search all files
        for path in Path(search_path).rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SAFE_EXTENSIONS:
                continue

            filename = path.name if case_sensitive else path.name.lower()

            # ✅ Token-based filename match only
            if all(token in filename for token in tokens):
                results.append(str(path))

        results = results[:max_results]

        return {
            "status": "success",
            "count": len(results),
            "matches": results
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}



def list_python_defs(params):
    with open(params["path"], "r") as f:
        return [line.strip() for line in f if line.strip().startswith("def ")]

def patch_function_in_file(params):
    path = params["path"]
    func_name = params["function"]
    new_code = params["new_code"]
    _reject_if_protected(path, "write")
    try:
        with open(path, "r") as f:
            lines = f.readlines()
        start = None
        end = None
        indent = None
        for i, line in enumerate(lines):
            if line.strip().startswith(f"def {func_name}("):
                start = i
                indent = len(line) - len(line.lstrip())
                break
        if start is None:
            return {"status": "error", "message": f"Function '{func_name}' not found in {path}"}
        for j in range(start + 1, len(lines)):
            if lines[j].strip() == "" or len(lines[j]) - len(lines[j].lstrip()) <= indent:
                end = j
                break
        else:
            end = len(lines)
        new_block = new_code.strip("\n").split("\n")
        new_block = [line + "\n" for line in new_block]
        patched = lines[:start] + new_block + lines[end:]
        with open(path, "w") as f:
            f.writelines(patched)
        return {"status": "success", "message": f"Function '{func_name}' patched in {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def run_function_inline(params):
    try:
        sys.path.append(os.getcwd())
        module = importlib.import_module(params["module"])
        func = getattr(module, params["function"])
        return func(json.loads(params["args"]))
    except Exception as e:
        return {"status": "error", "message": str(e)}

def run_terminal_command(params):
    import subprocess
    command = params["command"]
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {
            "status": "success" if result.returncode == 0 else "error",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def append_file_text(params):
    import os
    from pathlib import Path

    path = params.get("path")
    content = params.get("content")

    if not path or not content:
        return {"error": "Both 'path' and 'content' are required."}

    file_path = Path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content + "\n")
        return {"status": "success", "path": str(file_path)}
    except Exception as e:
        return {"status": "error", "message": str(e)}



def main():
    import argparse
    import json  # Make sure this is imported at the top
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params")
    args = parser.parse_args()
    
    try:
        params = json.loads(args.params) if args.params else {}
    except:
        print(json.dumps({"status": "error", "message": "Invalid JSON"}))
        return

    router = {
        "read_file_text": read_file_text,
        "write_file_text": write_file_text,
        "append_file_text": append_file_text,
        "list_python_defs": list_python_defs,
        "patch_function_in_file": patch_function_in_file,
        "run_function_inline": run_function_inline,
        "run_terminal_command": run_terminal_command,
        "find_file": find_file  # ✅ new action registered here
    }

    if args.action not in router:
        print(json.dumps({"status": "error", "message": f"Unknown action: {args.action}"}))
        return

    result = router[args.action](params)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()