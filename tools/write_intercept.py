#!/usr/bin/env python3
"""
Centralized Write Intercept System for Protected Files

Intercepts terminal_tool write actions against files that have dedicated tools.
Returns error messages with exact tool/action/param signatures to use instead.

Loads protection rules from data/protected_files.json with mtime-based caching.
Error messages from data/error_handlers.json.
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, Optional, Tuple

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PROTECTED_FILES_PATH = os.path.join(PROJECT_ROOT, "data", "protected_files.json")
ERROR_HANDLERS_PATH = os.path.join(PROJECT_ROOT, "data", "error_handlers.json")
WRITE_INTERCEPT_LOG = os.path.join(PROJECT_ROOT, "data", "write_interceptions.log")

# Cache for protected files and error handlers
_protected_files_cache: Dict = {}
_protected_files_mtime: float = 0
_error_handlers_cache: Dict = {}
_error_handlers_mtime: float = 0


def _load_protected_files() -> Dict:
    """Load protected files config with mtime-based cache reload."""
    global _protected_files_cache, _protected_files_mtime

    try:
        current_mtime = os.path.getmtime(PROTECTED_FILES_PATH)
        if current_mtime != _protected_files_mtime:
            with open(PROTECTED_FILES_PATH, "r") as f:
                _protected_files_cache = json.load(f)
            _protected_files_mtime = current_mtime
    except (FileNotFoundError, json.JSONDecodeError) as e:
        if not _protected_files_cache:
            _protected_files_cache = {}

    return _protected_files_cache


def _load_error_handlers() -> Dict:
    """Load error handlers config with mtime-based cache reload."""
    global _error_handlers_cache, _error_handlers_mtime

    try:
        current_mtime = os.path.getmtime(ERROR_HANDLERS_PATH)
        if current_mtime != _error_handlers_mtime:
            with open(ERROR_HANDLERS_PATH, "r") as f:
                _error_handlers_cache = json.load(f)
            _error_handlers_mtime = current_mtime
    except (FileNotFoundError, json.JSONDecodeError) as e:
        if not _error_handlers_cache:
            _error_handlers_cache = {}

    return _error_handlers_cache


def _log_interception(action: str, filename: str, redirect_to: str, blocked: bool = True):
    """Log write interceptions to data/write_interceptions.log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "attempted_action": action,
        "target_file": filename,
        "redirect_to": redirect_to,
        "blocked": blocked
    }

    try:
        os.makedirs(os.path.dirname(WRITE_INTERCEPT_LOG), exist_ok=True)
        with open(WRITE_INTERCEPT_LOG, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass


def _get_basename(filepath: str) -> str:
    """Extract filename from any path format"""
    return os.path.basename(filepath.replace("\\", "/"))


def _get_error_message(filename: str, block_level: str = "full") -> dict:
    """Get error message from error_handlers.json for a protected file."""
    error_handlers = _load_error_handlers()
    handler_key = f"protected_file__{filename}"

    if handler_key in error_handlers:
        handler = error_handlers[handler_key]
        message = handler.get("message", f"Cannot write to {filename}")
        tool = handler.get("tool", "unknown")
        actions = handler.get("actions", "")

        if block_level == "absolute":
            return {
                "status": "error",
                "message": f"🚫 ABSOLUTELY PROTECTED: {filename}",
                "severity": "CRITICAL",
                "reason": "This file must NEVER be modified via code under any circumstances.",
                "instruction": "Ask the user to manually update this file if needed."
            }

        return {
            "status": "error",
            "message": f"🚫 PROTECTED FILE: {filename}",
            "use_instead": tool,
            "available_actions": actions,
            "instruction": message,
            "hint": f"Use execution_hub: python3 execution_hub.py execute_task --params '{{\"tool_name\": \"{tool}\", \"action\": \"...\", \"params\": {{...}}}}'"
        }

    # Fallback if no error handler defined
    protected_files = _load_protected_files()
    if filename in protected_files:
        config = protected_files[filename]
        tool = config.get("tool", "unknown")
        actions = config.get("actions", {})
        block_level = config.get("block_level", "full")

        if block_level == "absolute":
            return {
                "status": "error",
                "message": f"🚫 ABSOLUTELY PROTECTED: {filename}",
                "severity": "CRITICAL",
                "reason": "This file must NEVER be modified via code.",
                "instruction": "Manual edit only."
            }

        action_list = ", ".join(actions.keys()) if isinstance(actions, dict) else str(actions)
        return {
            "status": "error",
            "message": f"🚫 PROTECTED FILE: {filename}",
            "use_instead": tool,
            "available_actions": action_list,
            "hint": f"Use {tool} tool via execution_hub instead of direct write."
        }

    return {
        "status": "error",
        "message": f"🚫 PROTECTED FILE: {filename}",
        "instruction": "Use the appropriate tool for this file."
    }


def check_protected_write(action: str, params: dict) -> Optional[dict]:
    """
    Check if a write action targets a protected file.

    Args:
        action: The terminal_tool action (write_file_text, append_file_text, etc.)
        params: The params dict with filepath/filename

    Returns:
        None if write is allowed, or error dict with redirect instructions
    """
    # Only intercept write actions
    write_actions = [
        "write_file_text",
        "write_file",
        "append_file_text",
        "replace_lines",
        "patch_function_in_file",
        "insert_new_function_in_script",
        "write_python_script",
        "delete_function_from_script"
    ]
    if action not in write_actions:
        return None

    # Extract filepath from various param names
    filepath = (
        params.get("filepath") or
        params.get("filename") or
        params.get("path") or
        params.get("file") or
        params.get("file_path") or
        ""
    )

    if not filepath:
        return None

    basename = _get_basename(filepath)
    protected_files = _load_protected_files()

    # Check exact matches
    if basename in protected_files:
        config = protected_files[basename]
        block_level = config.get("block_level", "full")
        tool = config.get("tool", "unknown")

        error = _get_error_message(basename, block_level)
        _log_interception(action, filepath, tool, blocked=True)
        return error

    # Check pattern matches for task queue files (claude_task_q*.json)
    if basename.startswith("claude_task_q") and basename.endswith(".json"):
        error = _get_error_message("claude_task_q1.json", "full")  # Use q1 as template
        _log_interception(action, filepath, "claude_assistant", blocked=True)
        return error

    # Not protected, allow write
    return None


def check_command_for_protected_writes(command: str) -> Optional[dict]:
    """
    Parse a shell command to detect writes to protected files.

    Checks for:
    - > or >> redirect operators
    - sed -i (in-place edit)
    - cp/mv targeting protected files

    Args:
        command: The shell command string

    Returns:
        None if no protected write detected, or error dict
    """
    protected_files = _load_protected_files()
    protected_basenames = set(protected_files.keys())

    # Also check for pattern matches
    def is_protected(filename: str) -> Tuple[bool, str]:
        basename = _get_basename(filename)
        if basename in protected_basenames:
            return True, basename
        # Check for task queue pattern
        if basename.startswith("claude_task_q") and basename.endswith(".json"):
            return True, basename
        return False, ""

    # Check for redirect operators (> or >>)
    redirect_patterns = [
        r'>\s*([^\s;|&]+)',   # > filename
        r'>>\s*([^\s;|&]+)',  # >> filename
    ]

    for pattern in redirect_patterns:
        matches = re.findall(pattern, command)
        for match in matches:
            protected, basename = is_protected(match)
            if protected:
                config = protected_files.get(basename, {})
                block_level = config.get("block_level", "full")
                error = _get_error_message(basename, block_level)
                _log_interception("redirect", match, "blocked", blocked=True)
                error["detected_in"] = f"redirect operator in: {command[:100]}"
                return error

    # Check for sed -i (in-place edit)
    sed_pattern = r'sed\s+(-[a-zA-Z]*i[a-zA-Z]*|\-\-in-place)\s+.*?([^\s;|&]+\.json)'
    sed_matches = re.findall(sed_pattern, command)
    for _, filename in sed_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("sed -i", filename, "blocked", blocked=True)
            error["detected_in"] = f"sed -i command: {command[:100]}"
            return error

    # Alternative sed pattern
    sed_alt_pattern = r'sed\s+-i\s+.*?\s+([^\s;|&]+)'
    sed_alt_matches = re.findall(sed_alt_pattern, command)
    for filename in sed_alt_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("sed -i", filename, "blocked", blocked=True)
            error["detected_in"] = f"sed -i command: {command[:100]}"
            return error

    # Check for cp/mv targeting protected files
    cp_mv_pattern = r'(cp|mv)\s+[^\s;|&]+\s+([^\s;|&]+)'
    cp_mv_matches = re.findall(cp_mv_pattern, command)
    for cmd, target in cp_mv_matches:
        protected, basename = is_protected(target)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception(cmd, target, "blocked", blocked=True)
            error["detected_in"] = f"{cmd} command: {command[:100]}"
            return error

    # Check for tee command (writes to file while also outputting)
    tee_pattern = r'tee\s+(-a\s+)?([^\s;|&]+)'
    tee_matches = re.findall(tee_pattern, command)
    for _, filename in tee_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("tee", filename, "blocked", blocked=True)
            error["detected_in"] = f"tee command: {command[:100]}"
            return error

    # Check for echo/printf with redirect to JSON files
    echo_printf_pattern = r'(?:echo|printf)\s+.*?>\s*([^\s;|&]+\.json)'
    echo_matches = re.findall(echo_printf_pattern, command)
    for filename in echo_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("echo/printf redirect", filename, "blocked", blocked=True)
            error["detected_in"] = f"echo/printf command: {command[:100]}"
            return error

    # Check for cat heredoc (cat << EOF > file.json or cat <<EOF > file.json)
    cat_heredoc_pattern = r'cat\s*<<[^\s]*\s*.*?>\s*([^\s;|&]+\.json)'
    cat_matches = re.findall(cat_heredoc_pattern, command)
    for filename in cat_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("cat heredoc", filename, "blocked", blocked=True)
            error["detected_in"] = f"cat heredoc command: {command[:100]}"
            return error

    # Check for python -c with open(..., 'w') targeting JSON files
    python_open_pattern = r'python3?\s+-c\s+.*?open\s*\([^)]*["\']([^"\']+\.json)["\'].*?["\']w["\']'
    python_open_matches = re.findall(python_open_pattern, command, re.IGNORECASE)
    for filename in python_open_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("python -c open(w)", filename, "blocked", blocked=True)
            error["detected_in"] = f"python -c command: {command[:100]}"
            return error

    # Check for python -c with json.dump and file path
    python_dump_pattern = r'python3?\s+-c\s+.*?json\.dump.*?["\']([^"\']+\.json)["\']'
    python_dump_matches = re.findall(python_dump_pattern, command, re.IGNORECASE)
    for filename in python_dump_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("python -c json.dump", filename, "blocked", blocked=True)
            error["detected_in"] = f"python -c command: {command[:100]}"
            return error

    # Check for jq with redirect to JSON file
    jq_pattern = r'jq\s+.*?>\s*([^\s;|&]+\.json)'
    jq_matches = re.findall(jq_pattern, command)
    for filename in jq_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("jq redirect", filename, "blocked", blocked=True)
            error["detected_in"] = f"jq command: {command[:100]}"
            return error

    # Check for awk with redirect to JSON file
    awk_pattern = r'awk\s+.*?>\s*([^\s;|&]+\.json)'
    awk_matches = re.findall(awk_pattern, command)
    for filename in awk_matches:
        protected, basename = is_protected(filename)
        if protected:
            config = protected_files.get(basename, {})
            block_level = config.get("block_level", "full")
            error = _get_error_message(basename, block_level)
            _log_interception("awk redirect", filename, "blocked", blocked=True)
            error["detected_in"] = f"awk command: {command[:100]}"
            return error

    # No protected write detected
    return None


def intercept_terminal_write(action: str, params: dict) -> Tuple[bool, Optional[dict]]:
    """
    Main entry point for terminal_tool write interception.

    Args:
        action: The action being attempted
        params: The params dict

    Returns:
        Tuple of (should_block, error_response)
        - (False, None) = proceed with write
        - (True, error_dict) = block and return error
    """
    error = check_protected_write(action, params)
    if error:
        return (True, error)
    return (False, None)


def intercept_terminal_command(command: str) -> Tuple[bool, Optional[dict]]:
    """
    Entry point for run_terminal_command interception.

    Args:
        command: The shell command to check

    Returns:
        Tuple of (should_block, error_response)
    """
    error = check_command_for_protected_writes(command)
    if error:
        return (True, error)
    return (False, None)


# CLI for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python write_intercept.py check_write <action> <filepath>")
        print("  python write_intercept.py check_command '<shell command>'")
        print("\nProtected files (from data/protected_files.json):")
        protected = _load_protected_files()
        for fname, config in protected.items():
            tool = config.get("tool", "unknown")
            level = config.get("block_level", "full")
            print(f"  {fname} -> {tool} [{level}]")
        sys.exit(0)

    mode = sys.argv[1]

    if mode == "check_write" and len(sys.argv) >= 4:
        action = sys.argv[2]
        filepath = sys.argv[3]
        blocked, error = intercept_terminal_write(action, {"filepath": filepath})
        if blocked:
            print(json.dumps(error, indent=2))
        else:
            print(f"Write allowed: {filepath}")

    elif mode == "check_command" and len(sys.argv) >= 3:
        command = sys.argv[2]
        blocked, error = intercept_terminal_command(command)
        if blocked:
            print(json.dumps(error, indent=2))
        else:
            print(f"Command allowed: {command}")

    else:
        print("Invalid arguments. Run without args for usage.")
