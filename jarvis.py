from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import subprocess, json, os, logging, time, sys
import asyncio
from pathlib import Path
from collections import defaultdict

from tools import json_manager
from tools.smart_json_dispatcher import orchestrate_write
from system_guard import validate_action, ContractViolation

app = FastAPI()

# NDJSON execution logging
EXECUTION_LOG_PATH = os.path.join(os.path.dirname(__file__), "data", "execution_log.ndjson")

def log_execution(tool_name: str, action: str, params: dict, status: str):
    """Append one NDJSON line: tool_name, action, params, status, source, timestamp"""
    log_entry = {
        "tool_name": tool_name,
        "action": action,
        "params": params,
        "status": status,
        "source": "claude_ai",
        "timestamp": datetime.now().isoformat()
    }
    with open(EXECUTION_LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Rate limiting state (in-memory)
rate_limit_state = defaultdict(list)
RATE_LIMITS = {
    "/execute_task": {"requests": 60, "window_seconds": 60},
    "/get_supported_actions": {"requests": 10, "window_seconds": 60}
}

# System paths
SYSTEM_REGISTRY = os.path.join(BASE_DIR, "system_settings.ndjson")
WORKING_MEMORY_PATH = os.path.join(BASE_DIR, "data/working_memory.json")
EXEC_HUB_PATH = os.path.join(BASE_DIR, "execution_hub.py")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Static mounts
app.mount(
    "/semantic_memory",
    StaticFiles(directory=os.path.join(BASE_DIR, "semantic_memory")),
    name="semantic_memory"
)

app.mount(
    "/data",
    StaticFiles(directory=os.path.join(BASE_DIR, "data")),
    name="data"
)

@app.get("/data-nocache/{filename:path}")
async def get_data_nocache(filename: str):
    """Serve data files with no-cache headers"""
    from fastapi.responses import FileResponse
    filepath = os.path.join(BASE_DIR, "data", filename)
    if not os.path.exists(filepath):
        return {"error": "File not found"}
    return FileResponse(
        filepath,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


# Rate limiting middleware
def check_rate_limit(endpoint: str, client_id: str = "default"):
    """Check if request should be rate limited"""
    if endpoint not in RATE_LIMITS:
        return True

    config = RATE_LIMITS[endpoint]
    now = time.time()
    window_start = now - config["window_seconds"]

    key = f"{endpoint}:{client_id}"
    rate_limit_state[key] = [ts for ts in rate_limit_state[key] if ts > window_start]

    if len(rate_limit_state[key]) >= config["requests"]:
        return False

    rate_limit_state[key].append(now)
    return True


# Run a tool action via subprocess (async - does not block event loop)
async def run_script(tool_name, action, params):
    command = [
        sys.executable, EXEC_HUB_PATH, "execute_task", "--params", json.dumps({
            "tool_name": tool_name,
            "action": action,
            "params": params
        })
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
        return json.loads(stdout.decode().strip())
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"error": "Execution timed out", "details": "Task exceeded 90s limit"}
    except Exception as e:
        return {"error": "Execution failed", "details": str(e)}


# Execute a tool via HTTP POST
@app.post("/execute_task")
async def execute_task(request: Request):
    client_id = request.client.host if request.client else "unknown"
    if not check_rate_limit("/execute_task", client_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": "Too many requests. Limit: 60 req/min per client.",
                "retry_after": 60
            }
        )

    try:
        request_data = await request.json()
        tool_name = request_data.get("tool_name")
        action_name = request_data.get("action")
        params = request_data.get("params", {})

        if not tool_name or not action_name:
            raise HTTPException(status_code=400, detail="Missing tool_name or action.")

        if tool_name == "system_control" and action_name == "load_orchestrate_os":
            proc = await asyncio.create_subprocess_exec(
                sys.executable, EXEC_HUB_PATH, "load_orchestrate_os",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            log_execution(tool_name, action_name, params, "success")
            return json.loads(stdout.decode().strip())

        if tool_name == "json_manager" and action_name == "orchestrate_write":
            log_execution(tool_name, action_name, params, "success")
            return orchestrate_write(**params)

        params = validate_action(tool_name, action_name, params)
        result = await run_script(tool_name, action_name, params)

        if "error" in result:
            log_execution(tool_name, action_name, params, "error")
            raise HTTPException(status_code=500, detail=result)

        log_execution(tool_name, action_name, params, "success")
        return result

    except ContractViolation as e:
        log_execution(tool_name, action_name, params, "error")
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        log_execution(tool_name if 'tool_name' in dir() else "unknown", action_name if 'action_name' in dir() else "unknown", params if 'params' in dir() else {}, "error")
        return JSONResponse(status_code=500, content={
            "error": "Execution failed",
            "details": str(e)
        })


@app.get("/get_supported_actions")
def get_supported_actions(request: Request, offset: int = 0, limit: int = 999):
    """Return all actions (default limit=999 returns full schema in one call)"""
    client_id = request.client.host if request.client else "unknown"
    if not check_rate_limit("/get_supported_actions", client_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": "Too many requests. Limit: 10 req/min per client.",
                "retry_after": 60
            }
        )

    try:
        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]

        lean_actions = []
        for entry in entries:
            if entry.get("action") == "__tool__":
                continue

            lean_entry = {
                "tool": entry.get("tool"),
                "action": entry.get("action"),
                "params": entry.get("params", []),
                "description": entry.get("description", "")[:100]
            }
            lean_actions.append(lean_entry)

        total = len(lean_actions)
        paginated = lean_actions[offset:offset+limit]

        return {
            "status": "success",
            "supported_actions": paginated,
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "returned": len(paginated),
                "has_more": (offset + limit) < total,
                "next_offset": offset + limit if (offset + limit) < total else None
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {"status": "Jarvis core is online."}


# File Upload endpoint - accepts multipart form data
from fastapi import UploadFile, File, Form

@app.post("/upload_file")
async def upload_file(
    file: UploadFile = File(...),
    destination: str = Form(default=""),
    subfolder: str = Form(default="")
):
    """Upload a file via multipart form data.

    - destination: full path like 'semantic_memory/images/foo.png'
    - subfolder: just the directory like 'semantic_memory/images' (filename from upload)
    - If neither provided, saves to data/uploads/
    """
    try:
        if destination:
            # Full path provided
            save_path = os.path.join(BASE_DIR, destination)
        elif subfolder:
            # Directory + original filename
            save_path = os.path.join(BASE_DIR, subfolder, file.filename)
        else:
            # Default to data/uploads/
            uploads_dir = os.path.join(BASE_DIR, "data", "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            save_path = os.path.join(uploads_dir, file.filename)

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Write file
        contents = await file.read()
        with open(save_path, "wb") as f:
            f.write(contents)

        return {
            "status": "success",
            "filename": file.filename,
            "path": save_path,
            "size": len(contents),
            "content_type": file.content_type
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# NATIVE DOC EDITOR ENDPOINTS (SQLite via doc_editor.py)
# ============================================================

def _import_doc_editor():
    """Lazy import doc_editor (now SQLite-backed)"""
    import importlib
    if 'doc_editor' in sys.modules:
        return sys.modules['doc_editor']
    sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
    return importlib.import_module('doc_editor')


@app.get("/docs/list")
async def list_docs():
    """List all docs from SQLite"""
    try:
        de = _import_doc_editor()
        result = de.list_docs()
        if result.get("status") == "success":
            docs_list = []
            for doc in result.get("docs", []):
                docs_list.append({
                    "id": doc.get("id", ""),
                    "title": doc.get("title", "Untitled"),
                    "collection": doc.get("collection", ""),
                    "updated_at": doc.get("updated_at", ""),
                    "created_at": doc.get("created_at", ""),
                    "word_count": doc.get("word_count", 0),
                    "description": doc.get("description", ""),
                    "status": doc.get("status", ""),
                    "campaign_id": doc.get("campaign_id", ""),
                    "published_url": doc.get("published_url", "")
                })
            return {"status": "success", "docs": docs_list}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/docs/get/{doc_id}")
async def get_doc(doc_id: str):
    """Get single doc from SQLite"""
    try:
        de = _import_doc_editor()
        result = de.read_doc(doc_id)
        if result.get("status") == "success":
            return {"status": "success", "doc": result.get("doc", {})}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/docs/save")
async def save_doc(request: Request):
    """Save/update doc via SQLite"""
    try:
        body = await request.json()
        doc_id = body.get("id")
        de = _import_doc_editor()

        if doc_id:
            existing = de.read_doc(doc_id)
            if existing.get("status") == "success":
                existing_doc = existing.get("doc", {})
                title = body.get("title", existing_doc.get("title"))
                content = body.get("content", existing_doc.get("content", ""))
                collection = body.get("collection", existing_doc.get("collection"))

                if title != existing_doc.get("title") or collection != existing_doc.get("collection"):
                    de.update_doc(doc_id, find="", replace="", title=title, collection=collection)

                if "content" in body:
                    db = de.get_db()
                    word_count = de._count_words(content)
                    meta_desc = de._extract_meta_description(content)
                    db.execute(
                        "UPDATE docs SET content=?, word_count=?, meta_description=?, updated_at=? WHERE id=?",
                        (content, word_count, meta_desc, datetime.now().isoformat(), doc_id)
                    )
                    db.commit()

                meta_fields = {}
                for field in ["status", "description", "campaign_id", "published_url"]:
                    if field in body:
                        meta_fields[field] = body[field]
                if meta_fields:
                    de.update_metadata(doc_id, **meta_fields)

                return {"status": "success", "doc_id": doc_id}

        title = body.get("title", "Untitled")
        content = body.get("content", "")
        collection = body.get("collection", "Notes")
        result = de.create_doc(title=title, content=content, collection=collection, convert_markdown=False)
        return {"status": "success", "doc_id": result.get("doc_id", "")}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/docs/delete/{doc_id}")
async def delete_doc(doc_id: str):
    """Delete doc from SQLite"""
    try:
        de = _import_doc_editor()
        return de.delete_doc(doc_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/docs/backlinks/{doc_id}")
async def get_backlinks(doc_id: str):
    """Get backlinks from SQLite"""
    try:
        de = _import_doc_editor()
        result = de.read_backlinks(doc_id)
        if result.get("status") == "success":
            return {"status": "success", "backlinks": result.get("backlinks", [])}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/docs/link")
async def create_doc_link(request: Request):
    """Create bidirectional link in SQLite"""
    try:
        body = await request.json()
        source_doc_id = body.get("source_doc_id")
        target_doc_id = body.get("target_doc_id")
        if not source_doc_id or not target_doc_id:
            return {"status": "error", "message": "source_doc_id and target_doc_id required"}
        de = _import_doc_editor()
        return de.link_docs(source_doc_id, target_doc_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}
