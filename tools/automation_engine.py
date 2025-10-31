import os
import json
import time
import sys
import argparse
import subprocess
import glob
from datetime import datetime

RULES_FILE = 'data/automation_rules.json'
STATE_FILE = 'data/automation_state.json'
EVENT_TYPES_FILE = 'data/automation_events.json'
NDJSON_REGISTRY_FILE = 'system_settings.ndjson'


def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)


def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def load_tool_registry():
    """Load tool registry from system_settings.ndjson to get correct script paths"""
    tool_paths = {}
    
    if not os.path.exists(NDJSON_REGISTRY_FILE):
        print('[REGISTRY WARNING] system_settings.ndjson not found', flush=True)
        return tool_paths
    
    try:
        with open(NDJSON_REGISTRY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('action') == '__tool__':
                        tool_name = entry.get('tool')
                        script_path = entry.get('script_path')
                        if tool_name and script_path:
                            tool_paths[tool_name] = script_path
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f'[REGISTRY ERROR] Failed to load tool registry: {e}', flush=True)
    
    return tool_paths


def get_script_path(tool_name, registry):
    """Get script path for a tool, with fallback to legacy format"""
    if tool_name in registry:
        return registry[tool_name]
    
    # Fallback to legacy format if not in registry
    print(f'[REGISTRY WARNING] Tool {tool_name} not in registry, using fallback path', flush=True)
    return f"tools/{tool_name}.py"


def resolve_context_values(params, context):
    """Simple context resolution - replace {key} with values from context"""
    if isinstance(params, dict):
        return {k: resolve_context_values(v, context) for k, v in params.items()}
    elif isinstance(params, list):
        return [resolve_context_values(item, context) for item in params]
    elif isinstance(params, str):
        # Simple string replacement
        resolved = params
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            if placeholder in resolved:
                resolved = resolved.replace(placeholder, str(value))
        return resolved
    else:
        return params


def run_action(action, context):
    """Execute a single action or multi-step workflow"""
    try:
        # Check if this is a multi-step workflow
        if 'steps' in action:
            return run_workflow_steps(action['steps'], context)

        # Single action execution
        raw_params = action.get('params', {})
        resolved_params = resolve_context_values(raw_params, context)

        print('[PARAMS]', json.dumps(resolved_params), flush=True)

        # Check if tool exists in registry - if not, call directly (for utility scripts)
        registry = load_tool_registry()
        tool_name = action['tool']

        if tool_name in registry:
            # Use execution_hub.py for registered tools
            cmd = ['python3', 'execution_hub.py', 'execute_task', '--params', json.dumps({
                "tool_name": tool_name,
                "action": action['action'],
                "params": resolved_params
            })]
        else:
            # Direct call for utility scripts not in registry
            print(f'[DIRECT CALL] Tool {tool_name} not in registry, calling directly', flush=True)
            script = f"tools/{tool_name}.py"
            cmd = ['python3', script, action['action'], '--params', json.dumps(resolved_params)]

        print('[RUN]', ' '.join(cmd), flush=True)
        subprocess.run(cmd)

    except Exception as e:
        print('[RUN ERROR]', str(e), flush=True)


def run_workflow_steps(steps, initial_context):
    """Execute workflow steps sequentially with simplified context passing"""
    context = initial_context.copy()
    previous_output = {}
    registry = load_tool_registry()

    print(f'[WORKFLOW] Starting with context: {list(context.keys())}', flush=True)

    for i, step in enumerate(steps):
        try:
            # Build step context
            step_context = context.copy()
            step_context['prev'] = previous_output

            # Handle foreach step type
            if step.get('type') == 'foreach':
                array_path = step.get('array')
                sub_steps = step.get('steps', [])

                print(f'[STEP {i+1}] foreach over {array_path}', flush=True)

                # Extract array from context using simple dot notation
                try:
                    array_data = step_context
                    for part in array_path.split('.'):
                        array_data = array_data[part]

                    # Process each item
                    foreach_results = []
                    for idx, item in enumerate(array_data):
                        print(f'[FOREACH {idx+1}] Processing item', flush=True)

                        # Create item context
                        item_context = step_context.copy()
                        item_context['item'] = item
                        item_context['index'] = idx

                        # Execute sub-steps
                        for sub_step in sub_steps:
                            resolved_step = resolve_context_values(sub_step, item_context)

                            # Check registry for tool routing
                            if resolved_step['tool'] in registry:
                                cmd = ['python3', 'execution_hub.py', 'execute_task', '--params', json.dumps({
                                    "tool_name": resolved_step['tool'],
                                    "action": resolved_step['action'],
                                    "params": resolved_step['params']
                                })]
                            else:
                                cmd = ['python3', f"tools/{resolved_step['tool']}.py",
                                       resolved_step['action'], '--params', json.dumps(resolved_step['params'])]

                            result = subprocess.run(cmd, capture_output=True, text=True)

                            try:
                                sub_output = json.loads(result.stdout.strip())
                            except json.JSONDecodeError:
                                sub_output = {"status": "completed", "output": result.stdout.strip()}

                            item_context['prev'] = sub_output

                        foreach_results.append(sub_output)

                    previous_output = {"results": foreach_results, "processed_count": len(foreach_results)}
                    continue

                except Exception as e:
                    print(f'[FOREACH ERROR] {str(e)}', flush=True)
                    return {"status": "error", "message": f"Foreach step failed: {str(e)}"}

            # Regular step processing
            print(f'[STEP {i+1}] {step["tool"]}.{step["action"]}', flush=True)

            raw_params = step.get('params', {})

            # Simple context resolution
            resolved_params = resolve_context_values(raw_params, step_context)

            print(f'[STEP {i+1}] Resolved params: {resolved_params}', flush=True)

            # Check registry for tool routing
            if step['tool'] in registry:
                cmd = ['python3', 'execution_hub.py', 'execute_task', '--params', json.dumps({
                    "tool_name": step['tool'],
                    "action": step['action'],
                    "params": resolved_params
                })]
            else:
                cmd = ['python3', f"tools/{step['tool']}.py", step['action'], '--params', json.dumps(resolved_params)]

            result = subprocess.run(cmd, capture_output=True, text=True)

            print(f'[STEP {i+1}] Exit code: {result.returncode}', flush=True)
            if result.stderr:
                print(f'[STEP {i+1}] stderr: {result.stderr}', flush=True)

            # Parse step output
            try:
                step_output = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                step_output = {"status": "completed", "output": result.stdout.strip()}

            print(f'[STEP {i+1}] Output status: {step_output.get("status", "unknown")}', flush=True)

            # Update context for next step
            previous_output = step_output

            # Stop on error
            if step_output.get("status") == "error":
                print(f'[WORKFLOW ERROR] Step {i+1} failed: {step_output.get("message", "Unknown error")}', flush=True)
                return step_output

        except Exception as e:
            error_result = {"status": "error", "message": f"Step {i+1} execution failed: {str(e)}"}
            print(f'[WORKFLOW ERROR] {error_result["message"]}', flush=True)
            return error_result

    print(f'[WORKFLOW] Completed {len(steps)} steps successfully', flush=True)
    return previous_output


def check_time_trigger(rule):
    from datetime import datetime
    now = datetime.now()
    current_time = now.strftime('%H:%M')
    trigger = rule.get('trigger', {})
    if trigger.get('at') == current_time:
        return True
    if trigger.get('daily'):
        return now.strftime('%H:%M') == trigger['daily']
    return False


def check_interval_trigger(rule, state):
    """Check if enough time has passed for interval trigger"""
    from datetime import datetime
    trigger = rule.get('trigger', {})
    interval_minutes = trigger.get('minutes', 5)

    # Create unique key for this rule
    rule_key = f"interval_{id(rule)}"

    # Get last execution time
    last_execution = state.get('interval_executions', {}).get(rule_key)

    if last_execution is None:
        # First execution
        return True, rule_key

    # Check if enough time has passed
    now = datetime.now()
    last_time = datetime.fromisoformat(last_execution)
    minutes_passed = (now - last_time).total_seconds() / 60

    if minutes_passed >= interval_minutes:
        return True, rule_key

    return False, rule_key


def detect_triggered_entries(trigger_type, path, state):
    new_data = read_json(path)
    old_data = state.get(path, {})
    new_entries = new_data.get('entries', {})
    old_entries = old_data.get('entries', {})
    test_expr = read_json(EVENT_TYPES_FILE).get(trigger_type, {}).get('test')
    if not test_expr:
        return [], old_data
    triggered = []
    for key, new_entry in new_entries.items():
        old_entry = old_entries.get(key, {})
        ctx = {'key': key, 'old_entry': old_entry, 'new_entry': new_entry}
        try:
            if eval(test_expr, {}, ctx):
                triggered.append((key, new_entry))
        except Exception as e:
            print('[EVAL ERROR]', str(e), flush=True)
    return triggered, new_data


def detect_file_triggers(trigger_type, directory, pattern, state):
    """Detect new files in directory matching pattern"""
    if not os.path.exists(directory):
        return []
    
    # Get current files
    pattern_path = os.path.join(directory, pattern)
    current_files = set(os.path.basename(f) for f in glob.glob(pattern_path))
    
    # Get previous files from state
    state_key = f"files_{directory}_{pattern}"
    old_files = set(state.get(state_key, []))
    
    # Update state
    state[state_key] = list(current_files)
    
    # Find new files
    new_files = current_files - old_files
    
    # Filter using test expression
    test_expr = read_json(EVENT_TYPES_FILE).get(trigger_type, {}).get('test')
    if not test_expr:
        return []
    
    triggered = []
    for filename in new_files:
        ctx = {
            'filename': filename,
            'old_files': old_files,
            'new_files': current_files
        }
        try:
            if eval(test_expr, {}, ctx):
                triggered.append(filename)
        except Exception as e:
            print(f'[FILE EVAL ERROR] {str(e)}', flush=True)
    
    return triggered


def extract_guest_name_from_filename(filename):
    """Extract guest name from filename - handles various formats"""
    # Remove extension
    base = os.path.splitext(filename)[0]
    
    # Replace underscores with spaces and title case
    guest_name = base.replace('_', ' ').title()
    
    return guest_name


def dispatch_event(event_key, payload):
    rules = read_json(RULES_FILE).get('rules', [])
    matched = []
    for rule in rules:
        trigger = rule.get('trigger', {})
        if trigger.get('type') == 'event' and trigger.get('event_key') == event_key:
            context = payload.copy()
            run_action(rule['action'], context)
            matched.append(rule)
    return {'status': 'ok', 'message': f'{len(matched)} event-based rule(s) triggered.', 'event': event_key}


def engine_loop():
    print(json.dumps({'status': 'ok', 'message': 'Automation Engine is running'}), flush=True)
    state = read_json(STATE_FILE)
    
    while True:
        rules = read_json(RULES_FILE).get('rules', [])
        
        # Track processed files
        processed_files = {}
        activity_occurred = False
        
        for rule in rules:
            trigger = rule.get('trigger', {})
            trig_type = trigger.get('type')
            file_path = trigger.get('file')

            if trig_type in ('entry_added', 'entry_updated'):
                # Only process each file once per iteration
                if file_path not in processed_files:
                    triggered, updated = detect_triggered_entries(trig_type, file_path, state)
                    processed_files[file_path] = (triggered, updated)
                else:
                    triggered, updated = processed_files[file_path]
                
                for key, new_entry in triggered:
                    # Check rule-specific condition
                    rule_condition = rule.get("condition")
                    if rule_condition:
                        try:
                            ctx = {
                                "key": key,
                                "old_entry": state.get(file_path, {}).get("entries", {}).get(key, {}),
                                "new_entry": new_entry
                            }
                            if not eval(rule_condition, {}, ctx):
                                continue
                        except Exception as e:
                            print("[CONDITION ERROR]", str(e), flush=True)
                            continue

                    # Build context for action - flat structure
                    context = {"entry_key": key}
                    # Add all entry fields directly to context (no nesting)
                    for k, v in new_entry.items():
                        if k != "entry_key":  # Avoid duplicate
                            context[k] = v
                    
                    print("[TRIGGER]", key, flush=True)
                    run_action(rule["action"], context)
                    activity_occurred = True

            elif trig_type == 'file_created':
                # Handle file system triggers
                directory = trigger.get('directory')
                pattern = trigger.get('pattern', '*')
                
                if directory:
                    triggered_files = detect_file_triggers(trig_type, directory, pattern, state)
                    
                    for filename in triggered_files:
                        # Build file context
                        base_filename = os.path.splitext(filename)[0]
                        guest_name = extract_guest_name_from_filename(filename)
                        
                        # Load transcript index for condition checking
                        transcript_index = read_json('data/transcript_index.json')
                        old_entries = transcript_index.get('entries', {})
                        
                        context = {
                            'filename': filename,
                            'base_filename': base_filename,
                            'guest_name': guest_name,
                            'directory': directory,
                            'old_entries': old_entries
                        }
                        
                        # Check rule condition
                        rule_condition = rule.get("condition")
                        if rule_condition:
                            try:
                                if not eval(rule_condition, {}, context):
                                    print(f"[FILE CONDITION] Skipping {filename} - condition not met", flush=True)
                                    continue
                            except Exception as e:
                                print(f"[FILE CONDITION ERROR] {str(e)}", flush=True)
                                continue
                        
                        print(f"[FILE TRIGGER] {filename}", flush=True)
                        run_action(rule['action'], context)
                        activity_occurred = True

            elif trig_type == 'time':
                if check_time_trigger(rule):
                    print('[TRIGGER] (time)', flush=True)
                    run_action(rule['action'], {})
                    activity_occurred = True

            elif trig_type == 'interval':
                should_execute, rule_key = check_interval_trigger(rule, state)
                if should_execute:
                    from datetime import datetime
                    print('[TRIGGER] (interval)', flush=True)
                    run_action(rule['action'], {})

                    # Update last execution time
                    if 'interval_executions' not in state:
                        state['interval_executions'] = {}
                    state['interval_executions'][rule_key] = datetime.now().isoformat()

                    activity_occurred = True

        # Update state for processed files
        for file_path, (triggered, updated) in processed_files.items():
            state[file_path] = updated
            
        write_json(STATE_FILE, state)
        
        if activity_occurred:
            print(f"[ENGINE] Processed {len(processed_files)} files, activity detected", flush=True)
        
        time.sleep(60)


def add_rule(params):
    required_trigger_keys = {'type'}
    if not isinstance(params, dict):
        return {'status': 'error', 'message': 'Params must be a dictionary.'}
    
    trigger = params.get('trigger')
    action = params.get('action')
    
    if not isinstance(trigger, dict) or not required_trigger_keys.issubset(trigger):
        return {'status': 'error', 'message': "Trigger must be a dict with at least 'type'."}
    
    if not isinstance(action, dict):
        return {'status': 'error', 'message': "Action must be a dictionary."}
    
    # Validate action format
    if 'steps' in action:
        # Multi-step workflow validation
        steps = action.get('steps')
        if not isinstance(steps, list) or len(steps) == 0:
            return {'status': 'error', 'message': 'Workflow steps must be a non-empty list.'}
        
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return {'status': 'error', 'message': f'Step {i+1} must be a dictionary.'}
            
            required_step_keys = {'tool', 'action', 'params'}
            if not required_step_keys.issubset(step.keys()):
                return {'status': 'error', 'message': f'Step {i+1} must have tool, action, and params.'}
            
            if not isinstance(step['params'], dict):
                return {'status': 'error', 'message': f'Step {i+1} params must be a dictionary.'}
    else:
        # Single action validation
        required_action_keys = {'tool', 'action', 'params'}
        if not required_action_keys.issubset(action.keys()):
            return {'status': 'error', 'message': "Single action must have 'tool', 'action', and 'params'."}
        
        if not isinstance(action['params'], dict):
            return {'status': 'error', 'message': 'Action params must be a dictionary.'}
    
    allowed_keys = {'trigger', 'action', 'condition'}
    if not set(params).issubset(allowed_keys):
        return {'status': 'error', 'message': 'Unexpected keys in rule definition.'}
    
    data = read_json(RULES_FILE)
    rules = data.get('rules', [])
    rules.append(params)
    data['rules'] = rules
    write_json(RULES_FILE, data)
    return {'status': 'success', 'message': 'Rule added.'}


def update_rule(params):
    index = params.get('index')
    new_rule = params.get('rule')
    
    if not isinstance(index, int):
        return {'status': 'error', 'message': 'Index must be an integer.'}
    if not isinstance(new_rule, dict):
        return {'status': 'error', 'message': 'Rule must be a dictionary.'}

    # Same validation as add_rule
    required_trigger_keys = {'type'}
    trigger = new_rule.get('trigger')
    action = new_rule.get('action')

    if not isinstance(trigger, dict) or not required_trigger_keys.issubset(trigger):
        return {'status': 'error', 'message': "Trigger must be a dict with at least 'type'."}
    
    if not isinstance(action, dict):
        return {'status': 'error', 'message': "Action must be a dictionary."}
    
    # Validate action format
    if 'steps' in action:
        steps = action.get('steps')
        if not isinstance(steps, list) or len(steps) == 0:
            return {'status': 'error', 'message': 'Workflow steps must be a non-empty list.'}
        
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return {'status': 'error', 'message': f'Step {i+1} must be a dictionary.'}
            
            required_step_keys = {'tool', 'action', 'params'}
            if not required_step_keys.issubset(step.keys()):
                return {'status': 'error', 'message': f'Step {i+1} must have tool, action, and params.'}
            
            if not isinstance(step['params'], dict):
                return {'status': 'error', 'message': f'Step {i+1} params must be a dictionary.'}
    else:
        required_action_keys = {'tool', 'action', 'params'}
        if not required_action_keys.issubset(action.keys()):
            return {'status': 'error', 'message': "Single action must have 'tool', 'action', and 'params'."}
        
        if not isinstance(action['params'], dict):
            return {'status': 'error', 'message': 'Action params must be a dictionary.'}

    allowed_keys = {'trigger', 'action', 'condition'}
    if not set(new_rule).issubset(allowed_keys):
        return {'status': 'error', 'message': 'Unexpected keys in rule definition.'}

    data = read_json(RULES_FILE)
    rules = data.get('rules', [])
    if 0 <= index < len(rules):
        rules[index] = new_rule
        data['rules'] = rules
        write_json(RULES_FILE, data)
        return {'status': 'success', 'message': f'Rule {index} updated.'}

    return {'status': 'error', 'message': 'Invalid rule index.'}


def add_event_type(params):
    if not isinstance(params, dict):
        return {'status': 'error', 'message': 'Params must be a dictionary.'}
    key = params.get('key')
    expr = params.get('test')
    if not isinstance(key, str) or not key.strip():
        return {'status': 'error', 'message': 'Event type key must be a non-empty string.'}
    if not isinstance(expr, str) or not expr.strip():
        return {'status': 'error', 'message': 'Test expression must be a non-empty string.'}
    allowed_keys = {'key', 'test'}
    if not set(params).issubset(allowed_keys):
        return {'status': 'error', 'message': 'Unexpected keys in event type definition.'}
    data = read_json(EVENT_TYPES_FILE)
    data[key] = {'test': expr}
    write_json(EVENT_TYPES_FILE, data)
    return {'status': 'success', 'message': f"Event type '{key}' added."}


def update_event_type(params):
    if not isinstance(params, dict):
        return {'status': 'error', 'message': 'Params must be a dictionary.'}
    key = params.get('key')
    expr = params.get('test')
    if not isinstance(key, str) or not key.strip():
        return {'status': 'error', 'message': 'Event type key must be a non-empty string.'}
    if not isinstance(expr, str) or not expr.strip():
        return {'status': 'error', 'message': 'Test expression must be a non-empty string.'}
    allowed_keys = {'key', 'test'}
    if not set(params).issubset(allowed_keys):
        return {'status': 'error', 'message': 'Unexpected keys in event type definition.'}
    data = read_json(EVENT_TYPES_FILE)
    if key in data:
        data[key]['test'] = expr
        write_json(EVENT_TYPES_FILE, data)
        return {'status': 'success', 'message': f"Event type '{key}' updated."}
    return {'status': 'error', 'message': 'Event type not found.'}


def get_rules(params):
    data = read_json(RULES_FILE)
    rules = data.get('rules', [])
    return {'status': 'ok', 'rules': rules}


def get_event_types(params):
    data = read_json(EVENT_TYPES_FILE)
    return {'status': 'ok', 'events': data}


def delete_rule(params):
    index = params.get('index')
    if not isinstance(index, int):
        return {'status': 'error', 'message': 'Index must be an integer.'}

    data = read_json(RULES_FILE)
    rules = data.get('rules', [])

    if 0 <= index < len(rules):
        removed = rules.pop(index)
        data['rules'] = rules
        write_json(RULES_FILE, data)
        return {'status': 'success', 'message': f'Rule {index} deleted.', 'deleted_rule': removed}

    return {'status': 'error', 'message': 'Invalid rule index.'}


def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'run_engine':
        result = engine_loop()
    elif args.action == 'add_rule':
        result = add_rule(params)
    elif args.action == 'update_rule':
        result = update_rule(params)
    elif args.action == 'add_event_type':
        result = add_event_type(params)
    elif args.action == 'update_event_type':
        result = update_event_type(params)
    elif args.action == 'dispatch_event':
        result = dispatch_event(params.get('event_key'), params)
    elif args.action == 'get_rules':
        result = get_rules(params)
    elif args.action == 'get_event_types':
        result = get_event_types(params)
    elif args.action == 'delete_rule':
        result = delete_rule(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()