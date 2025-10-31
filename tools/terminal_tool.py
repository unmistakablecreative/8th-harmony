import os
import json
import importlib
import subprocess
import argparse
from pathlib import Path
import ast

__tool__ = "terminal_tool"

SAFE_EXTENSIONS = (".py", ".json", ".md", ".txt", ".csv", ".tsv", ".yaml", ".yml", ".html", ".env")

PROTECTED_FILES = {
    "system_settings.ndjson": "system_settings",
    "intent_routes.json": "json_manager",
    "master_index.json": "json_manager",
    "working_memory.json": "json_manager",
    "session_tracker.json": "json_manager",
    "orchestrate_guardrails.json": "json_manager"
}

BLOCKED_COMMANDS = [
    "mkdir data", "mkdir tools", "rm data", "rm tools",
    "rm -r data", "rm -r tools", "rm -rf data", "rm -rf tools"
]

def _reject_if_protected(path, mode="write"):
    if os.path.basename(path) in PROTECTED_FILES:
        raise PermissionError(f"⛔ Use `{PROTECTED_FILES[os.path.basename(path)]}` to {mode} this file.")

def resolve_path(filename):
    index_path = os.path.join("data", "directory_index.json")
    try:
        with open(index_path, "r") as f:
            index = json.load(f)
        for directory in index:
            potential = os.path.join(directory, filename)
            if os.path.exists(potential):
                return potential
        return filename  # fallback to raw path
    except:
        return filename

def read_file_text(params):
    import os
    import pdfplumber

    path = params.get("path")
    if not path:
        return {"status": "error", "message": "Missing 'path' parameter"}

    if not os.path.isfile(path):
        return {"status": "error", "message": f"File not found: {path}"}

    if path.endswith(".pdf"):
        try:
            with pdfplumber.open(path) as pdf:
                text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            return {"status": "success", "content": text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def write_file_text(params):
    path = params.get("path")
    content = params.get("content") or params.get("text")
    if not path or not content:
        return {"status": "error", "message": "Missing 'path' or file content."}
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success", "message": f"✅ Written to {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def append_file_text(params):
    path = resolve_path(params["path"])
    _reject_if_protected(path, "write")
    with open(path, "a", encoding="utf-8") as f:
        f.write(params["content"] + "\n")
    return {"status": "success", "path": path}

def list_files(params):
    path = params.get("path", ".")
    recursive = params.get("recursive", False)
    try:
        if recursive:
            files = [str(p) for p in Path(path).rglob("*") if p.is_file()]
        else:
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        return {"status": "success", "files": files}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def list_python_defs(params):
    path = resolve_path(params["path"])
    with open(path, "r") as f:
        return [line.strip() for line in f if line.strip().startswith("def ")]

def patch_function_in_file(params):
    path = params.get("path")
    func_name = params.get("function")
    new_code = params.get("new_code")

    if not all([path, func_name, new_code]):
        return {"status": "error", "message": "Missing required params."}
    if not os.path.exists(path):
        return {"status": "error", "message": f"❌ File not found: {path}"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
            lines = source.splitlines(keepends=True)
        tree = ast.parse(source)

        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                start, end = node.lineno - 1, node.end_lineno
                break
        else:
            return {"status": "error", "message": f"Function '{func_name}' not found."}

        new_lines = [line + "\n" for line in new_code.strip().split("\n")]
        updated = lines[:start] + new_lines + lines[end:]

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(updated)

        return {"status": "success", "message": f"✅ Patched '{func_name}' in {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def run_terminal_command(params):
    command = params["command"].strip()
    if command in BLOCKED_COMMANDS:
        return {"status": "error", "message": f"⛔ Blocked dangerous command: `{command}`"}
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

def find_file(params):
    import json
    from pathlib import Path

    keyword = params.get("keyword")
    case_sensitive = params.get("case_sensitive", False)
    max_results = params.get("max_results", 50)
    index_path = os.path.join("data", "directory_index.json")

    if not keyword:
        return {"status": "error", "message": "Missing required parameter: 'keyword'"}

    try:
        with open(index_path, "r") as f:
            folders = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to load index: {str(e)}"}

    keyword_flat = keyword.replace(" ", "").lower()
    matches = []

    for folder in folders:
        base = Path(folder)
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            flattened = str(path).replace("_", "").replace("-", "").replace(" ", "").lower()
            if keyword_flat in flattened:
                matches.append(str(path))

    return {
        "status": "success",
        "query": keyword,
        "count": len(matches),
        "matches": matches[:max_results]
    }



def insert_new_function_in_script(params):
    import ast
    import re

    # Handle multiple possible parameter names for flexibility
    file_path = (params.get("file_path") or 
                 params.get("filepath") or 
                 params.get("path") or 
                 params.get("script_path"))
    
    func_code = (params.get("function_code") or 
                 params.get("func_code") or 
                 params.get("code") or 
                 params.get("function"))

    # Debug logging
    if not file_path or not func_code:
        return {
            "status": "error", 
            "message": "Missing 'file_path' or 'function_code'",
            "debug_info": {
                "params_received": list(params.keys()),
                "expected": ["file_path", "function_code"],
                "file_path_value": file_path,
                "func_code_value": func_code
            }
        }
    
    if not os.path.exists(file_path):
        return {"status": "error", "message": f"❌ File not found: {file_path}"}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Find main() function
        main_line_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("def main("):
                main_line_idx = i
                break
        
        if main_line_idx is None:
            return {"status": "error", "message": "Could not find main() function in file"}

        # Insert function above main()
        new_func_lines = [line + "\n" for line in func_code.strip().split("\n")]
        patched_lines = lines[:main_line_idx] + ["\n"] + new_func_lines + ["\n"] + lines[main_line_idx:]

        # Extract function name from the code
        func_name_match = re.search(r'def\s+(\w+)\s*\(', func_code)
        if not func_name_match:
            return {"status": "error", "message": "Could not extract function name from code"}
        
        func_name = func_name_match.group(1)

        # Patch main() dispatch - find the right place to insert
        inside_main = False
        final_lines = []
        inserted = False
        
        for i, line in enumerate(patched_lines):
            final_lines.append(line)
            
            # Look for the action dispatch section in main()
            if "if args.action ==" in line and not inside_main:
                inside_main = True
            elif inside_main and "else:" in line and not inserted:
                # Insert before the else clause
                dispatch_line = f"    elif args.action == '{func_name}':\n        result = {func_name}(params)\n"
                final_lines.insert(len(final_lines) - 1, dispatch_line)
                inserted = True
                inside_main = False

        # Write back to file
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(final_lines)

        # Register in system_settings.ndjson
        tool_name = os.path.basename(file_path).replace(".py", "")
        entry = {
            "tool": tool_name,
            "action": func_name,
            "params": [],  # Will be filled by install_tool if needed
            "description": f"Auto-added function: {func_name}"
        }

        ndjson_path = "system_settings.ndjson"
        already_registered = False
        
        if os.path.exists(ndjson_path):
            with open(ndjson_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line.strip())
                        if obj.get("tool") == tool_name and obj.get("action") == func_name:
                            already_registered = True
                            break
                    except:
                        continue

        if not already_registered:
            with open(ndjson_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

        return {
            "status": "success",
            "message": f"✅ Inserted '{func_name}' into {file_path}",
            "function_name": func_name,
            "registered": not already_registered
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": str(e.__traceback__)}





def run_function_inline(params):
    import importlib.util
    import json
    import os

    path = params.get("path")
    func_name = params.get("function_name")
    func_params = params.get("params", {})

    if not path or not func_name:
        return {"status": "error", "message": "Missing required 'path' or 'function_name'"}

    if not os.path.exists(path):
        return {"status": "error", "message": f"❌ File not found: {path}"}

    try:
        spec = importlib.util.spec_from_file_location("module.name", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, func_name):
            return {"status": "error", "message": f"Function '{func_name}' not found in {path}"}

        result = getattr(module, func_name)(**func_params)

        # Allow raw result if not wrapped in contract
        if isinstance(result, dict) and "status" in result:
            return {"status": "success", "result": result}
        else:
            return {"status": "success", "raw_output": result}

    except Exception as e:
        return {"status": "error", "message": f"Function execution failed: {str(e)}"}


def delete_function_from_script(params):
    import ast

    file_path = params.get("file_path")
    func_name = params.get("function_name")
    if not file_path or not func_name:
        return {"status": "error", "message": "Missing 'file_path' or 'function_name'"}
    if not os.path.exists(file_path):
        return {"status": "error", "message": f"❌ File not found: {file_path}"}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
            lines = source.splitlines(keepends=True)
            tree = ast.parse(source)

        # Find and remove function block
        start, end = None, None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                start, end = node.lineno - 1, node.end_lineno
                break
        if start is None:
            return {"status": "error", "message": f"Function '{func_name}' not found."}

        del lines[start:end]

        # Remove router block in main()
        inside_main = False
        new_lines = []
        for line in lines:
            if f"elif args.action == '{func_name}':" in line or f"if args.action == '{func_name}':" in line:
                inside_main = True
                continue
            if inside_main and line.strip().startswith("result ="):
                continue
            inside_main = False
            new_lines.append(line)

        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # Remove from system_settings.ndjson
        tool_name = os.path.basename(file_path).replace(".py", "")
        ndjson_path = "system_settings.ndjson"
        if os.path.exists(ndjson_path):
            with open(ndjson_path, "r", encoding="utf-8") as f:
                entries = [json.loads(line) for line in f if line.strip()]
            updated = [e for e in entries if not (e.get("tool") == tool_name and e.get("action") == func_name)]
            with open(ndjson_path, "w", encoding="utf-8") as f:
                for e in updated:
                    f.write(json.dumps(e) + "\n")

        return {"status": "success", "message": f"🗑️ Deleted '{func_name}' from {file_path} and system settings."}

    except Exception as e:
        return {"status": "error", "message": str(e)}

def main():
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", type=str)
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == "read_file_text":
        result = read_file_text(params)
    elif args.action == "write_file_text":
        result = write_file_text(params)
    elif args.action == "append_file_text":
        result = append_file_text(params)
    elif args.action == "list_files":
        result = list_files(params)
    elif args.action == "run_terminal_command":
        result = run_terminal_command(params)
    elif args.action == "patch_function_in_file":
        result = patch_function_in_file(params)
    elif args.action == "insert_new_function_in_script":
        result = insert_new_function_in_script(params)
    elif args.action == "run_function_inline":
        result = run_function_inline(params)
    elif args.action == "find_file":
        result = find_file(params)
    elif args.action == 'delete_function_from_script':
        result = delete_function_from_script(params)
    else:
        result = {"status": "error", "message": f"Unknown action {args.action}"}

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
