import os
import json
import argparse
import sys

# ---------- Utility ----------

def resolve_path(filename):
    for base in ['data', 'demo', 'templates']:
        path = os.path.join(os.getcwd(), base, filename)
        if os.path.exists(path):
            return path
    return None


# ---------- Core Actions ----------

def create_json_file(params):
    filename = os.path.basename(params['filename'])
    data_dir = os.path.join(os.getcwd(), 'data')
    filepath = os.path.join(data_dir, filename)
    os.makedirs(data_dir, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'entries': {}}, f, indent=4)
    return {'status': 'success', 'message': '✅ File initialized.'}


def add_json_entry(params):
    import datetime
    import os
    import json

    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    entry_data = params['entry_data']
    filepath = resolve_path(filename)

    # Auto-create the file if it doesn't exist
    if not filepath:
        filepath = resolve_path(filename, create=True)  # assuming resolve_path can handle creation
        if not filepath:  # Fallback manual creation if resolve_path doesn't support create=True
            filepath = os.path.join("data", filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({"entries": {}}, f, indent=4)

    # Add timestamp for specific files
    timestamp_files = {"thread_log.json", "second_wave_notes.json", "srini_notes.json"}
    if filename in timestamp_files and "created_at" not in entry_data:
        entry_data["created_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    # Load existing data
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {"entries": {}}

    data.setdefault('entries', {})
    data['entries'][str(entry_key)] = entry_data

    # Save updated file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    return {'status': 'success', 'message': f"✅ Entry '{entry_key}' added."}




def update_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    new_data = params['new_data']
    filepath = resolve_path(filename)
    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if entry_key in data.get('entries', {}):
        data['entries'][entry_key].update(new_data)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message': f"✅ Entry '{entry_key}' updated."}
    return {'status': 'error', 'message': '❌ Entry not found.'}


def batch_add_json_entries(params):
    import os
    import json

    filename = os.path.basename(params['filename'])
    entries = params['entries']
    filepath = resolve_path(filename)

    # Auto-create the file if it doesn't exist
    if not filepath:
        filepath = os.path.join("data", filename)
        if not os.path.exists(os.path.dirname(filepath)):
            os.makedirs(os.path.dirname(filepath))
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({"entries": {}}, f, indent=4)

    # Load existing data (handle empty or bad JSON)
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {"entries": {}}

    data.setdefault('entries', {})
    added = 0
    for entry_key, entry_data in entries.items():
        data['entries'][entry_key] = entry_data
        added += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    return {'status': 'success', 'message': f'✅ {added} entries added.'}

def batch_update_json_entries(params):
    filename = os.path.basename(params['filename'])
    updates = params['updates']
    filepath = resolve_path(filename)
    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated_count = 0
    for entry_key, new_data in updates.items():
        if entry_key in data.get('entries', {}):
            data['entries'][entry_key].update(new_data)
            updated_count += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    return {'status': 'success', 'message': f'✅ Updated {updated_count} entries.'}


def add_field_to_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = resolve_path(filename)

    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if entry_key in data.get('entries', {}):
        data['entries'][entry_key][field_name] = field_value
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message': f"✅ Field '{field_name}' added to entry '{entry_key}'."}
    return {'status': 'error', 'message': '❌ Entry not found.'}


def batch_add_field_to_json_entries(params):
    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = resolve_path(filename)

    if not filepath:
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


def delete_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = resolve_path(filename)

    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if entry_key in data.get('entries', {}):
        del data['entries'][entry_key]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message': f"✅ Entry '{entry_key}' deleted."}
    return {'status': 'error', 'message': '❌ Entry not found.'}


def batch_delete_json_entries(params):
    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    filepath = resolve_path(filename)

    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    deleted = 0
    for key in entry_keys:
        if key in data.get('entries', {}):
            del data['entries'][key]
            deleted += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    return {'status': 'success', 'message': f'✅ Deleted {deleted} entries.'}


def search_json_entries(params):
    filename = os.path.basename(params['filename'])
    search_key = params['search_key']
    search_value = str(params['search_value']).lower()
    filepath = resolve_path(filename)

    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    results = {}
    for key, entry in data.get('entries', {}).items():
        value = str(entry.get(search_key, '')).lower()
        if search_value in value:
            results[key] = entry

    return {'status': 'success', 'results': results}


def list_json_entries(params):
    filename = os.path.basename(params['filename'])
    filepath = resolve_path(filename)
    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return {'status': 'success', 'entries': data.get('entries', {})}


def read_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = resolve_path(filename)
    if not filepath:
        return {'status': 'error', 'message': '❌ File not found.'}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entry = data.get('entries', {}).get(entry_key)
    if entry is None:
        return {'status': 'error', 'message': f"❌ Entry '{entry_key}' not found."}
    return {'status': 'success', 'entry': entry}


def read_json_file(params):
    filename = os.path.basename(params['filename'])
    filepath = resolve_path(filename)

    if not filepath:
        return {
            'status': 'error',
            'message': f"❌ File '{filename}' not found in [data, demo, templates]."
        }

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            'status': 'success',
            'data': data
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f"❌ Failed to read '{filename}': {str(e)}"
        }




# ---------- Action Router ----------

def main():
    parser = argparse.ArgumentParser(description='Orchestrate JSON Manager')
    parser.add_argument('action', help='Action to perform')
    parser.add_argument('--params', type=str, required=False, help='JSON-encoded parameters')
    args = parser.parse_args()

    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError:
        print(json.dumps({'status': 'error', 'message': '❌ Invalid JSON format.'}, indent=4))
        return

    try:
        func = getattr(sys.modules[__name__], args.action)
        result = func(params)
    except AttributeError:
        result = {'status': 'error', 'message': f'❌ Unknown action: {args.action}'}

    print(json.dumps(result, indent=4))


if __name__ == '__main__':
    main()
