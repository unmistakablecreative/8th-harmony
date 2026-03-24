import os
import json
import importlib
import subprocess
import argparse
from pathlib import Path
import ast
from datetime import datetime

# Import write intercept for protected file handling
try:
    from write_intercept import intercept_terminal_write, intercept_terminal_command
except ImportError:
    intercept_terminal_write = None
    intercept_terminal_command = None

__tool__ = "terminal_tool"


def add_temporal_reminder():
    """Generate temporal context reminder for Claude to avoid hallucinating outdated info."""
    now = datetime.now()
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_year": now.year,
        "reminder": f"Today is {now.strftime('%B %d, %Y')}. When referencing dates, APIs, or documentation, use {now.year} as the current year. Do not hallucinate outdated information."
    }

PROJECT_ROOT = Path(__file__).parent.parent

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

# File search interception patterns
FILE_SEARCH_PATTERNS = [
    r'^find\s+',           # find . -name "*.py"
    r'^locate\s+',         # locate filename
    r'^ls\s+.*\|\s*grep',  # ls | grep pattern
    r'^ls\s+-[lRa]*\s+.*\|\s*grep',  # ls -la | grep
    r'^fd\s+',             # fd alternative to find
    r'^mdfind\s+',         # macOS spotlight
]

def _log_interception(original_cmd, intercepted_action, result):
    """Log intercepted file search commands to data/file_search_interceptions.log"""
    import os
    from datetime import datetime

    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "file_search_interceptions.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_entry = {
        "timestamp": timestamp,
        "original_command": original_cmd,
        "intercepted_action": intercepted_action,
        "result_status": result.get("status", "unknown"),
        "result_count": result.get("count", len(result.get("matches", [])) if "matches" in result else 0)
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass  # Silent fail on logging

def _extract_search_target(command):
    """Extract the filename or keyword from a file search command."""
    import re

    # find . -name "pattern" or find . -name 'pattern'
    find_name_match = re.search(r'-name\s+["\']?([^"\']+)["\']?', command)
    if find_name_match:
        return find_name_match.group(1).strip("*")

    # find . -iname "pattern" (case insensitive)
    find_iname_match = re.search(r'-iname\s+["\']?([^"\']+)["\']?', command)
    if find_iname_match:
        return find_iname_match.group(1).strip("*")

    # locate filename
    locate_match = re.search(r'^locate\s+(.+)$', command.strip())
    if locate_match:
        return locate_match.group(1).strip()

    # ls | grep pattern or ls -la | grep pattern
    grep_match = re.search(r'\|\s*grep\s+["\']?([^"\'|]+)["\']?', command)
    if grep_match:
        return grep_match.group(1).strip()

    # fd pattern
    fd_match = re.search(r'^fd\s+["\']?([^"\']+)["\']?', command.strip())
    if fd_match:
        return fd_match.group(1).strip()

    # mdfind pattern
    mdfind_match = re.search(r'^mdfind\s+["\']?([^"\']+)["\']?', command.strip())
    if mdfind_match:
        return mdfind_match.group(1).strip()

    return None

def _intercept_file_search(command):
    """
    Check if command is a file search and intercept it.
    Returns (should_intercept, result) tuple.
    """
    import re

    for pattern in FILE_SEARCH_PATTERNS:
        if re.match(pattern, command.strip(), re.IGNORECASE):
            # Extract the search target
            target = _extract_search_target(command)

            if not target:
                # Couldn't extract target, let original command run
                return False, None

            # Try alias resolution first
            alias_files = _resolve_alias(target)
            if alias_files and len(alias_files) == 1:
                resolved = _resolve_filename_to_path(alias_files[0])
                if resolved:
                    result = {
                        "status": "success",
                        "intercepted": True,
                        "original_command": command,
                        "method": "alias_resolution",
                        "resolved_path": resolved,
                        "message": f"🎯 Intercepted file search. Found via alias: {resolved}"
                    }
                    _log_interception(command, "alias_resolution", result)
                    return True, result

            # Try filesystem index resolution
            resolved = _resolve_filename_to_path(target)
            if resolved:
                result = {
                    "status": "success",
                    "intercepted": True,
                    "original_command": command,
                    "method": "filesystem_index",
                    "resolved_path": resolved,
                    "message": f"🎯 Intercepted file search. Found via index: {resolved}"
                }
                _log_interception(command, "filesystem_index", result)
                return True, result

            # Fall back to search_files for fuzzy matching
            search_result = search_files({"keyword": target, "search_type": "name", "max_results": 10})
            if search_result.get("status") == "success" and search_result.get("matches"):
                result = {
                    "status": "success",
                    "intercepted": True,
                    "original_command": command,
                    "method": "search_files",
                    "matches": search_result.get("matches"),
                    "count": search_result.get("count"),
                    "message": f"🎯 Intercepted file search. Found {search_result.get('count')} matches"
                }
                _log_interception(command, "search_files", result)
                return True, result

            # Nothing found, let original command run as escape hatch
            _log_interception(command, "no_match_passthrough", {"status": "passthrough"})
            return False, None

    return False, None

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

def _load_filesystem_index(repo="jarvis"):
    """Load filesystem index for a given repo."""
    repo_mapping = {
        "jarvis": "data/filesystem.json",
        "os": "data/filesystem_os.json",
        "container": "data/filesystem_container.json"
    }

    index_path = repo_mapping.get(repo, f"data/filesystem_{repo}.json")

    try:
        with open(index_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return None

# File alias configuration
FILE_ALIASES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "file_aliases.json")

def _load_file_aliases():
    """Load file aliases from data/file_aliases.json."""
    try:
        with open(FILE_ALIASES_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _resolve_alias(filename, extension_hint=None):
    """
    Resolve a filename through file aliases.

    Args:
        filename: The filename or alias to resolve (e.g., "nylas inbox", "doc editor")
        extension_hint: Optional extension filter like "py" or ".py"

    Returns:
        List of resolved filenames, or None if no alias match
    """
    aliases = _load_file_aliases()

    # Normalize the input (case insensitive)
    filename_lower = filename.lower().strip()

    # Check for alias match
    for alias_key, file_list in aliases.items():
        if alias_key.lower() == filename_lower:
            # Filter by extension if hint provided
            if extension_hint:
                ext = extension_hint.lstrip('.').lower()
                filtered = [f for f in file_list if f.lower().endswith(f'.{ext}')]
                if filtered:
                    return filtered
            return file_list

    return None

def _resolve_filename_to_path(filename, repo="jarvis"):
    """Resolve a filename (without path) to its full path using filesystem index or directory scan."""
    import os
    
    # Common directories to search
    SEARCH_DIRS = ["tools", "data", ".", "scripts", "engines", "semantic_memory"]
    
    # First try filesystem index
    index = _load_filesystem_index(repo)
    if index:
        # Direct match by key (filename)
        if filename in index:
            return index[filename].get("path")

        # Try matching with .py extension if not provided
        if not filename.endswith(".py") and f"{filename}.py" in index:
            return index[f"{filename}.py"].get("path")

        # Search in paths
        for key, data in index.items():
            file_path = data.get("path", "")
            if file_path.endswith(filename) or file_path.endswith(f"/{filename}"):
                return file_path

    # Fallback: scan common directories
    for directory in SEARCH_DIRS:
        if os.path.isdir(directory):
            # Try direct path
            candidate = os.path.join(directory, filename)
            if os.path.isfile(candidate):
                return candidate
            # Try with .py extension
            if not filename.endswith(".py"):
                candidate_py = os.path.join(directory, f"{filename}.py")
                if os.path.isfile(candidate_py):
                    return candidate_py

    return None

def read_file_text(params):
    import os

    filename = params.get("filename")
    repo = params.get("repo", "jarvis")  # Default to jarvis repo

    # Auto-strip path if Claude.ai sends full path - just use filename
    if filename and "/" in filename:
        filename = os.path.basename(filename)

    if not filename:
        return {"status": "error", "message": "Missing 'filename' parameter"}

    # Check for extension hint in the filename request and extract clean alias name
    extension_hint = None
    alias_lookup_name = filename
    if "python" in filename.lower():
        extension_hint = "py"
        alias_lookup_name = filename.lower().replace("python", "").strip()
    elif ".py" in filename.lower():
        extension_hint = "py"
        alias_lookup_name = filename.lower().replace(".py", "").strip()
    elif ".html" in filename.lower():
        extension_hint = "html"
        alias_lookup_name = filename.lower().replace(".html", "").strip()

    # Try alias resolution first (use cleaned name for lookup)
    alias_files = _resolve_alias(alias_lookup_name, extension_hint)
    if alias_files:
        # If single file in alias, resolve and read it
        if len(alias_files) == 1:
            resolved = _resolve_filename_to_path(alias_files[0], repo)
            if resolved and os.path.isfile(resolved):
                try:
                    with open(resolved, "r", encoding="utf-8") as f:
                        content = f.read()
                    return {"status": "success", "content": content, "resolved_path": resolved, "alias_matched": filename}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
        else:
            # Multiple files - concatenate all
            all_content = []
            resolved_paths = []
            for alias_file in alias_files:
                resolved = _resolve_filename_to_path(alias_file, repo)
                if resolved and os.path.isfile(resolved):
                    try:
                        with open(resolved, "r", encoding="utf-8") as f:
                            all_content.append(f"# ===== {alias_file} =====\n{f.read()}")
                            resolved_paths.append(resolved)
                    except Exception:
                        pass
            if all_content:
                return {
                    "status": "success",
                    "content": "\n\n".join(all_content),
                    "resolved_paths": resolved_paths,
                    "alias_matched": filename,
                    "files_included": alias_files
                }

    path = filename
    # If path doesn't exist as-is, try resolving via filesystem index
    if not os.path.isfile(path):
        resolved_path = _resolve_filename_to_path(path, repo)
        if resolved_path and os.path.isfile(resolved_path):
            path = resolved_path
        else:
            return {"status": "error", "message": f"File not found: {filename}"}

    if path.endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = "\n".join([page.extract_text() or "" for page in pdf.pages])
            result = {"status": "success", "content": text, "resolved_path": path}
            result["temporal_context"] = add_temporal_reminder()
            return result
        except Exception as e:
            return {"status": "error", "message": str(e)}

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "content": content}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def write_file_text(params):
    import base64

    # Check for protected file intercept
    if intercept_terminal_write:
        blocked, error = intercept_terminal_write("write_file_text", params)
        if blocked:
            return error

    filepath = params.get("filepath") or params.get("filename") or params.get("path")
    content = params.get("content") or params.get("text")
    is_base64 = params.get("base64", False)
    skip_lint = params.get("skip_lint", False)
    force_write = params.get("force", False)

    if not filepath or not content:
        return {"status": "error", "message": "Missing 'filepath' or content."}
    try:
        if is_base64:
            content = base64.b64decode(content).decode("utf-8")

        # Run code_linter on .py files unless skipped
        if filepath.endswith(".py") and not skip_lint:
            try:
                from code_linter import lint_python_file
                lint_result = lint_python_file(content, filepath)

                if not lint_result["passed"] and not force_write:
                    return {
                        "status": "error",
                        "message": "Lint FAILED - file NOT written",
                        "errors": lint_result["errors"],
                        "warnings": lint_result["warnings"],
                        "hint": "Fix errors or set force=true to override"
                    }

                # Attach warnings even on success
                warnings = lint_result.get("warnings", [])
            except ImportError:
                warnings = ["code_linter not found - skipping lint"]
            except Exception as lint_error:
                warnings = [f"Lint error: {str(lint_error)}"]
        else:
            warnings = []

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        result = {"status": "success", "message": f"Written to {filepath}", "path": filepath}
        if warnings:
            result["warnings"] = warnings
        return result
    except Exception as e:
        if "padding" in str(e).lower() or "base64" in str(e).lower():
            return {"status": "error", "message": "❌ Content must be base64 encoded. Encode your content before sending, or set base64=false for raw text."}
        return {"status": "error", "message": str(e)}

def write_python_script(params):
    """
    Write Python script using base64 encoding to avoid ALL escaping issues.

    params:
        path: Target file path
        code_base64: Base64-encoded Python code
    """
    import base64
    import os

    # Check for protected file intercept
    if intercept_terminal_write:
        blocked, error = intercept_terminal_write("write_python_script", params)
        if blocked:
            return error

    filename = params.get("filename")
    code_base64 = params.get("code_base64")
    
    if not path or not code_base64:
        return {
            "status": "error", 
            "message": "Missing 'path' or 'code_base64'",
            "usage": "Encode Python code as base64, send in code_base64 param"
        }
    
    try:
        # Decode from base64
        code = base64.b64decode(code_base64).decode("utf-8")
        
        # Write the decoded code
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        
        # Make executable
        if path.endswith(".py"):
            os.chmod(path, 0o755)
        
        return {
            "status": "success",
            "message": f"✅ Written Python script to {path}",
            "lines": len(code.split("\n")),
            "size": len(code)
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to write script: {str(e)}"}

def append_file_text(params):
    """Append content to a file. Supports base64 encoding for complex content."""

    # Check for protected file intercept
    if intercept_terminal_write:
        blocked, error = intercept_terminal_write("append_file_text", params)
        if blocked:
            return error

    filename = params.get("filename")
    content = params.get("content") or params.get("text", "")
    use_base64 = params.get("base64", True)  # CHANGED: Default to True

    if not filename:
        return {"status": "error", "message": "path is required"}
    
    try:
        if use_base64:
            import base64
            content = base64.b64decode(content).decode("utf-8")
        
        full_path = PROJECT_ROOT / path if not path.startswith("/") else Path(path)
        with open(full_path, "a") as f:
            f.write(content)
        return {"status": "success", "message": f"Appended to {path}"}
    except Exception as e:
        if "padding" in str(e).lower() or "base64" in str(e).lower():
            return {"status": "error", "message": "❌ Content must be base64 encoded. Encode your content before sending, or set base64=false for raw text."}
        return {"status": "error", "message": str(e)}

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

def patch_function_in_file(params):
    import base64

    # Check for protected file intercept
    if intercept_terminal_write:
        blocked, error = intercept_terminal_write("patch_function_in_file", params)
        if blocked:
            return error

    filename = params.get("filename")
    func_name = params.get("function")
    new_code = params.get("new_code")
    new_code_base64 = params.get("new_code_base64")
    
    # Decode if base64 provided
    if new_code_base64:
        try:
            new_code = base64.b64decode(new_code_base64).decode("utf-8")
        except Exception as e:
            if "padding" in str(e).lower() or "base64" in str(e).lower():
                return {"status": "error", "message": "❌ Content must be base64 encoded. Encode your content before sending, or set base64=false for raw text."}
            return {"status": "error", "message": f"Failed to decode base64: {str(e)}"}

    if not all([path, func_name, new_code]):
        return {"status": "error", "message": "Missing required params."}
    if not os.path.exists(path):
        return {"status": "error", "message": f"File not found: {path}"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
            lines = source.splitlines(keepends=True)
        tree = ast.parse(source)

        # Find function - check top level and inside classes
        target_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                target_node = node
                break
        
        if target_node is None:
            return {"status": "error", "message": f"Function {func_name} not found."}
        
        start, end = target_node.lineno - 1, target_node.end_lineno
        new_lines = [line + "\n" for line in new_code.strip().split("\n")]
        updated = lines[:start] + new_lines + lines[end:]

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(updated)

        return {"status": "success", "message": f"Patched {func_name} in {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}



def run_terminal_command(params):
    import base64

    command = params.get("command")
    command_base64 = params.get("command_base64")
    bypass_intercept = params.get("bypass_intercept", False)  # Escape hatch

    # Decode if base64 provided
    if command_base64:
        try:
            command = base64.b64decode(command_base64).decode("utf-8")
        except Exception as e:
            return {"status": "error", "message": f"Failed to decode base64: {str(e)}"}

    if not command:
        return {"status": "error", "message": "Missing 'command' parameter"}

    command = command.strip()
    if command in BLOCKED_COMMANDS:
        return {"status": "error", "message": f"⛔ Blocked dangerous command: `{command}`"}

    # Check for writes to protected files (redirects, sed -i, cp/mv)
    if intercept_terminal_command and not bypass_intercept:
        blocked, error = intercept_terminal_command(command)
        if blocked:
            return error

    # Intercept file search commands and reroute to read_file_text path resolution
    if not bypass_intercept:
        should_intercept, intercept_result = _intercept_file_search(command)
        if should_intercept and intercept_result:
            return intercept_result

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

def search_files(params):
    """
    Search for files by name, content, or both.

    params:
        keyword (required): what to search for
        search_type: 'name', 'content', or 'both' (default: 'both')
        path: starting directory (default: PROJECT_ROOT)
        extension: file extension filter like '.py', '.json' (optional)
        max_results: max results to return (default: 20)
        case_sensitive: bool (default: False)
    """
    import subprocess
    from pathlib import Path

    keyword = params.get("keyword")
    search_type = params.get("search_type", "both")
    search_path = params.get("path", str(PROJECT_ROOT))
    extension = params.get("extension")
    max_results = params.get("max_results", 20)
    case_sensitive = params.get("case_sensitive", False)

    if not keyword:
        return {"status": "error", "message": "Missing required parameter: 'keyword'"}

    matches = []
    seen_paths = set()

    # Normalize extension
    if extension and not extension.startswith("."):
        extension = "." + extension

    # NAME SEARCH: Query filesystem.json index first, fallback to rglob
    if search_type in ("name", "both"):
        index_matches = []
        fallback_to_rglob = False

        # Try filesystem.json index first
        try:
            index_path = PROJECT_ROOT / "data" / "filesystem.json"
            if index_path.exists():
                with open(index_path) as f:
                    fs_index = json.load(f)

                keyword_check = keyword if case_sensitive else keyword.lower()

                for filename, info in fs_index.items():
                    fname_check = filename if case_sensitive else filename.lower()

                    if keyword_check in fname_check:
                        full_path = str(PROJECT_ROOT / info["path"])

                        # Extension filter
                        if extension and not full_path.endswith(extension):
                            continue

                        if full_path not in seen_paths:
                            seen_paths.add(full_path)
                            index_matches.append({"path": full_path, "match_type": "name"})

                matches.extend(index_matches)
            else:
                fallback_to_rglob = True
        except Exception:
            fallback_to_rglob = True

        # Fallback to rglob if index not available or empty results
        if fallback_to_rglob or (not index_matches and search_type == "name"):
            try:
                base = Path(search_path)
                for path in base.rglob("*"):
                    if not path.is_file():
                        continue

                    # Extension filter
                    if extension and not str(path).endswith(extension):
                        continue

                    # Check filename match
                    filename = path.name if case_sensitive else path.name.lower()
                    keyword_check = keyword if case_sensitive else keyword.lower()

                    if keyword_check in filename:
                        path_str = str(path)
                        if path_str not in seen_paths:
                            seen_paths.add(path_str)
                            matches.append({"path": path_str, "match_type": "name"})
            except Exception:
                pass  # Continue to content search even if name search fails

    # CONTENT SEARCH: Use grep for speed
    if search_type in ("content", "both"):
        try:
            # Build grep command with exclusions to avoid timeouts on large dirs
            cmd = ["grep", "-r", "-l"]  # -l = list files only
            if not case_sensitive:
                cmd.append("-i")

            # Exclude heavy directories that cause timeouts
            for exclude_dir in [".git", "node_modules", "__pycache__", ".claude", "venv", ".venv", "env"]:
                cmd.extend(["--exclude-dir", exclude_dir])

            # Add extension filter via --include
            if extension:
                cmd.extend(["--include", f"*{extension}"])
            else:
                # Default to text file types to avoid searching binaries
                for ext in ["*.py", "*.json", "*.md", "*.txt", "*.html", "*.yaml", "*.yml", "*.csv", "*.sh"]:
                    cmd.extend(["--include", ext])

            cmd.append(keyword)
            cmd.append(search_path)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line and line not in seen_paths:
                        seen_paths.add(line)
                        # Check if this was already found by name search
                        existing = next((m for m in matches if m["path"] == line), None)
                        if existing:
                            existing["match_type"] = "both"
                        else:
                            matches.append({"path": line, "match_type": "content"})
        except subprocess.TimeoutExpired:
            pass  # Timeout on content search, return what we have
        except Exception as e:
            pass  # Continue with what we have

    return {
        "status": "success",
        "query": keyword,
        "search_type": search_type,
        "count": len(matches),
        "matches": matches[:max_results]
    }


def find_file(params):
    """Backwards-compatible wrapper for search_files."""
    # Map old params to new format
    return search_files(params)

def insert_new_function_in_script(params):
    import ast
    import re
    import base64

    # Check for protected file intercept
    if intercept_terminal_write:
        blocked, error = intercept_terminal_write("insert_new_function_in_script", params)
        if blocked:
            return error

    # Handle multiple possible parameter names for flexibility
    file_path = (params.get("file_path") or
                 params.get("filepath") or
                 params.get("path") or
                 params.get("script_path"))
    
    func_code = (params.get("function_code") or 
                 params.get("func_code") or 
                 params.get("code") or 
                 params.get("function"))
    
    # Support base64 encoding - CHANGED: Default to True
    use_base64 = params.get("base64", True)
    
    # Decode if base64 is expected
    if use_base64 and func_code:
        try:
            func_code = base64.b64decode(func_code).decode("utf-8")
        except Exception as e:
            if "padding" in str(e).lower() or "base64" in str(e).lower():
                return {"status": "error", "message": "❌ Content must be base64 encoded. Encode your content before sending, or set base64=false for raw text."}
            return {"status": "error", "message": f"Failed to decode base64: {str(e)}"}

    # Debug logging
    if not file_path or not func_code:
        return {
            "status": "error", 
            "message": "Missing 'file_path' or 'function_code'",
            "debug_info": {
                "params_received": list(params.keys()),
                "expected": ["file_path", "function_code (base64 encoded by default)"],
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
        # FIX: Only look for dispatch pattern AFTER we enter def main()
        in_main_func = False
        inside_dispatch = False
        final_lines = []
        inserted = False

        for i, line in enumerate(patched_lines):
            final_lines.append(line)

            # First detect when we enter main()
            if line.strip().startswith("def main("):
                in_main_func = True

            # Only look for dispatch pattern AFTER we are in main()
            if in_main_func and "if args.action ==" in line and not inside_dispatch:
                inside_dispatch = True
            elif inside_dispatch and "else:" in line and not inserted:
                # Insert before the else clause
                dispatch_line = f"    elif args.action == '{func_name}':\n        result = {func_name}(params)\n"
                final_lines.insert(len(final_lines) - 1, dispatch_line)
                inserted = True
                inside_dispatch = False

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

    filename = params.get("filename")
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

    # Check for protected file intercept
    if intercept_terminal_write:
        blocked, error = intercept_terminal_write("delete_function_from_script", params)
        if blocked:
            return error

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


def replace_lines(params):
    """Replace a range of lines in a file. Supports base64 for new_content."""

    # Check for protected file intercept
    if intercept_terminal_write:
        blocked, error = intercept_terminal_write("replace_lines", params)
        if blocked:
            return error

    filename = params.get("filename")
    start_line = params.get("start_line")
    end_line = params.get("end_line", start_line)
    new_content = params.get("new_content", "")
    use_base64 = params.get("base64", True)  # CHANGED: Default to True

    if not filename or not start_line:
        return {"status": "error", "message": "path and start_line are required"}
    
    try:
        if use_base64:
            import base64
            new_content = base64.b64decode(new_content).decode("utf-8")
        
        full_path = PROJECT_ROOT / path if not path.startswith("/") else Path(path)
        lines = full_path.read_text().split("\n")
        
        # Convert to 0-indexed
        start_idx = start_line - 1
        end_idx = end_line
        
        # Replace the lines
        new_lines = lines[:start_idx] + new_content.split("\n") + lines[end_idx:]
        full_path.write_text("\n".join(new_lines))
        
        return {"status": "success", "message": f"Replaced lines {start_line}-{end_line} in {path}"}
    except Exception as e:
        err_str = str(e).lower()
        if "padding" in err_str or "base64" in err_str or "codec" in err_str or "decode" in err_str:
            return {"status": "error", "message": "❌ Content must be base64 encoded. Encode your content before sending, or set base64=false for raw text."}
        return {"status": "error", "message": str(e)}



def grep_content(params):
    """Search file contents for a pattern. Replaces native Grep tool."""
    import subprocess
    import json
    
    pattern = params.get("pattern")
    path = params.get("path", ".")
    file_type = params.get("type")
    max_results = params.get("max_results", 100)
    case_insensitive = params.get("case_insensitive", False)
    context_lines = params.get("context", 0)
    
    if not pattern:
        return {"status": "error", "message": "Missing pattern parameter"}
    
    # Use full path to ripgrep (bundled with Claude Code)
    rg_path = "/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/vendor/ripgrep/arm64-darwin/rg"
    cmd = [rg_path, "--json", pattern]
    
    if case_insensitive:
        cmd.append("-i")
    
    if file_type:
        cmd.extend(["--type", file_type])
    
    if context_lines:
        cmd.extend(["-C", str(context_lines)])
    
    cmd.append(path)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        matches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data.get("data", {})
                    matches.append({
                        "file": match_data.get("path", {}).get("text"),
                        "line_number": match_data.get("line_number"),
                        "text": match_data.get("lines", {}).get("text", "").strip()
                    })
            except:
                continue
        
        return {
            "status": "success",
            "pattern": pattern,
            "count": len(matches),
            "matches": matches[:max_results]
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Search timed out after 30s"}
    except FileNotFoundError:
        return {"status": "error", "message": "ripgrep (rg) not installed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def read_function(params):
    """Read a specific function from a Python file and return its complete code.
    
    If function_name is omitted, returns a function index with all functions,
    their line ranges, and docstring summaries.
    
    Args:
        params: dict with:
            - filename (str): Name of the Python file or tool alias
            - function_name (str, optional): Name of the function to extract.
              If omitted, returns function index for the entire file.
            - directory (str, optional): Directory to search in
    
    Returns:
        dict with status and content (the function code) or error message
        If function_name omitted: dict with function_count and functions list
    """
    import ast
    import os
    import json
    
    filename = params.get("filename")
    function_name = params.get("function_name")
    directory = params.get("directory", "tools")
    
    if not filename:
        return {"status": "error", "message": "Missing 'filename' parameter"}
    
    # Check if filename is a tool alias in system_settings
    resolved_from_tool = None
    settings_file = "system_settings.ndjson"
    if os.path.exists(settings_file) and not filename.endswith(".py"):
        try:
            with open(settings_file, "r") as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        if entry.get("action") == "__tool__" and entry.get("tool") == filename:
                            resolved_from_tool = entry.get("script_path")
                            break
        except Exception:
            pass  # Fall through to normal resolution
    
    # If we resolved a tool alias, use that path
    if resolved_from_tool:
        filename = resolved_from_tool
    
    # Resolve the file path
    if os.path.isabs(filename):
        path = filename
    elif os.path.exists(filename):
        path = filename
    else:
        # Try with directory prefix
        path = os.path.join(directory, filename)
        if not os.path.exists(path):
            # Try resolving via filesystem index
            resolved = _resolve_filename_to_path(filename)
            if resolved and os.path.exists(resolved):
                path = resolved
            else:
                return {"status": "error", "message": f"File not found: {filename}"}
    
    if not os.path.exists(path):
        return {"status": "error", "message": f"File not found: {path}"}
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
            lines = source.splitlines(keepends=True)
        
        tree = ast.parse(source)
        
        # FUNCTION INDEX MODE: If no function_name provided, return index of all functions
        if not function_name:
            functions = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Extract first line of docstring if present
                    doc_summary = ""
                    if (node.body and isinstance(node.body[0], ast.Expr) and
                        isinstance(node.body[0].value, ast.Constant) and
                        isinstance(node.body[0].value.value, str)):
                        docstring = node.body[0].value.value
                        first_line = docstring.strip().split('\n')[0].strip()
                        doc_summary = first_line[:80] if len(first_line) > 80 else first_line
                    
                    functions.append({
                        "name": node.name,
                        "start_line": node.lineno,
                        "end_line": node.end_lineno,
                        "doc_summary": doc_summary
                    })
            
            # Sort by start_line for consistent ordering
            functions.sort(key=lambda x: x["start_line"])
            
            return {
                "status": "success",
                "filename": os.path.basename(path),
                "file_path": os.path.abspath(path),
                "function_count": len(functions),
                "functions": functions
            }
        
        # SINGLE FUNCTION MODE: Find and return specific function
        target_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                target_node = node
                break
        
        if target_node is None:
            # List available functions for helpful error
            available = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            return {
                "status": "error",
                "message": f"Function '{function_name}' not found in {path}",
                "available_functions": available[:20]  # Limit to first 20
            }
        
        # Extract function code (1-indexed to 0-indexed)
        start = target_node.lineno - 1
        end = target_node.end_lineno
        function_code = "".join(lines[start:end])
        
        return {
            "status": "success",
            "content": function_code,
            "function_name": function_name,
            "file_path": path,
            "start_line": target_node.lineno,
            "end_line": target_node.end_lineno
        }
    except SyntaxError as e:
        return {"status": "error", "message": f"Syntax error parsing {path}: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Error reading function: {str(e)}"}


def list_python_defs(params):
    """List all function definitions in a Python file with their argument signatures.

    Uses AST module for proper parsing (not regex).

    Args:
        params: dict with:
            - path (str): Path to the .py file to analyze. Can be:
                - Full path: /path/to/file.py
                - Relative path: tools/file.py
                - Bare filename: file.py
                - Tool name without extension: file

    Returns:
        dict with status, file, and functions list containing:
            - name: function name
            - args: full argument signature as string
            - line: line number where function is defined
    """
    import ast
    import os

    path = params.get("path")
    if not path:
        return {"status": "error", "message": "Missing required parameter: path"}

    # Auto-strip path if full path is given - just use filename (like read_file_text)
    if "/" in path:
        path = os.path.basename(path)

    # Add .py extension if not provided
    if not path.endswith(".py"):
        path = f"{path}.py"

    # If path doesn't exist as-is, try resolving via filesystem index
    if not os.path.isfile(path):
        resolved_path = _resolve_filename_to_path(path)
        if resolved_path and os.path.isfile(resolved_path):
            path = resolved_path
        else:
            return {"status": "error", "message": f"File not found: {path}"}

    try:
        with open(path, "r") as f:
            content = f.read()

        tree = ast.parse(content)
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Build argument signature
                args_parts = []

                # Get all arguments
                all_args = node.args

                # positional-only args (before /)
                posonlyargs = getattr(all_args, "posonlyargs", [])

                # regular args
                regular_args = all_args.args

                # defaults for regular args (aligned from the end)
                defaults = all_args.defaults
                num_defaults = len(defaults)
                num_regular = len(regular_args)

                # Process positional-only args
                for i, arg in enumerate(posonlyargs):
                    arg_str = arg.arg
                    if arg.annotation:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    args_parts.append(arg_str)

                if posonlyargs:
                    args_parts.append("/")

                # Process regular args
                for i, arg in enumerate(regular_args):
                    arg_str = arg.arg
                    if arg.annotation:
                        arg_str += f": {ast.unparse(arg.annotation)}"

                    # Check if this arg has a default
                    default_idx = i - (num_regular - num_defaults)
                    if default_idx >= 0:
                        default_val = defaults[default_idx]
                        arg_str += f" = {ast.unparse(default_val)}"

                    args_parts.append(arg_str)

                # *args
                if all_args.vararg:
                    vararg_str = f"*{all_args.vararg.arg}"
                    if all_args.vararg.annotation:
                        vararg_str += f": {ast.unparse(all_args.vararg.annotation)}"
                    args_parts.append(vararg_str)
                elif all_args.kwonlyargs:
                    args_parts.append("*")

                # keyword-only args
                kw_defaults = all_args.kw_defaults
                for i, arg in enumerate(all_args.kwonlyargs):
                    arg_str = arg.arg
                    if arg.annotation:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    if kw_defaults[i] is not None:
                        arg_str += f" = {ast.unparse(kw_defaults[i])}"
                    args_parts.append(arg_str)

                # **kwargs
                if all_args.kwarg:
                    kwarg_str = f"**{all_args.kwarg.arg}"
                    if all_args.kwarg.annotation:
                        kwarg_str += f": {ast.unparse(all_args.kwarg.annotation)}"
                    args_parts.append(kwarg_str)

                args_signature = ", ".join(args_parts)

                functions.append({
                    "name": node.name,
                    "args": args_signature,
                    "line": node.lineno
                })

        # Sort by line number
        functions.sort(key=lambda x: x["line"])

        return {
            "status": "success",
            "file": os.path.basename(path),
            "functions": functions
        }

    except SyntaxError as e:
        return {"status": "error", "message": f"Syntax error in file: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Error parsing file: {str(e)}"}



def ssh_command(params):
    """Execute command on remote server via SSH.

    Required params:
        host: Remote hostname or IP
        username: SSH username
        command: Command to execute

    Optional params:
        password: SSH password (if not using key)
        key_file: Path to private key file
        port: SSH port (default 22)
        timeout: Command timeout in seconds (default 300)
    """
    import paramiko  # Import here to avoid breaking other actions if paramiko not installed

    host = params.get("host")
    username = params.get("username")
    command = params.get("command")
    password = params.get("password")
    key_file = params.get("key_file")
    port = params.get("port", 22)
    timeout = params.get("timeout", 300)

    if not all([host, username, command]):
        return {"status": "error", "message": "Missing required params: host, username, command"}

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": host,
            "username": username,
            "port": port,
            "timeout": 30,
            "allow_agent": False,
            "look_for_keys": False
        }

        if key_file:
            connect_kwargs["key_filename"] = key_file
        elif password:
            connect_kwargs["password"] = password
        else:
            return {"status": "error", "message": "Must provide password or key_file"}

        client.connect(**connect_kwargs)

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()

        client.close()

        return {
            "status": "success" if exit_code == 0 else "error",
            "exit_code": exit_code,
            "stdout": output,
            "stderr": error,
            "host": host
        }
    except paramiko.AuthenticationException:
        return {"status": "error", "message": f"Authentication failed for {username}@{host}"}
    except paramiko.SSHException as e:
        return {"status": "error", "message": f"SSH error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Connection error: {str(e)}"}


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
    elif args.action == "write_python_script":
        result = write_python_script(params)
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
    elif args.action == "search_files":
        result = search_files(params)
    elif args.action == "find_file":
        # DEPRECATED: Redirect to search_files with warning
        result = search_files(params)
        result["deprecation_warning"] = "⚠️ find_file is deprecated. Use search_files or read_file_text (with auto-resolution) instead."
    elif args.action == "delete_function_from_script":
        result = delete_function_from_script(params)
    elif args.action == "replace_lines":
        result = replace_lines(params)
    elif args.action == 'read_function':
        result = read_function(params)
    elif args.action == 'grep_content':
        result = grep_content(params)
    elif args.action == 'list_python_defs':
        result = list_python_defs(params)
    elif args.action == 'ssh_command':
        result = ssh_command(params)
    else:
        result = {"status": "error", "message": f"Unknown action {args.action}"}

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()