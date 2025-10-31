import sys
import json
import os
import argparse


def flatten_params(params):
    """Flatten any nested dicts that snuck in - force everything to top level"""
    flattened = {}
    
    # Common keys that GPT nests data under - unwrap these completely
    UNWRAP_KEYS = {'entry_data', 'data', 'fields', 'content', 'updates'}
    
    for key, value in params.items():
        if isinstance(value, dict) and key in UNWRAP_KEYS:
            # Unwrap completely - pull nested keys directly to top level
            flattened.update(value)
        elif isinstance(value, dict):
            # Other nested dicts - flatten with prefix (but avoid double-nesting)
            for nested_key, nested_value in value.items():
                flat_key = f"{key}_{nested_key}" if key != 'entry_data' else nested_key
                flattened[flat_key] = nested_value
        else:
            flattened[key] = value
    
    return flattened


def validate_flat_params(params):
    """Validate that no parameter values are dicts or complex structures"""
    for key, value in params.items():
        if isinstance(value, dict):
            raise ValueError(f"Parameter '{key}' contains nested data - all params must be flat")
        if isinstance(value, list):
            # Lists are OK for specific fields like entry_keys, recovery_signals, etc.
            continue
    return True


def render_as_table(results, columns=None):
    """Convert JSON results to markdown table"""
    if not results:
        return "No results found."

    # Auto-detect columns if not specified
    if columns is None:
        # Get common keys from first few entries
        sample = list(results.values())[:3] if isinstance(results, dict) else results[:3]
        all_keys = set().union(*[entry.keys() for entry in sample if isinstance(entry, dict)])
        # Add entry_key as first column if results is a dict
        if isinstance(results, dict):
            columns = ['entry_key'] + list(all_keys)
        else:
            columns = list(all_keys)

    # Build table header
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join(["---" for _ in columns]) + "|"

    # Build rows
    rows = []
    if isinstance(results, dict):
        # Include entry_key in each row
        for entry_key, entry_value in results.items():
            if isinstance(entry_value, dict):
                row_data = {'entry_key': entry_key}
                row_data.update(entry_value)
                row = "| " + " | ".join([str(row_data.get(col, "")) for col in columns]) + " |"
                rows.append(row)
    else:
        # No entry_key for list results
        for entry in results:
            if isinstance(entry, dict):
                row = "| " + " | ".join([str(entry.get(col, "")) for col in columns]) + " |"
                rows.append(row)

    return "\n".join([header, separator] + rows)


def render_as_markdown(results):
    """Convert to markdown list with hierarchy"""
    if not results:
        return "No results found."
    
    output = []
    entries = results.values() if isinstance(results, dict) else results
    
    for entry in entries:
        if not isinstance(entry, dict):
            continue
            
        title = entry.get("title", "Untitled")
        status = entry.get("status", "")
        priority = entry.get("priority", "")
        
        # Build list item with formatting
        item = f"**{title}**"
        if status:
            item += f" `{status}`"
        if priority:
            item += f" ⚡{priority}"
        
        output.append(f"- {item}")
        
        # Add description if present
        if desc := entry.get("description"):
            output.append(f"  {desc[:100]}...")
    
    return "\n".join(output)


def render_as_summary(results):
    """Aggregate statistics about results"""
    if not results:
        return "No results found."
    
    entries = list(results.values() if isinstance(results, dict) else results)
    total = len(entries)
    
    # Count by status
    status_counts = {}
    for entry in entries:
        if isinstance(entry, dict):
            status = entry.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
    
    # Count by type
    type_counts = {}
    for entry in entries:
        if isinstance(entry, dict):
            entry_type = entry.get("type", "unknown")
            type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
    
    # Build summary
    summary = [f"**Total:** {total} entries\n"]
    
    if status_counts:
        summary.append("**By Status:**")
        for status, count in sorted(status_counts.items()):
            summary.append(f"- {status}: {count}")
    
    if type_counts:
        summary.append("\n**By Type:**")
        for type_name, count in sorted(type_counts.items()):
            summary.append(f"- {type_name}: {count}")
    
    return "\n".join(summary)


def insert_json_entry_from_template(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    template_name = params['template_name']
    data_dir = os.path.join(os.getcwd(), 'data')
    template_path = os.path.join(data_dir, template_name)
    filepath = os.path.join(data_dir, filename)
    
    if not os.path.exists(template_path):
        return {'status': 'error', 'message': f"❌ Template '{template_name}' not found."}
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_data = json.load(f)
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    data.setdefault('entries', {})
    data['entries'][str(entry_key)] = template_data
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    return {'status': 'success', 'message': f"✅ Inserted entry '{entry_key}' from template."}


def create_json_file_from_template(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    template_name = params['template_name']
    new_filename = os.path.basename(params['new_filename'])
    data_dir = os.path.join(os.getcwd(), 'data')
    template_path = os.path.join(data_dir, template_name)
    new_file_path = os.path.join(data_dir, new_filename)
    
    if not os.path.exists(template_path):
        return {'status': 'error', 'message': f"❌ Template '{template_name}' not found."}
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_data = json.load(f)
    
    with open(new_file_path, 'w', encoding='utf-8') as f:
        json.dump(template_data, f, indent=4)
    
    return {'status': 'success', 'message': f"✅ Created file '{new_filename}' from template."}


def batch_add_field_to_json_entries(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated = 0
    for key in entry_keys:
        if key in data.get('entries', {}):
            data['entries'][key][field_name] = field_value
            updated += 1
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    return {'status': 'success', 'message': f"✅ Field '{field_name}' added to {updated} entries."}


def add_field_to_json_entry(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if entry_key in data.get('entries', {}):
        data['entries'][entry_key][field_name] = field_value
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message': f"✅ Field '{field_name}' added to entry '{entry_key}'."}
    
    return {'status': 'error', 'message': '❌ Entry not found.'}


def search_json_entries(params):
    """Search entries - supports field filters or fallback blob search WITH RENDERING"""
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    case_insensitive = params.get('case_insensitive', True)
    max_results = params.get('max_results', 50)
    fields_to_return = params.get('fields_to_return', [])
    format_type = params.get('format', 'json')  # NEW: format parameter

    search_value = params.get('search_value', '').lower()
    control_keys = {'filename', 'search_value', 'case_insensitive', 'fields_to_return', 'max_results', 'format'}
    field_filters = {k: v for k, v in params.items() if k not in control_keys}

    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': f'❌ File not found: {filename}'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get('entries', {})
    results = {}

    for entry_key, entry_value in entries.items():
        match = True

        # Apply field filters first
        for f_key, f_val in field_filters.items():
            field_val = entry_value.get(f_key)
            if field_val is None:
                match = False
                break

            if case_insensitive:
                if str(field_val).lower() != str(f_val).lower():
                    match = False
                    break
            else:
                if str(field_val) != str(f_val):
                    match = False
                    break

        # If no field filters, fallback to blob search
        if not field_filters and search_value:
            blob = json.dumps(entry_value).lower()
            if search_value not in blob:
                match = False

        if match:
            if fields_to_return:
                filtered = {k: entry_value.get(k) for k in fields_to_return}
                results[entry_key] = filtered
            else:
                results[entry_key] = entry_value

            if len(results) >= max_results:
                break

    # NEW: Apply rendering based on format
    if format_type == "table":
        output = render_as_table(results)
        return {'status': 'success', 'output': output, 'format': 'table', 'match_count': len(results)}
    elif format_type == "markdown":
        output = render_as_markdown(results)
        return {'status': 'success', 'output': output, 'format': 'markdown', 'match_count': len(results)}
    elif format_type == "summary":
        output = render_as_summary(results)
        return {'status': 'success', 'output': output, 'format': 'summary', 'match_count': len(results)}
    else:
        # Default: raw JSON
        return {'status': 'success', 'results': results, 'match_count': len(results)}


def search_json_entries_chunked(params):
    """Search entries in chunks to handle large result sets"""
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    keyword = params.get('search_value', '').lower()
    chunk_size = params.get('chunk_size', 20)
    chunk_index = params.get('chunk_index', 0)
    
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': f'❌ File not found: {filename}'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entries = data.get('entries', {})
    
    # Find all matching entries first
    all_matches = {}
    for entry_key, entry_value in entries.items():
        entry_blob = json.dumps(entry_value).lower()
        if keyword in entry_blob:
            all_matches[entry_key] = entry_value
    
    # Convert to list for chunking
    match_items = list(all_matches.items())
    total_matches = len(match_items)
    
    # Calculate chunk boundaries
    start_idx = chunk_index * chunk_size
    end_idx = min(start_idx + chunk_size, total_matches)
    
    # Get chunk data
    chunk_items = match_items[start_idx:end_idx]
    chunk_results = dict(chunk_items)
    
    return {
        'status': 'success',
        'results': chunk_results,
        'search_info': {
            'keyword': keyword,
            'chunk_index': chunk_index,
            'chunk_size': chunk_size,
            'total_matches': total_matches,
            'matches_in_chunk': len(chunk_results),
            'total_chunks': (total_matches + chunk_size - 1) // chunk_size if total_matches > 0 else 0,
            'has_more_chunks': end_idx < total_matches
        }
    }


def list_json_entries(params):
    """List entries - use list_json_entries_chunked for large files"""
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entries = data.get('entries', {})
    
    # Warn if entries might be too large
    if len(entries) > 50:
        return {
            'status': 'warning', 
            'message': f'File has {len(entries)} entries - use list_json_entries_chunked to avoid response size limits',
            'entry_count': len(entries),
            'suggestion': 'Use list_json_entries_chunked with chunk_size parameter'
        }
    
    return {'status': 'success', 'entries': entries}


def list_json_entries_chunked(params):
    """List entries in chunks to handle large files"""
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    chunk_size = params.get('chunk_size', 20)
    chunk_index = params.get('chunk_index', 0)
    
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entries = data.get('entries', {})
    
    # Convert to list for chunking
    entry_items = list(entries.items())
    total_entries = len(entry_items)
    
    # Calculate chunk boundaries
    start_idx = chunk_index * chunk_size
    end_idx = min(start_idx + chunk_size, total_entries)
    
    # Get chunk data
    chunk_items = entry_items[start_idx:end_idx]
    chunk_entries = dict(chunk_items)
    
    return {
        'status': 'success',
        'entries': chunk_entries,
        'chunk_info': {
            'chunk_index': chunk_index,
            'chunk_size': chunk_size,
            'total_entries': total_entries,
            'entries_in_chunk': len(chunk_entries),
            'total_chunks': (total_entries + chunk_size - 1) // chunk_size if total_entries > 0 else 0,
            'has_more_chunks': end_idx < total_entries
        }
    }


def batch_delete_json_entries(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    deleted_count = 0
    for key in entry_keys:
        if key in data.get('entries', {}):
            del data['entries'][key]
            deleted_count += 1
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    return {'status': 'success', 'message': f'✅ Deleted {deleted_count} entries.'}


def delete_json_entry(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if entry_key in data.get('entries', {}):
        del data['entries'][entry_key]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message': f"✅ Entry '{entry_key}' deleted."}
    
    return {'status': 'error', 'message': '❌ Entry not found.'}


def batch_update_json_entries(params):
    """Update multiple entries - expects updates as a list with entry_key and direct field updates"""
    params = flatten_params(params)
    # Don't validate flat params here because updates can contain nested structures
    
    filename = os.path.basename(params['filename'])
    updates = params['updates']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    updated_count = 0
    for update in updates:
        entry_key = update.get('entry_key')
        if not entry_key:
            continue
            
        if entry_key in data.get('entries', {}):
            # Apply all fields from update except entry_key
            update_fields = {k: v for k, v in update.items() if k != 'entry_key'}
            data['entries'][entry_key].update(update_fields)
            updated_count += 1
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    return {'status': 'success', 'message': f'✅ Updated {updated_count} entries.'}


def update_json_entry(params):
    """Update a single entry - all fields except filename and entry_key become the update data"""
    params = flatten_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if entry_key not in data.get('entries', {}):
        return {'status': 'error', 'message': '❌ Entry not found.'}
    
    # Extract update fields (everything except filename and entry_key)
    update_fields = {k: v for k, v in params.items() if k not in ['filename', 'entry_key']}
    
    if not update_fields:
        return {'status': 'error', 'message': '❌ No update fields provided.'}
    
    # Apply updates
    data['entries'][entry_key].update(update_fields)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    return {'status': 'success', 'message': f"✅ Entry '{entry_key}' updated with {len(update_fields)} fields."}


def read_json_entry(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entry = data.get('entries', {}).get(entry_key)
    if entry is None:
        return {'status': 'error', 'message': f"❌ Entry '{entry_key}' not found."}
    
    return {'status': 'success', 'entry': entry}


def add_json_entry(params):
    """Add entry - all fields except filename and entry_key become the entry data"""
    params = flatten_params(params)
    
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    data.setdefault('entries', {})
    
    # Extract entry data (everything except filename and entry_key)
    entry_data = {k: v for k, v in params.items() if k not in ['filename', 'entry_key']}
    
    if not entry_data:
        return {'status': 'error', 'message': '❌ No entry data provided.'}
    
    data['entries'][str(entry_key)] = entry_data
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    return {'status': 'success', 'message': f"✅ Entry '{entry_key}' added with {len(entry_data)} fields."}


def read_json_file(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return {'status': 'success', 'entries': data.get('entries', {})}


def create_json_file(params):
    params = flatten_params(params)
    validate_flat_params(params)
    
    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'entries': {}}, f, indent=4)
    
    return {'status': 'success', 'message': '✅ File initialized.'}


def log_thread_event(params):
    import time
    params = flatten_params(params)
    
    filename = "thread_log.json"
    key = params.get("entry_key")
    context_goal = params.get("context_goal")
    recovery_signals = params.get("recovery_signals")
    next_steps = params.get("next_steps")
    status = params.get("status")

    if not all([key, context_goal, recovery_signals, next_steps, status]):
        return {"status": "error", "message": "Missing required fields: entry_key, context_goal, recovery_signals, next_steps, status"}

    if not isinstance(recovery_signals, list) or not isinstance(next_steps, list):
        return {"status": "error", "message": "recovery_signals and next_steps must be lists."}

    # Use the flat structure for add_json_entry
    return add_json_entry({
        "filename": filename,
        "entry_key": key,
        "context_goal": context_goal,
        "recovery_signals": recovery_signals,
        "next_steps": next_steps,
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "author": "Jarvis 3.0"
    })


def read_large_json_file_chunked(params):
    """Read large JSON file in chunks to avoid response size errors"""
    params = flatten_params(params)
    validate_flat_params(params)

    filename = params.get("filename")
    chunk_size = params.get("chunk_size", 100)
    chunk_index = params.get("chunk_index", 0)

    if not filename:
        return {"status": "error", "message": "Missing filename parameter"}

    try:
        data_dir = os.path.join(os.getcwd(), "data")
        file_path = os.path.join(data_dir, filename)

        if not os.path.exists(file_path):
            return {"status": "error", "message": f"File '{filename}' not found"}

        with open(file_path, "r") as f:
            data = json.load(f)

        if isinstance(data, dict) and "entries" in data:
            data = list(data["entries"].values())

        total_entries = len(data)
        start_idx = chunk_index * chunk_size
        end_idx = min(start_idx + chunk_size, total_entries)

        chunk_data = data[start_idx:end_idx]

        return {
            "status": "success",
            "data": chunk_data,
            "chunk_info": {
                "chunk_index": chunk_index,
                "chunk_size": chunk_size,
                "total_entries": total_entries,
                "entries_in_chunk": len(chunk_data),
                "total_chunks": (total_entries + chunk_size - 1) // chunk_size,
                "has_more_chunks": end_idx < total_entries
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def batch_add_json_entries(params):
    """Add multiple entries with individual data for each entry"""
    params = flatten_params(params)
    # Don't validate flat params here because entries can contain nested structures
    
    filename = os.path.basename(params['filename'])
    entries = params['entries']  # List of entry objects with entry_key + fields
    filepath = os.path.join(os.getcwd(), 'data', filename)
    
    if not os.path.exists(filepath):
        return {"status": "error", "message": "❌ File not found."}
    
    if not isinstance(entries, list):
        return {"status": "error", "message": "❌ 'entries' must be a list of entry objects."}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    data.setdefault('entries', {})
    added_count = 0
    skipped_count = 0
    
    for entry in entries:
        if not isinstance(entry, dict):
            continue
            
        entry_key = entry.get('entry_key')
        if not entry_key:
            continue
        
        # Skip if entry already exists
        if entry_key in data['entries']:
            skipped_count += 1
            continue
        
        # Extract entry data (everything except entry_key)
        entry_data = {k: v for k, v in entry.items() if k != 'entry_key'}
        
        if entry_data:  # Only add if there's actual data
            data['entries'][str(entry_key)] = entry_data
            added_count += 1
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    message = f"✅ Added {added_count} entries"
    if skipped_count > 0:
        message += f", skipped {skipped_count} existing entries"
    
    return {"status": "success", "message": message}


def log_task_entry(params):
    """
    Creates a new task entry in orchestrate_brain.json with enforced schema fields.
    Required: entry_key, title, description, related_area
    Optional: estimated_time_min, priority, due, status
    Defaults: type='task', status='todo', priority='TBD', due='TBD', estimated_time_min=30
    """
    params = flatten_params(params)
    
    filename = "orchestrate_brain.json"
    entry_key = str(params.get("entry_key"))
    
    # Validate required fields
    required_fields = ["title", "description", "related_area"]
    missing = [field for field in required_fields if field not in params]
    
    if not entry_key:
        return {"status": "error", "message": "Missing entry_key"}
    if missing:
        return {"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}
    
    # Build entry with defaults
    entry = {
        "type": "task",
        "title": params["title"],
        "description": params["description"],
        "priority": params.get("priority", "TBD"),
        "related_area": params["related_area"],
        "status": params.get("status", "todo"),
        "due": params.get("due", "TBD"),
        "estimated_time_min": params.get("estimated_time_min", 30)  # NEW: Default to 30 minutes
    }
    
    # Read or create file
    filepath = os.path.join(os.getcwd(), 'data', filename)
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"entries": {}}
    
    if "entries" not in data:
        data["entries"] = {}
    
    # Add entry
    data["entries"][entry_key] = entry
    
    # Write back
    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    return {"status": "success", "message": f"✅ Task '{entry_key}' logged successfully"}


def log_resource_entry(params):
    """
    Logs a new resource entry in orchestrate_brain.json.
    Required: title, description
    Defaults: type='resource'
    REMOVED: related_asset field (no longer makes sense)
    """
    params = flatten_params(params)

    filename = "orchestrate_brain.json"
    entry_key = str(params.get("entry_key"))

    required_fields = ["title", "description"]  # REMOVED related_asset
    missing = [field for field in required_fields if field not in params]

    if not entry_key:
        return {"status": "error", "message": "Missing entry_key"}
    if missing:
        return {"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}

    # Build entry (no related_asset)
    entry = {
        "type": "resource",
        "title": params["title"],
        "description": params["description"]
    }

    filepath = os.path.join(os.getcwd(), 'data', filename)
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"entries": {}}

    data.setdefault("entries", {})
    data["entries"][entry_key] = entry

    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": f"✅ Resource '{entry_key}' logged successfully"}


def log_project_entry(params):
    """
    Logs a new project entry in orchestrate_brain.json.
    Required: title, description
    Defaults: type='project', status='TBD'
    """
    params = flatten_params(params)

    filename = "orchestrate_brain.json"
    entry_key = str(params.get("entry_key"))

    required_fields = ["title", "description"]
    missing = [field for field in required_fields if field not in params]

    if not entry_key:
        return {"status": "error", "message": "Missing entry_key"}
    if missing:
        return {"status": "error", "message": f"Missing required fields: {', '.join(missing)}"}

    entry = {
        "type": "project",
        "title": params["title"],
        "description": params["description"],
        "status": params.get("status", "TBD")
    }

    filepath = os.path.join(os.getcwd(), 'data', filename)
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"entries": {}}

    data.setdefault("entries", {})
    data["entries"][entry_key] = entry

    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": f"✅ Project '{entry_key}' logged successfully"}


def add_intent_route_entry(params):
    """Add a new intent route entry to intent_routes.json

    Required params:
    - intent: The intent trigger phrase
    - tool: The tool_name to route to
    - action: The action to call
    - description: Description of what this route does

    Optional:
    - icon: Emoji icon for display
    - params: Default params for the tool action
    """
    params = flatten_params(params)

    intent = params.get('intent')
    tool = params.get('tool')
    action = params.get('action')
    description = params.get('description')

    if not all([intent, tool, action, description]):
        return {'status': 'error', 'message': 'Missing required fields: intent, tool, action, description'}

    filename = 'intent_routes.json'
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        data = {'entries': {}}
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

    if 'entries' not in data:
        data = {'entries': data}  # Wrap existing data

    # Generate entry key from intent
    entry_key = intent.lower().replace(' ', '_').replace('{', '').replace('}', '')

    # Check if entry already exists
    if entry_key in data['entries']:
        return {'status': 'error', 'message': f'Entry for intent "{intent}" already exists'}

    # Build entry
    entry = {
        'icon': params.get('icon', '⚙️'),
        'intent': intent,
        'description': description,
        'tool_name': tool,
        'action': action
    }

    # Add optional params if provided
    if 'params' in params:
        entry['params'] = params['params']

    data['entries'][entry_key] = entry

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    return {
        'status': 'success',
        'message': f'✅ Intent route "{intent}" added successfully',
        'entry_key': entry_key
    }


def sort_json_entries(params):
    """Sort top-level entries in a JSON file by a specified key

    Required params:
    - filename: The JSON file to sort
    - sort_key: The field name to sort by

    Optional:
    - reverse: Sort in descending order (default: False)
    """
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    sort_key = params['sort_key']
    reverse = params.get('reverse', False)

    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': f'❌ File "{filename}" not found'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if 'entries' not in data:
        return {'status': 'error', 'message': '❌ File does not have an "entries" structure'}

    entries = data['entries']

    # Sort entries by the specified key
    try:
        sorted_entries = dict(sorted(
            entries.items(),
            key=lambda item: item[1].get(sort_key, ''),
            reverse=reverse
        ))
    except Exception as e:
        return {'status': 'error', 'message': f'❌ Failed to sort by "{sort_key}": {str(e)}'}

    # Replace entries with sorted version
    data['entries'] = sorted_entries

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    sort_order = 'descending' if reverse else 'ascending'

    return {
        'status': 'success',
        'message': f'✅ Sorted {len(sorted_entries)} entries by "{sort_key}" ({sort_order})',
        'entry_count': len(sorted_entries)
    }


def log_content_entry(params):
    """Log a new content entry in orchestrate_brain.json

    Required params:
    - title: Title of the content piece
    - description: Description/summary of the content

    Optional:
    - status: Status of the content (default: 'idea')
    - related_area: Related area like 'blog', 'podcast', 'social' (default: 'content')
    - tags: List of tags (default: [])
    - doc_id: Optional Outline doc ID if content is already in Outline
    """
    import time
    import uuid

    params = flatten_params(params)

    title = params.get('title')
    description = params.get('description')

    if not all([title, description]):
        return {'status': 'error', 'message': 'Missing required fields: title, description'}

    filename = 'orchestrate_brain.json'
    filepath = os.path.join(os.getcwd(), 'data', filename)

    # Read or create file
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {'entries': {}}

    if 'entries' not in data:
        data['entries'] = {}

    # Generate entry key
    entry_key = f"content_{int(time.time())}_{str(uuid.uuid4())[:8]}"

    # Build entry
    entry = {
        'type': 'content',
        'title': title,
        'description': description,
        'status': params.get('status', 'idea'),
        'related_area': params.get('related_area', 'content'),
        'tags': params.get('tags', []),
        'created_at': time.strftime('%Y-%m-%d')
    }

    # Add optional doc_id if provided
    if 'doc_id' in params:
        entry['doc_id'] = params['doc_id']

    # Add entry
    data['entries'][entry_key] = entry

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    return {
        'status': 'success',
        'message': f'✅ Content entry "{title}" logged successfully',
        'entry_key': entry_key
    }


def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()

    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as e:
        result = {'status': 'error', 'message': f'Invalid JSON in params: {e}'}
        print(json.dumps(result, indent=2))
        return

    if args.action == 'add_json_entry':
        result = add_json_entry(params)
    elif args.action == 'read_json_file':
        result = read_json_file(params)
    elif args.action == 'delete_json_entry':
        result = delete_json_entry(params)
    elif args.action == 'create_json_file':
        result = create_json_file(params)
    elif args.action == 'update_json_entry':
        result = update_json_entry(params)
    elif args.action == 'batch_update_json_entries':
        result = batch_update_json_entries(params)
    elif args.action == 'batch_delete_json_entries':
        result = batch_delete_json_entries(params)
    elif args.action == 'insert_json_entry_from_template':
        result = insert_json_entry_from_template(params)
    elif args.action == 'create_json_file_from_template':
        result = create_json_file_from_template(params)
    elif args.action == 'add_field_to_json_entry':
        result = add_field_to_json_entry(params)
    elif args.action == 'batch_add_field_to_json_entries':
        result = batch_add_field_to_json_entries(params)
    elif args.action == 'read_json_entry':
        result = read_json_entry(params)
    elif args.action == 'search_json_entries':
        result = search_json_entries(params)
    elif args.action == 'search_json_entries_chunked':
        result = search_json_entries_chunked(params)
    elif args.action == 'list_json_entries':
        result = list_json_entries(params)
    elif args.action == 'list_json_entries_chunked':
        result = list_json_entries_chunked(params)
    elif args.action == 'read_large_json_file_chunked':
        result = read_large_json_file_chunked(params)
    elif args.action == 'log_thread_event':
        result = log_thread_event(params)
    elif args.action == 'batch_add_json_entries':
        result = batch_add_json_entries(params)
    elif args.action == 'log_task_entry':
        result = log_task_entry(params)
    elif args.action == 'log_resource_entry':
        result = log_resource_entry(params)
    elif args.action == 'log_project_entry':
        result = log_project_entry(params)
    elif args.action == 'add_intent_route_entry':
        result = add_intent_route_entry(params)
    elif args.action == 'sort_json_entries':
        result = sort_json_entries(params)
    elif args.action == 'log_content_entry':
        result = log_content_entry(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()