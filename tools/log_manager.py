#!/usr/bin/env python3
"""
log_manager.py - Unified log query tool for OrchestrateOS

Data sources:
- data/execution_log.ndjson (real-time execution logs)
- data/claude_task_results.json (task outcomes)
- data/task_archive/tasks.jsonl (archived tasks)
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXECUTION_LOG = os.path.join(BASE_DIR, "data", "execution_log.ndjson")
TASK_RESULTS = os.path.join(BASE_DIR, "data", "claude_task_results.json")
TASKS_ARCHIVE = os.path.join(BASE_DIR, "data", "task_archive", "tasks.jsonl")


def _read_ndjson(filepath: str, limit: Optional[int] = None) -> List[Dict]:
    """Read NDJSON file, return list of dicts."""
    if not os.path.exists(filepath):
        return []
    lines = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    # Return most recent first
    lines.reverse()
    if limit:
        return lines[:limit]
    return lines


def _read_task_results() -> Dict:
    """Read task results JSON."""
    if not os.path.exists(TASK_RESULTS):
        return {}
    with open(TASK_RESULTS, "r") as f:
        data = json.load(f)
    return data.get("results", {})


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        # Handle various ISO formats
        if "T" in ts:
            return datetime.fromisoformat(ts.replace("Z", "+00:00").split("+")[0])
        return datetime.strptime(ts, "%Y-%m-%d")
    except:
        return None


def get_recent(n: int = 20, source: str = "all") -> Dict:
    """
    Get n most recent log entries.

    Args:
        n: Number of entries to return (default 20)
        source: "execution", "results", "archive", or "all"

    Returns:
        Dict with entries from requested source(s)
    """
    result = {}

    if source in ("execution", "all"):
        result["execution_log"] = _read_ndjson(EXECUTION_LOG, limit=n)

    if source in ("results", "all"):
        tasks = _read_task_results()
        # Sort by completed_at or started_at
        sorted_tasks = sorted(
            tasks.items(),
            key=lambda x: x[1].get("completed_at") or x[1].get("started_at") or "",
            reverse=True
        )[:n]
        result["task_results"] = [{"task_id": k, **v} for k, v in sorted_tasks]

    if source in ("archive", "all"):
        result["archived_tasks"] = _read_ndjson(TASKS_ARCHIVE, limit=n)

    return {"status": "success", "count": n, "data": result}


def search_by_tool(tool_name: str, limit: int = 50) -> Dict:
    """
    Search execution log by tool name.

    Args:
        tool_name: Tool to search for (e.g., "nylas_inbox", "doc_editor")
        limit: Max results (default 50)

    Returns:
        Matching execution log entries
    """
    entries = _read_ndjson(EXECUTION_LOG)
    matches = []

    for entry in entries:
        if entry.get("tool_name") == tool_name or entry.get("tool") == tool_name:
            matches.append(entry)
            if len(matches) >= limit:
                break

    return {"status": "success", "tool": tool_name, "count": len(matches), "entries": matches}


def search_by_action(action_name: str, limit: int = 50) -> Dict:
    """
    Search execution log by action name.

    Args:
        action_name: Action to search for (e.g., "send_email", "create_doc")
        limit: Max results (default 50)

    Returns:
        Matching execution log entries
    """
    entries = _read_ndjson(EXECUTION_LOG)
    matches = []

    for entry in entries:
        if entry.get("action") == action_name:
            matches.append(entry)
            if len(matches) >= limit:
                break

    return {"status": "success", "action": action_name, "count": len(matches), "entries": matches}


def search_by_status(status: str, limit: int = 50) -> Dict:
    """
    Search all logs by status.

    Args:
        status: Status to search for ("success", "error", "done", "in_progress", etc.)
        limit: Max results (default 50)

    Returns:
        Matching entries from execution log and task results
    """
    result = {"execution_log": [], "task_results": []}

    # Search execution log
    for entry in _read_ndjson(EXECUTION_LOG):
        if entry.get("status") == status:
            result["execution_log"].append(entry)
            if len(result["execution_log"]) >= limit:
                break

    # Search task results
    tasks = _read_task_results()
    for task_id, task_data in tasks.items():
        if task_data.get("status") == status:
            result["task_results"].append({"task_id": task_id, **task_data})
            if len(result["task_results"]) >= limit:
                break

    total = len(result["execution_log"]) + len(result["task_results"])
    return {"status": "success", "searched_status": status, "count": total, "data": result}


def filter_by_source(source: str, limit: int = 50) -> Dict:
    """
    Filter execution log by source (claude_ai, claude_code, etc.).

    Args:
        source: Source to filter by
        limit: Max results (default 50)

    Returns:
        Matching execution log entries
    """
    entries = _read_ndjson(EXECUTION_LOG)
    matches = []

    for entry in entries:
        if entry.get("source") == source:
            matches.append(entry)
            if len(matches) >= limit:
                break

    return {"status": "success", "source": source, "count": len(matches), "entries": matches}


def filter_by_time(hours: int = 24, source: str = "all") -> Dict:
    """
    Filter logs by time window.

    Args:
        hours: Hours to look back (default 24)
        source: "execution", "results", "archive", or "all"

    Returns:
        Entries from the time window
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    result = {}

    if source in ("execution", "all"):
        matches = []
        for entry in _read_ndjson(EXECUTION_LOG):
            ts = _parse_timestamp(entry.get("timestamp"))
            if ts and ts >= cutoff:
                matches.append(entry)
        result["execution_log"] = matches

    if source in ("results", "all"):
        matches = []
        for task_id, task_data in _read_task_results().items():
            ts = _parse_timestamp(task_data.get("completed_at") or task_data.get("started_at"))
            if ts and ts >= cutoff:
                matches.append({"task_id": task_id, **task_data})
        result["task_results"] = matches

    if source in ("archive", "all"):
        matches = []
        for entry in _read_ndjson(TASKS_ARCHIVE):
            ts = _parse_timestamp(entry.get("completed"))
            if ts and ts >= cutoff:
                matches.append(entry)
        result["archived_tasks"] = matches

    total = sum(len(v) for v in result.values())
    return {"status": "success", "hours": hours, "count": total, "data": result}


def get_task_by_id(task_id: str) -> Dict:
    """
    Get task details by ID from any source.

    Args:
        task_id: Task ID to look up

    Returns:
        Task data if found
    """
    # Check task results first (most likely for recent tasks)
    tasks = _read_task_results()
    if task_id in tasks:
        return {"status": "success", "source": "task_results", "task": {"task_id": task_id, **tasks[task_id]}}

    # Check archive
    for entry in _read_ndjson(TASKS_ARCHIVE):
        if entry.get("task_id") == task_id:
            return {"status": "success", "source": "archive", "task": entry}

    return {"status": "error", "message": f"Task {task_id} not found"}


def search_task_archive(
    keyword: str = None,
    tool_filter: str = None,
    category: str = None,
    date_from: str = None,
    date_to: str = None,
    limit: int = 50
) -> Dict:
    """
    Search the task archive with flexible filters.

    Args:
        keyword: Search in summary and actions_taken fields (case insensitive)
        tool_filter: Match tasks mentioning this tool name in summary or actions_taken
        category: Exact match on category field
        date_from: Filter by completed date >= this (ISO format)
        date_to: Filter by completed date <= this (ISO format)
        limit: Max results (default 50)

    Returns:
        Dict with status, count, and matching entries
    """
    entries = []

    # Parse date filters
    from_dt = _parse_timestamp(date_from) if date_from else None
    to_dt = _parse_timestamp(date_to) if date_to else None

    # If to_dt has no time component (midnight), set to end of day
    # This fixes single-day queries where tasks completed during the day would be skipped
    if to_dt and to_dt.hour == 0 and to_dt.minute == 0 and to_dt.second == 0:
        to_dt = to_dt.replace(hour=23, minute=59, second=59)

    # Read and filter task archive (don't use _read_ndjson - we need forward order and all entries)
    if not os.path.exists(TASKS_ARCHIVE):
        return {"status": "error", "message": "Task archive not found"}

    with open(TASKS_ARCHIVE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Category filter (exact match)
            if category and entry.get("category") != category:
                continue

            # Date filters
            if from_dt or to_dt:
                completed_dt = _parse_timestamp(entry.get("completed"))
                if not completed_dt:
                    continue
                if from_dt and completed_dt < from_dt:
                    continue
                if to_dt and completed_dt > to_dt:
                    continue

            # Prepare searchable text
            summary = (entry.get("summary") or "").lower()
            actions = entry.get("actions_taken") or []
            if isinstance(actions, list):
                actions_text = " ".join(str(a) for a in actions).lower()
            else:
                actions_text = str(actions).lower()
            combined_text = f"{summary} {actions_text}"

            # Keyword filter (case insensitive)
            if keyword and keyword.lower() not in combined_text:
                continue

            # Tool filter (search for tool name in text)
            if tool_filter and tool_filter.lower() not in combined_text:
                continue

            # Build result entry
            entries.append({
                "task_id": entry.get("task_id"),
                "summary": entry.get("summary"),
                "completed": entry.get("completed"),
                "category": entry.get("category"),
                "actions_taken": entry.get("actions_taken")
            })

            if len(entries) >= limit:
                break

    return {
        "status": "success",
        "count": len(entries),
        "entries": entries
    }


def get_summary(hours: int = 24) -> Dict:
    """
    Get aggregated summary across all log sources.

    Args:
        hours: Hours to look back (default 24)

    Returns:
        Summary stats: tool usage, action counts, status breakdown, error count
    """
    cutoff = datetime.now() - timedelta(hours=hours)

    summary = {
        "period_hours": hours,
        "execution_log": {
            "total": 0,
            "by_tool": defaultdict(int),
            "by_action": defaultdict(int),
            "by_status": defaultdict(int),
            "by_source": defaultdict(int)
        },
        "task_results": {
            "total": 0,
            "by_status": defaultdict(int),
            "avg_execution_time": 0
        },
        "archived_tasks": {
            "total": 0,
            "by_category": defaultdict(int)
        }
    }

    # Execution log stats
    exec_times = []
    for entry in _read_ndjson(EXECUTION_LOG):
        ts = _parse_timestamp(entry.get("timestamp"))
        if ts and ts >= cutoff:
            summary["execution_log"]["total"] += 1
            summary["execution_log"]["by_tool"][entry.get("tool_name") or entry.get("tool", "unknown")] += 1
            summary["execution_log"]["by_action"][entry.get("action", "unknown")] += 1
            summary["execution_log"]["by_status"][entry.get("status", "unknown")] += 1
            summary["execution_log"]["by_source"][entry.get("source", "unknown")] += 1

    # Task results stats
    for task_id, task_data in _read_task_results().items():
        ts = _parse_timestamp(task_data.get("completed_at") or task_data.get("started_at"))
        if ts and ts >= cutoff:
            summary["task_results"]["total"] += 1
            summary["task_results"]["by_status"][task_data.get("status", "unknown")] += 1
            if task_data.get("execution_time_seconds"):
                exec_times.append(task_data["execution_time_seconds"])

    if exec_times:
        summary["task_results"]["avg_execution_time"] = round(sum(exec_times) / len(exec_times), 2)

    # Archive stats
    for entry in _read_ndjson(TASKS_ARCHIVE):
        ts = _parse_timestamp(entry.get("completed"))
        if ts and ts >= cutoff:
            summary["archived_tasks"]["total"] += 1
            summary["archived_tasks"]["by_category"][entry.get("category", "unknown")] += 1

    # Convert defaultdicts to regular dicts for JSON serialization
    summary["execution_log"]["by_tool"] = dict(summary["execution_log"]["by_tool"])
    summary["execution_log"]["by_action"] = dict(summary["execution_log"]["by_action"])
    summary["execution_log"]["by_status"] = dict(summary["execution_log"]["by_status"])
    summary["execution_log"]["by_source"] = dict(summary["execution_log"]["by_source"])
    summary["task_results"]["by_status"] = dict(summary["task_results"]["by_status"])
    summary["archived_tasks"]["by_category"] = dict(summary["archived_tasks"]["by_category"])

    return {"status": "success", "summary": summary}


# Action dispatcher for execution_hub
ACTIONS = {
    "get_recent": get_recent,
    "search_by_tool": search_by_tool,
    "search_by_action": search_by_action,
    "search_by_status": search_by_status,
    "filter_by_source": filter_by_source,
    "filter_by_time": filter_by_time,
    "get_task_by_id": get_task_by_id,
    "get_summary": get_summary,
    "search_task_archive": search_task_archive
}


def execute(action: str, params: Dict = None) -> Dict:
    """Main entry point for execution_hub."""
    params = params or {}

    if action not in ACTIONS:
        return {"status": "error", "message": f"Unknown action: {action}. Available: {list(ACTIONS.keys())}"}

    try:
        return ACTIONS[action](**params)
    except Exception as e:
        return {"status": "error", "action": action, "message": str(e)}


if __name__ == "__main__":
    import sys
    import argparse

    if len(sys.argv) < 2:
        print("Usage: python3 log_manager.py <action> --params '{...}'")
        print(f"Actions: {list(ACTIONS.keys())}")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", type=str, default="{}")
    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}
    result = execute(args.action, params)
    print(json.dumps(result, indent=2, default=str))
