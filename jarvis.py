from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import subprocess, json, os, logging
import threading  # <-- added for running buffer loop in background

from tools import json_manager
from tools.smart_json_dispatcher import orchestrate_write
from system_guard import validate_action, ContractViolation
from tools.buffer_engine import buffer_loop  # <-- import buffer loop

app = FastAPI()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.mount(
    "/semantic_memory",
    StaticFiles(directory=os.path.join(BASE_DIR, "semantic_memory")),
    name="semantic_memory"
)

app.mount(
    "/landing_page_template_thumbnails",
    StaticFiles(directory=os.path.join(BASE_DIR, "landing_page_template_thumbnails")),
    name="landing_page_template_thumbnails"
)

SIGNUPS_FILE = os.path.join(BASE_DIR, "data/orchestrate_signups.json")
SYSTEM_REGISTRY = os.path.join(BASE_DIR, "system_settings.ndjson")
WORKING_MEMORY_PATH = os.path.join(BASE_DIR, "data/working_memory.json")
EXEC_HUB_PATH = os.path.join(BASE_DIR, "execution_hub.py")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 🚀 Start buffer loop when FastAPI starts
@app.on_event("startup")
def start_buffer_loop():
    def run_loop():
        logging.info("📢 Starting buffer loop in background...")
        buffer_loop()
    threading.Thread(target=run_loop, daemon=True).start()

def run_script(tool_name, action, params):
    command = [
        "python3", EXEC_HUB_PATH, "execute_task", "--params", json.dumps({
            "tool_name": tool_name,
            "action": action,
            "params": params
        })
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": "Execution failed", "details": str(e)}

@app.post("/execute_task")
async def execute_task(request: Request):
    try:
        request_data = await request.json()
        tool_name = request_data.get("tool_name")
        action_name = request_data.get("action")
        params = request_data.get("params", {})

        if not tool_name or not action_name:
            raise HTTPException(status_code=400, detail="Missing tool_name or action.")

        # 🔐 Intercept system-level thread reset
        if tool_name == "system_control" and action_name == "load_orchestrate_os":
            result = subprocess.run(
                ["python3", EXEC_HUB_PATH, "load_orchestrate_os"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return json.loads(result.stdout.strip())

        # Custom handler passthrough
        if tool_name == "json_manager" and action_name == "orchestrate_write":
            return orchestrate_write(**params)

        # Validate contract and execute tool
        params = validate_action(tool_name, action_name, params)
        result = run_script(tool_name, action_name, params)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result)

        return result

    except ContractViolation as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": "Execution failed",
            "details": str(e)
        })

@app.get("/get_supported_actions")
def get_supported_actions():
    try:
        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]
        return {"status": "success", "supported_actions": entries}
    except Exception as e:
        logging.error(f"🚨 Failed to load registry: {e}")
        raise HTTPException(status_code=500, detail="Could not load registry.")

@app.post("/load_memory")
def load_memory():
    try:
        abs_path = os.path.abspath(WORKING_MEMORY_PATH)
        with open(abs_path, "r", encoding="utf-8") as f:
            memory = json.load(f)

        if not isinstance(memory, dict):
            raise ValueError("working_memory.json must be a top-level dict")

        return {
            "status": "success",
            "loaded": len(memory),
            "memory": memory
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": "Cannot load working_memory.json",
            "details": str(e)
        })

@app.get("/")
def root():
    return {"status": "Jarvis core is online."}

SIGNUPS_PATH = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/data/orchestrate_signups.json"
THANK_YOU_PAGE = "/semantic_memory/thankyou.html"

@app.post("/api/landing-capture")
async def capture_signup(name: str = Form(...), email: str = Form(...)):
    if not os.path.exists(SIGNUPS_PATH):
        with open(SIGNUPS_PATH, "w") as f:
            json.dump({}, f)

    with open(SIGNUPS_PATH, "r") as f:
        data = json.load(f)

    timestamp = datetime.utcnow().isoformat()
    entry_key = f"{email.lower()}_{timestamp}"

    data[entry_key] = {
        "name": name,
        "email": email,
        "timestamp": timestamp
    }

    with open(SIGNUPS_PATH, "w") as f:
        json.dump(data, f, indent=2)

    return RedirectResponse(url=THANK_YOU_PAGE, status_code=302)

@app.post("/save_form_entry")
async def save_form_entry(request: Request):
    try:
        payload = await request.json()

        # Run the Python tool as a subprocess
        proc = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "tools/save_form_entry.py")],
            input=json.dumps(payload),
            text=True,
            capture_output=True
        )

        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=proc.stderr)

        return json.loads(proc.stdout.strip())

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))