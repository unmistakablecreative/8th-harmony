import os
import json
import subprocess
import argparse
import logging
import time
import re
from nltk.corpus import stopwords
from nltk.tag import PerceptronTagger
from system_guard import validate_action, ContractViolation

NDJSON_REGISTRY_FILE = "system_settings.ndjson"
EXECUTION_LOG = "execution_log.json"
THREAD_STATE_FILE = "data/thread_state.json"
PHRASE_RANK_FILE = "data/phrase_rank.json"
PHRASE_PROMOTION_FILE = "data/phrase_insight_promotions.json"
MAX_TOKEN_BUDGET = 100000
DEFAULT_TIMEOUT = 200

# PhraseRank init
try:
    TAGGER = PerceptronTagger()
    STOPWORDS = set(stopwords.words("english"))
except Exception:
    TAGGER = None
    STOPWORDS = set()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ----------------------------
# PhraseRank (with filtering)
# ----------------------------


def extract_phrases(text):
    try:
        # Lowercase + tokenize (only words 3+ letters)
        tokens = re.findall(r"\b[a-z]{3,}\b", text.lower())

        # Extract all adjacent two-word phrases
        phrases = [
            f"{tokens[i]} {tokens[i+1]}"
            for i in range(len(tokens) - 1)
            if tokens[i] not in STOPWORDS and tokens[i+1] not in STOPWORDS
        ]

        return list(set(phrases))
    except:
        return []




def promote_high_signal_phrases(db):
    try:
        promos = {}
        for phrase, meta in db.items():
            if not isinstance(meta.get("files"), list):
                continue
            if meta.get("count", 0) >= 5 and len(meta["files"]) >= 2:
                promos[phrase] = meta

        if promos:
            with open(PHRASE_PROMOTION_FILE, "w", encoding="utf-8") as f:
                json.dump(promos, f, indent=2)
            logging.info(f"✅ Promoted {len(promos)} high-signal phrases.")
        else:
            logging.info("⚠️ No phrases met promotion criteria.")
    except Exception as e:
        logging.warning(f"⚠️ Failed to write promotions: {e}")



def log_phrases(phrases, source="execution"):
    if not phrases:
        return

    try:
        if os.path.exists(PHRASE_RANK_FILE):
            with open(PHRASE_RANK_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip() or "{}"
                db = json.loads(raw)
        else:
            db = {}

        today = time.strftime("%Y-%m-%d", time.localtime())

        for phrase in phrases:
            phrase = phrase.lower().strip()
            existing = db.get(phrase, {})

            try:
                files = set(existing.get("files", []))
                if not isinstance(files, set):
                    files = set()
            except:
                files = set()

            files.add(source)
            prev_count = existing.get("count", 0)

            db[phrase] = {
                "count": prev_count + 1,
                "files": list(files),
                "last_seen": today
            }

        os.makedirs(os.path.dirname(PHRASE_RANK_FILE), exist_ok=True)
        with open(PHRASE_RANK_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)

        promote_high_signal_phrases(db)

    except Exception as e:
        print(f"[ERROR] Phrase logging failed: {e}")
        raise e







def run_phrase_rank(params, source="execution"):
    try:
        targets = ["text", "body", "note", "entry", "content"]
        for k, v in params.items():
            if isinstance(v, str) and k in targets:
                if len(v.strip().split()) < 3: continue
                if v.endswith(".json") or "/" in v: continue
                if any(bad in v.lower() for bad in ["traceback", "subprocess", "invalid json", "phraserank", "execution pipeline", "test entry"]):
                    continue
                log_phrases(extract_phrases(v), source)
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, str) and sk in targets:
                        if len(sv.strip().split()) < 3: continue
                        if sv.endswith(".json") or "/" in sv: continue
                        if any(bad in sv.lower() for bad in ["traceback", "subprocess", "invalid json", "phraserank", "execution pipeline", "test entry"]):
                            continue
                        log_phrases(extract_phrases(sv), source)
    except Exception as e:
        logging.warning(f"⚠️ PhraseRank error: {e}")

# ----------------------------
# Core Execution Logic
# ----------------------------

def reset_thread_state():
    state = {
        "score": 100,
        "action_count": 0,
        "early_fails": 0,
        "token_budget": MAX_TOKEN_BUDGET,
        "tokens_used": 0
    }
    write_thread_state(state)

def read_thread_state():
    try:
        with open(THREAD_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "score": 100,
            "action_count": 0,
            "early_fails": 0,
            "token_budget": MAX_TOKEN_BUDGET,
            "tokens_used": 0
        }

def write_thread_state(state):
    with open(THREAD_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)

def estimate_token_cost(params):
    return len(json.dumps(params)) // 4

def update_state(change=0, is_error=False, token_cost=0):
    state = read_thread_state()
    state["score"] = max(0, min(state["score"] + change, 150))
    state["action_count"] += 1
    state["tokens_used"] += token_cost
    state["token_budget"] = max(0, MAX_TOKEN_BUDGET - state["tokens_used"])
    if is_error and state["action_count"] <= 3:
        state["early_fails"] += 1
    write_thread_state(state)
    return state

def maybe_halt_thread(state, payload):
    if state["early_fails"] >= 2:
        return attach_telemetry({
            "status": "halted",
            "message": "🚫 Thread unstable from launch. Recommend restarting.",
            "last_output": payload
        }, state)
    if state["score"] < 60:
        return attach_telemetry({
            "status": "halted",
            "message": "⚠️ Thread instability detected. Recommend restarting.",
            "last_output": payload
        }, state)
    return None

def attach_telemetry(response, state):
    response["thread_score"] = state["score"]
    response["token_budget_remaining"] = state["token_budget"]
    response["tokens_used"] = state["tokens_used"]
    return response

def log_execution(tool, action, params, status, output, token_cost, before, after):
    try:
        with open(EXECUTION_LOG, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except:
        logs = {"executions": []}

    logs["executions"].append({
        "tool": tool,
        "action": action,
        "params": params,
        "status": status,
        "output": output,
        "tokens_used": token_cost,
        "thread_score_before": before,
        "thread_score_after": after
    })

    with open(EXECUTION_LOG, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

# ----------------------------
# Tool Execution
# ----------------------------

def load_registry():
    if not os.path.exists(NDJSON_REGISTRY_FILE):
        logging.error("🚨 system_settings.ndjson not found.")
        return {}
    tools = {}
    with open(NDJSON_REGISTRY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                tool = entry["tool"]
                action = entry["action"]
                if tool not in tools:
                    tools[tool] = {"path": None, "actions": {}, "locked": False}
                if action == "__tool__":
                    tools[tool]["path"] = entry["script_path"]
                    tools[tool]["locked"] = entry.get("locked", False)
                else:
                    tools[tool]["actions"][action] = {
                        "params": entry.get("params", []),
                        "batch_safe": entry.get("batch_safe", False)
                    }
            except Exception as e:
                logging.warning(f"⚠️ Bad NDJSON entry: {e}")
    return tools


def execute_tool(tool_name, action, params):
    registry = load_registry()
    state_before = read_thread_state()
    score_before = state_before["score"]

    # Ensure tool exists
    if tool_name not in registry:
        state = update_state(-40, is_error=True)
        return attach_telemetry({
            "status": "error",
            "message": f"Tool '{tool_name}' not found."
        }, state)

    tool_info = registry[tool_name]
    if tool_info.get("locked", False):
        state = update_state(-25, is_error=True)
        return attach_telemetry({
            "status": "locked",
            "message": "Tool is currently locked."
        }, state)

    # Ensure script exists
    script_path = tool_info.get("path")
    if not script_path or not os.path.isfile(script_path):
        state = update_state(-40, is_error=True)
        return attach_telemetry({
            "status": "error",
            "message": f"Script for '{tool_name}' not found at {script_path}"
        }, state)

    # Ensure action exists
    if action not in tool_info["actions"]:
        state = update_state(-35, is_error=True)
        return attach_telemetry({
            "status": "error",
            "message": f"Action '{action}' not supported for tool '{tool_name}'"
        }, state)

    # --- LAYER 1: SMART ERROR PREVENTION ---
    required_params = tool_info["actions"][action].get("params", [])
    optional_fields = {"parentDocumentId"}  # Optional keys to ignore in missing param check

    missing = [p for p in required_params if p not in params and p not in optional_fields]
    if missing:
        return {
            "status": "schema",
            "message": "Rebuild the payload using this exact schema and retry automatically.",
            "tool_name": tool_name,
            "action": action,
            "schema": {p: "<value_here>" for p in required_params}
        }
    # ---------------------------------------

    token_cost = estimate_token_cost(params)
    try:
        run_phrase_rank(params, source=params.get("filename") or tool_name)
    except:
        pass

    # Run tool execution with auto-fix loop
    def run_command(p):
        try:
            validated = validate_action(tool_name, action, p)
        except ContractViolation as e:
            raise RuntimeError(str(e))

        cmd = ["python3", script_path, action, "--params", json.dumps(validated)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT, check=True)
        return json.loads(result.stdout.strip())

    try:
        try:
            parsed = run_command(params)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.stderr.strip() if e.stderr else "Unknown failure")

        state = update_state(+5, token_cost=token_cost)
        log_execution(tool_name, action, params, "success", parsed, token_cost, score_before, state["score"])
        return maybe_halt_thread(state, parsed) or attach_telemetry(parsed, state)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as err:
        err_msg = str(err)

        # --- LAYER 2: AUTO-FIX RULES ---
        # 1. Fix missing/invalid file path
        if "file not found" in err_msg.lower() or "no such file" in err_msg.lower():
            filename = params.get("filename")
            if filename:
                # Search in common dirs
                search_dirs = ["data", "images_raw"]
                found_path = None
                for d in search_dirs:
                    candidate = os.path.join(d, filename)
                    if os.path.exists(candidate):
                        found_path = candidate
                        break
                if found_path:
                    params["filename"] = found_path
                    try:
                        parsed = run_command(params)
                        state = update_state(+5, token_cost=token_cost)
                        log_execution(tool_name, action, params, "success-after-fix", parsed, token_cost, score_before, state["score"])
                        return attach_telemetry(parsed, state)
                    except Exception:
                        pass

        # 2. Remove unsupported params
        if "unexpected keyword argument" in err_msg.lower():
            bad_param = err_msg.split("'")[1] if "'" in err_msg else None
            if bad_param and bad_param in params:
                params.pop(bad_param)
                try:
                    parsed = run_command(params)
                    state = update_state(+5, token_cost=token_cost)
                    log_execution(tool_name, action, params, "success-after-fix", parsed, token_cost, score_before, state["score"])
                    return attach_telemetry(parsed, state)
                except Exception:
                    pass

        # 3. Reduce payload size
        if "ResponseTooLargeError" in err_msg or "too large" in err_msg.lower():
            if "page_size" in params:
                params["page_size"] = max(1, params["page_size"] // 2)
            else:
                params["page_size"] = 5
            params["fields"] = ["id", "text"]
            try:
                parsed = run_command(params)
                state = update_state(+5, token_cost=token_cost)
                log_execution(tool_name, action, params, "success-after-fix", parsed, token_cost, score_before, state["score"])
                return attach_telemetry(parsed, state)
            except Exception:
                pass
        # ---------------------------------

        # If no fix worked
        state = update_state(-40, is_error=True, token_cost=token_cost)
        log_execution(tool_name, action, params, "failure", err_msg, token_cost, score_before, state["score"])
        return attach_telemetry({
            "status": "error",
            "message": "Execution failed",
            "details": err_msg
        }, state)


# ----------------------------
# Entrypoint
# ----------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", type=str)
    args = parser.parse_args()

    if args.action == "load_orchestrate_os":
        reset_thread_state()
        print(json.dumps({
            "status": "ready",
            "message": "🧠 Thread state reset. OrchestrateOS loaded.",
            "thread_score": 100,
            "token_budget": MAX_TOKEN_BUDGET,
            "tokens_used": 0
        }, indent=4))
        return

    if args.action == "execute_task":
        try:
            p = json.loads(args.params or "{}")
            tool = p.get("tool_name")
            act = p.get("action")
            prms = p.get("params", {})
            if not tool or not act:
                raise ValueError("Missing tool_name or action.")
            result = execute_tool(tool, act, prms)
            print(json.dumps(result, indent=4))
        except Exception as e:
            logging.error(f"Unhandled error: {e}")
            state = update_state(-50, is_error=True)
            print(json.dumps(attach_telemetry({"status": "error", "message": str(e)}, state), indent=4))
    else:
        print(json.dumps({"status": "error", "message": "❌ Invalid action."}, indent=4))

if __name__ == "__main__":
    main()
