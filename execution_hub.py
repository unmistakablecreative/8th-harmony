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
THREAD_INTENT_FILE = "data/thread_intent.json"
PHRASE_RANK_FILE = "data/phrase_rank.json"
PHRASE_PROMOTION_FILE = "data/phrase_insight_promotions.json"
MAX_TOKEN_BUDGET = 100000
DEFAULT_TIMEOUT = 200

# ----------------------------
# PhraseRank (with filtering)
# ----------------------------

try:
    TAGGER = PerceptronTagger()
    STOPWORDS = set(stopwords.words("english"))
except Exception:
    TAGGER = None
    STOPWORDS = set()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def extract_phrases(text):
    try:
        tokens = re.findall(r"\b[a-z]{3,}\b", text.lower())
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
            files = set(existing.get("files", []))
            files.add(source)
            db[phrase] = {
                "count": existing.get("count", 0) + 1,
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
                if len(v.strip().split()) < 3:
                    continue
                if v.endswith(".json") or "/" in v:
                    continue
                if any(bad in v.lower() for bad in ["traceback", "subprocess", "invalid json", "phraserank", "execution pipeline", "test entry"]):
                    continue
                log_phrases(extract_phrases(v), source)
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, str) and sk in targets:
                        if len(sv.strip().split()) < 3:
                            continue
                        if sv.endswith(".json") or "/" in sv:
                            continue
                        if any(bad in sv.lower() for bad in ["traceback", "subprocess", "invalid json", "phraserank", "execution pipeline", "test entry"]):
                            continue
                        log_phrases(extract_phrases(sv), source)
    except Exception as e:
        logging.warning(f"⚠️ PhraseRank error: {e}")

# ----------------------------
# Thread Intent Lock System
# ----------------------------

def check_thread_intent(tool_name):
    """
    Check if tool_name is allowed under current thread intent
    Returns: (blocked: bool, message: str)
    """
    if not os.path.exists(THREAD_INTENT_FILE):
        return False, ""
    
    try:
        with open(THREAD_INTENT_FILE, "r") as f:
            intent = json.load(f)
    except:
        return False, ""
    
    if not intent.get("active", False):
        return False, ""
    
    allowed_tools = intent.get("allowed_tools", [])
    
    if allowed_tools == "*":
        return False, ""
    
    if tool_name in allowed_tools:
        return False, ""
    
    intent_name = intent.get("intent", "unknown")
    message = (
        f"🚫 Tool '{tool_name}' not allowed in '{intent_name}' intent. "
        f"Allowed tools: {', '.join(allowed_tools)}. "
        f"Stay focused on the current task."
    )
    
    return True, message


def increment_intent_violations():
    """Increment violation counter in thread_intent.json"""
    if not os.path.exists(THREAD_INTENT_FILE):
        return
    
    try:
        with open(THREAD_INTENT_FILE, "r") as f:
            intent = json.load(f)
        
        intent["violations_count"] = intent.get("violations_count", 0) + 1
        
        with open(THREAD_INTENT_FILE, "w") as f:
            json.dump(intent, f, indent=2)
    except:
        pass


def reset_thread_intent():
    """Reset thread intent to free_work mode"""
    intent = {
        "active": False,
        "intent": "free_work",
        "allowed_tools": "*",
        "description": "Fresh session - no restrictions",
        "reset_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "violations_count": 0
    }
    
    os.makedirs(os.path.dirname(THREAD_INTENT_FILE), exist_ok=True)
    with open(THREAD_INTENT_FILE, "w") as f:
        json.dump(intent, f, indent=2)

# ----------------------------
# Auto-Reconstruction Logic
# ----------------------------
def load_correction_rules():
    try:
        with open("data/param_corrections.json", "r") as f:
            return json.load(f)
    except Exception as e:
        logging.warning(f"Could not load param corrections: {e}")
        return {"tool_specific_mappings": {}, "type_corrections": {}}

def reconstruct_payload(params, required_params, tool_name, action):
    rules = load_correction_rules()
    fixed_params = params.copy()
    corrections = []
    
    tool_mappings = rules.get("tool_specific_mappings", {}).get(tool_name, {})
    for wrong_param, correct_param in tool_mappings.items():
        if wrong_param in fixed_params and correct_param not in fixed_params:
            fixed_params[correct_param] = fixed_params.pop(wrong_param)
            corrections.append(f"Mapped {wrong_param} → {correct_param}")
    
    type_rules = rules.get("type_corrections", {})
    bool_rules = type_rules.get("string_to_boolean", {})
    numeric_fields = type_rules.get("string_to_integer_fields", [])
    
    for key, value in fixed_params.items():
        if isinstance(value, str):
            if value.lower() in bool_rules.get("true_values", []):
                fixed_params[key] = True
                corrections.append(f"Fixed {key}: string → boolean")
            elif value.lower() in bool_rules.get("false_values", []):
                fixed_params[key] = False
                corrections.append(f"Fixed {key}: string → boolean")
            elif value.isdigit() and key in numeric_fields:
                fixed_params[key] = int(value)
                corrections.append(f"Fixed {key}: string → integer")
    
    missing = [p for p in required_params if p not in fixed_params]
    defaults = type_rules.get("default_values", {})
    
    for param in missing:
        if param in defaults:
            if isinstance(defaults[param], dict) and tool_name in defaults[param]:
                fixed_params[param] = defaults[param][tool_name]
                corrections.append(f"Added tool-specific default {param}")
            elif not isinstance(defaults[param], dict):
                fixed_params[param] = defaults[param]
                corrections.append(f"Added default {param}")
    
    return fixed_params, corrections


# ----------------------------
# Enhanced Logging System
# ----------------------------

def log_execution(tool, action, params, result_status, result_payload, token_cost, score_before, score_after, 
                 violation=None, penalty=0, reconstruction_info=None, schema_errors=None, 
                 validation_errors=None, execution_details=None):
    try:
        os.makedirs("data", exist_ok=True)
        
        log_entry = {
            "tool": tool,
            "action": action,
            "params": params,
            "status": result_status,
            "output": result_payload,
            "violation_type": violation,
            "penalty": penalty,
            "token_cost": token_cost,
            "thread_score_before": score_before,
            "thread_score_after": score_after,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "execution_time_ms": int(time.time() * 1000) % 100000,
            "triggered_by": params.get("source") or "manual"
        }
        
        if reconstruction_info:
            log_entry["reconstruction"] = reconstruction_info
        
        if schema_errors:
            log_entry["schema_errors"] = schema_errors
            
        if validation_errors:
            log_entry["validation_errors"] = validation_errors
            
        if execution_details:
            log_entry["execution_details"] = execution_details

        path = "data/execution_log.json"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = {"executions": []}

        existing["executions"].append(log_entry)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

    except Exception as e:
        logging.warning(f"⚠️ Failed to write to execution_log.json: {e}")

def apply_early_thread_penalty(base_penalty, execution_count):
    if execution_count <= 10:
        multiplier = 4.0
    elif execution_count <= 25:
        multiplier = 2.0
    else:
        multiplier = 1.0
    
    return int(base_penalty * multiplier)

def read_thread_state():
    if os.path.exists(THREAD_STATE_FILE):
        with open(THREAD_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"score": 100, "tokens_used": 0, "execution_count": 0, "thread_started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def update_state(score_change=0, token_cost=0, is_error=False):
    state = read_thread_state()
    state["score"] = max(0, min(150, state.get("score", 100) + score_change))
    state["tokens_used"] = state.get("tokens_used", 0) + token_cost
    state["execution_count"] = state.get("execution_count", 0) + 1
    with open(THREAD_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


def attach_telemetry(original_response, state):
    if not isinstance(original_response, dict):
        safe_response = {"result": original_response}
    else:
        safe_response = original_response.copy()
    
    safe_response["thread_score"] = state.get("score", 100)
    safe_response["tokens_used"] = state.get("tokens_used", 0)
    safe_response["tokens_remaining"] = MAX_TOKEN_BUDGET - state.get("tokens_used", 0)
    safe_response["token_budget"] = MAX_TOKEN_BUDGET
    
    score = state.get("score", 100)
    if score <= 30:
        safe_response["thread_warning"] = "CRITICAL: Thread stability very low"
    elif score <= 50:
        safe_response["thread_warning"] = "WARNING: Thread stability degraded"
    
    tokens_remaining = safe_response["tokens_remaining"]
    if tokens_remaining <= 1000:
        safe_response["token_warning"] = "CRITICAL: Token budget nearly exhausted"
    elif tokens_remaining <= 5000:
        safe_response["token_warning"] = "WARNING: Token budget running low"
    
    return safe_response


def maybe_halt_thread(state, response):
    if state["score"] < 30:
        response["status"] = "halted"
        response["message"] = "🧯 Thread marked unstable. Further execution halted."
        response["halt_reason"] = "Thread score below critical threshold (30)"
    return response


def reset_thread_state(force=False):
    """Reset thread state, but only if score is below baseline (100) unless forced"""
    current_state = read_thread_state()
    current_score = current_state.get("score", 100)

    # Only reset if below baseline or forced
    if force or current_score < 100:
        state = {
            "score": 100,
            "tokens_used": 0,
            "execution_count": 0,
            "thread_started_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        with open(THREAD_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        reset_thread_intent()

        return state
    else:
        # Score is already at or above baseline, don't reset
        return current_state


def estimate_token_cost(params):
    try:
        text = json.dumps(params)
        return int(len(text.split()) * 0.75)
    except:
        return 20

# ----------------------------
# Registry Management
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

# ----------------------------
# Core Execution Logic
# ----------------------------

def execute_tool(tool_name, action, params):
    registry = load_registry()
    state_before = read_thread_state()
    score_before = state_before["score"]
    violation = None
    penalty = 0
    
    intent_blocked, intent_message = check_thread_intent(tool_name)
    if intent_blocked:
        log_execution(
            tool=tool_name,
            action=action,
            params=params,
            result_status="intent_blocked",
            result_payload={"message": intent_message},
            token_cost=0,
            score_before=score_before,
            score_after=score_before,
            violation="intent_violation",
            penalty=0
        )
        
        increment_intent_violations()
        
        response = {
            "status": "blocked",
            "message": intent_message,
            "hint": "Use system_settings.deactivate_intent to unlock all tools"
        }
        response = attach_telemetry(response, state_before)
        return response
    
    if tool_name not in registry:
        violation = "tool_not_found"
        penalty = apply_early_thread_penalty(-100, state_before.get("execution_count", 0))
        state = update_state(penalty, is_error=True)
        log_execution(tool_name, action, params, "tool_not_found", 
                     {"error": "Tool not found"}, 0, score_before, state["score"], 
                     violation, penalty, execution_details={"registry_tools": list(registry.keys())})
        
        response = {"status": "error", "message": f"Tool '{tool_name}' not found."}
        response = attach_telemetry(response, state)
        return response

    tool_info = registry[tool_name]
    
    if tool_info.get("locked", False):
        violation = "tool_locked"
        penalty = apply_early_thread_penalty(-25, state_before.get("execution_count", 0))
        state = update_state(penalty, is_error=True)
        log_execution(tool_name, action, params, "tool_locked", 
                     {"error": "Tool is locked"}, 0, score_before, state["score"], 
                     violation, penalty)
        
        response = {"status": "locked", "message": "Tool is currently locked."}
        response = attach_telemetry(response, state)
        return response

    script_path = tool_info.get("path")
    if not script_path or not os.path.isfile(script_path):
        violation = "script_missing"
        penalty = apply_early_thread_penalty(-40, state_before.get("execution_count", 0))
        state = update_state(penalty, is_error=True)
        log_execution(tool_name, action, params, "script_missing", 
                     {"error": "Script not found"}, 0, score_before, state["score"], 
                     violation, penalty, execution_details={"expected_path": script_path})
        
        response = {"status": "error", "message": f"Script for '{tool_name}' not found at {script_path}"}
        response = attach_telemetry(response, state)
        return response

    if action not in tool_info["actions"]:
        violation = "action_not_found"
        penalty = apply_early_thread_penalty(-60, state_before.get("execution_count", 0))
        state = update_state(penalty, is_error=True)
        log_execution(tool_name, action, params, "action_not_found", 
                     {"error": "Action not registered"}, 0, score_before, state["score"], 
                     violation, penalty, execution_details={"available_actions": list(tool_info["actions"].keys())})
        
        response = {"status": "error", "message": f"Action '{action}' not supported for tool '{tool_name}'"}
        response = attach_telemetry(response, state)
        return response

    if tool_name == "system_settings" and action == "install_tool":
        token_cost = estimate_token_cost(params)
        try:
            run_phrase_rank(params, source=params.get("filename") or tool_name)
        except:
            pass

        def run_command_bypass(p):
            execution_start = time.time()
            validated = p
            logging.info("✅ Full bypass for system_settings.install_tool - raw parameters passed")

            cmd = ["python3", script_path, action, "--params", json.dumps(validated)]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT, check=True)
                stdout_output = result.stdout.strip()
                
                execution_details = {
                    "command": cmd,
                    "execution_time_ms": int((time.time() - execution_start) * 1000),
                    "stdout_length": len(stdout_output),
                    "return_code": result.returncode,
                    "bypass_mode": True
                }
                
            except subprocess.TimeoutExpired:
                execution_details = {
                    "timeout": True,
                    "timeout_seconds": DEFAULT_TIMEOUT
                }
                raise RuntimeError(f"Tool execution timed out after {DEFAULT_TIMEOUT}s")
            except subprocess.CalledProcessError as e:
                execution_details = {
                    "return_code": e.returncode,
                    "stderr": e.stderr
                }
                raise RuntimeError(f"Tool execution failed: {e.stderr}")

            try:
                parsed_output = json.loads(stdout_output)
                return parsed_output, execution_details, None
            except json.JSONDecodeError:
                execution_details["json_parse_error"] = {"raw_output": stdout_output[:500]}
                raise RuntimeError(f"Invalid JSON output: {stdout_output[:100]}...")

        try:
            parsed, execution_details, _ = run_command_bypass(params)
            state = update_state(+5, token_cost=token_cost)
            
            log_execution(tool_name, action, params, "success", parsed, token_cost, 
                         score_before, state["score"], execution_details=execution_details)
            
            response = attach_telemetry(parsed, state)
            response = maybe_halt_thread(state, response)
            return response

        except Exception as err:
            penalty = apply_early_thread_penalty(-40, state_before.get("execution_count", 0))
            state = update_state(penalty, is_error=True, token_cost=token_cost)
            
            log_execution(tool_name, action, params, "runtime_failure", {"error": str(err)}, token_cost, 
                         score_before, state["score"], "runtime_error", penalty)
            
            response = {"status": "error", "message": "Execution failed", "details": str(err)}
            response = attach_telemetry(response, state)
            return response

    required_params = tool_info["actions"][action].get("params", [])
    
    missing = [p for p in required_params if p not in params]
    original_params = params.copy()
    reconstruction_info = None
    
    if missing:
        fixed_params, corrections = reconstruct_payload(params, required_params, tool_name, action)
        
        still_missing = [p for p in required_params if p not in fixed_params]
        
        reconstruction_info = {
            "attempted": True,
            "original_params": original_params,
            "missing_params": missing,
            "corrections_applied": corrections,
            "still_missing": still_missing
        }
        
        if still_missing:
            penalty = apply_early_thread_penalty(-30, state_before.get("execution_count", 0))
            state = update_state(penalty, is_error=True)
            
            schema_errors = {
                "required_params": required_params,
                "provided_params": list(params.keys()),
                "missing_params": still_missing,
                "param_schema": {p: "<required>" for p in required_params}
            }
            
            log_execution(tool_name, action, params, "reconstruction_failed", 
                         {"error": f"Could not auto-fix missing parameters: {still_missing}"}, 
                         0, score_before, state["score"], "schema_error", penalty,
                         reconstruction_info, schema_errors)
            
            response = {
                "status": "schema",
                "message": f"Could not auto-fix missing parameters: {still_missing}",
                "tool_name": tool_name,
                "action": action,
                "schema": {p: "<required>" for p in required_params},
                "missing_params": still_missing,
                "attempted_fixes": corrections
            }
            response = attach_telemetry(response, state)
            return response
        else:
            logging.info(f"✅ Auto-reconstruction successful: {', '.join(corrections)}")
            params = fixed_params
            state = update_state(+2, is_error=False)
    else:
        fixed_params, corrections = reconstruct_payload(params, required_params, tool_name, action)
        if corrections:
            logging.info(f"✅ Basic type fixes applied: {', '.join(corrections)}")
            params = fixed_params
            reconstruction_info = {
                "attempted": True,
                "original_params": original_params,
                "missing_params": [],
                "corrections_applied": corrections,
                "still_missing": []
            }

    token_cost = estimate_token_cost(params)
    try:
        run_phrase_rank(params, source=params.get("filename") or tool_name)
    except:
        pass

    def run_command(p):
        execution_start = time.time()
        execution_details = None
        validation_errors = None
        
        if tool_name == "system_settings" and action == "install_tool":
            validated = p
            logging.info("✅ Bypassing validation for system_settings.install_tool")
        else:
            try:
                validated = validate_action(tool_name, action, p)
            except ContractViolation as e:
                validation_errors = {
                    "error": str(e),
                    "params_sent": p,
                    "validation_time_ms": int((time.time() - execution_start) * 1000)
                }
                raise RuntimeError(f"Validation failed: {str(e)}")

        cmd = ["python3", script_path, action, "--params", json.dumps(validated)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT, check=True)
            stdout_output = result.stdout.strip()
            stderr_output = result.stderr.strip()
            
            execution_details = {
                "command": cmd,
                "execution_time_ms": int((time.time() - execution_start) * 1000),
                "stdout_length": len(stdout_output),
                "stderr_length": len(stderr_output),
                "return_code": result.returncode
            }
            
            if stderr_output:
                execution_details["stderr_preview"] = stderr_output[:200]
            
        except subprocess.TimeoutExpired as e:
            execution_details = {
                "command": cmd,
                "execution_time_ms": DEFAULT_TIMEOUT * 1000,
                "timeout": True,
                "timeout_seconds": DEFAULT_TIMEOUT
            }
            raise RuntimeError(f"Tool execution timed out after {DEFAULT_TIMEOUT}s")
        except subprocess.CalledProcessError as e:
            execution_details = {
                "command": cmd,
                "execution_time_ms": int((time.time() - execution_start) * 1000),
                "return_code": e.returncode,
                "stdout": e.stdout,
                "stderr": e.stderr
            }
            raise RuntimeError(f"Tool execution failed with return code {e.returncode}: {e.stderr}")

        try:
            parsed_output = json.loads(stdout_output)
            return parsed_output, execution_details, validation_errors
        except json.JSONDecodeError as e:
            execution_details["json_parse_error"] = {
                "error": str(e),
                "raw_output": stdout_output[:500],
                "output_length": len(stdout_output)
            }
            raise RuntimeError(f"Invalid JSON output from tool '{tool_name}.{action}': {stdout_output[:100]}...")

    try:
        parsed, execution_details, validation_errors = run_command(params)
        
        tool_status = parsed.get("status", "success")
        
        if tool_status == "started":
            state = update_state(+5, token_cost=token_cost)
            log_status = "async_started"
            logging.info(f"✅ Async operation started: {tool_name}.{action}")
        else:
            state = update_state(+5, token_cost=token_cost)
            log_status = "reconstruction_success" if (reconstruction_info and reconstruction_info["corrections_applied"]) else "success"
            
        log_execution(tool_name, action, params, log_status, parsed, token_cost, 
                     score_before, state["score"], reconstruction_info=reconstruction_info,
                     execution_details=execution_details)
        
        response = attach_telemetry(parsed, state)
        response = maybe_halt_thread(state, response)
        return response

    except Exception as err:
        err_msg = str(err)
        
        if "Validation failed" in err_msg:
            violation = "validation_error"
            status = "validation_error"
        elif "timed out" in err_msg:
            violation = "timeout"
            status = "timeout"
        elif "Invalid JSON output" in err_msg:
            violation = "json_parse_error"
            status = "json_parse_error"
        elif "Tool execution failed" in err_msg:
            violation = "runtime_error"
            status = "runtime_failure"
        else:
            violation = "runtime_error"
            status = "runtime_failure"
        
        penalty = apply_early_thread_penalty(-40, state_before.get("execution_count", 0))
        state = update_state(penalty, is_error=True, token_cost=token_cost)
        
        log_execution(tool_name, action, params, status, {"error": err_msg}, token_cost, 
                     score_before, state["score"], violation, penalty, reconstruction_info)
        
        response = {"status": "error", "message": "Execution failed", "details": err_msg}
        response = attach_telemetry(response, state)
        return response

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", type=str)
    args = parser.parse_args()

    if args.action == "load_orchestrate_os":
        state = reset_thread_state()
        response = {
            "status": "ready",
            "message": "🧠 Thread state reset. Thread intent reset to free_work. OrchestrateOS loaded.",
        }
        response = attach_telemetry(response, state)
        print(json.dumps(response, indent=4))
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
            state_before = read_thread_state()
            penalty = apply_early_thread_penalty(-50, state_before.get("execution_count", 0))
            state = update_state(penalty, is_error=True)
            response = {"status": "error", "message": str(e)}
            response = attach_telemetry(response, state)
            print(json.dumps(response, indent=4))
    else:
        state = read_thread_state()
        response = {"status": "error", "message": "❌ Invalid action."}
        response = attach_telemetry(response, state)
        print(json.dumps(response, indent=4))


if __name__ == "__main__":
    main()