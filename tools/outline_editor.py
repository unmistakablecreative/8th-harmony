import json
import requests
import re
import os


def _update_working_context(result):
    """
    Helper function to append newly created docs to working_context.json
    Wrapped in try/except for safety - failures won't break doc creation
    """
    try:
        # Only proceed if result has the expected structure
        if not isinstance(result, dict) or 'data' not in result:
            return

        data = result['data']
        if not isinstance(data, dict) or 'id' not in data:
            return

        doc_id = data.get('id')
        title = data.get('title', 'Untitled')
        collection_id = data.get('collectionId')

        # Load working context
        context_file = os.path.join(os.getcwd(), 'data/working_context.json')
        if not os.path.exists(context_file):
            return

        with open(context_file, 'r', encoding='utf-8') as f:
            context = json.load(f)

        # Find the collection name from ID
        collection_name = None
        for name, info in context.get('collections', {}).items():
            if info.get('id') == collection_id:
                collection_name = name
                break

        if not collection_name:
            return

        # Append doc to collection's docs list
        if 'docs' not in context['collections'][collection_name]:
            context['collections'][collection_name]['docs'] = []

        # Check if doc already exists
        existing = [d for d in context['collections'][collection_name]['docs'] if d.get('id') == doc_id]
        if not existing:
            context['collections'][collection_name]['docs'].append({
                'id': doc_id,
                'title': title
            })

        # Save back
        with open(context_file, 'w', encoding='utf-8') as f:
            json.dump(context, f, indent=2)

    except Exception:
        # Silently continue if context update fails - don't break doc creation
        pass


def _create_share_link(doc_id):
    """
    Helper function to create a public share link for a document
    Returns the share URL or None if creation fails
    """
    try:
        from system_settings import load_credential
        api_base = 'https://app.getoutline.com/api'
        token = load_credential('outline_api_key')

        if not token:
            return None

        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # Create share link via Outline API
        payload = {'documentId': doc_id}
        res = requests.post(f'{api_base}/shares.create', json=payload, headers=headers, verify=False)
        res.raise_for_status()
        result = res.json()

        # Extract share URL from response
        if 'data' in result and 'url' in result['data']:
            return result['data']['url']

        return None
    except Exception:
        # If share creation fails, don't break doc creation
        return None


def _resolve_collection_id(content_or_hashtag):
    """Unified function to resolve collection ID from hashtag or content"""
    COLLECTIONS = {
        "Projects": "80d43828-f9fc-4dc6-ba1f-4031e863cc71",
        "Areas": "13768b39-2cc7-4fcc-9444-43a89bed38e9",
        "Resources": "c3bb9da4-8cad-4bed-8429-f9d1ff1a3bf7",
        "Inbox": "d5e76f6d-a87f-44f4-8897-ca15f98fa01a",
        "Content": "c8b717d5-b223-4e3b-9bee-3c669b6b5423",
        "Roles": "789dcb2d-ed1c-4456-aeda-102d5692197e",
        "Maples": "b25fa087-cd9c-848f-8812-7848592a8612"
    }

    # Default to Inbox
    collection_id = COLLECTIONS["Inbox"]

    # If it's already a collection ID, return it
    if content_or_hashtag in COLLECTIONS.values():
        return content_or_hashtag, content_or_hashtag

    # If it's a collection name, return the ID
    if content_or_hashtag in COLLECTIONS:
        return COLLECTIONS[content_or_hashtag], content_or_hashtag

    # Look for hashtag pattern in content
    tag_pattern = r'#(\w+)'
    match = re.search(tag_pattern, str(content_or_hashtag))

    if match:
        collection_name = match.group(1)
        if collection_name in COLLECTIONS:
            collection_id = COLLECTIONS[collection_name]

    return collection_id, str(content_or_hashtag)


def create_doc(params):
    title = params.get('title')
    content_file = params.get('content_file')  # Optional: read content from file
    content = params.get('content') or params.get('text')
    parent_doc_id = params.get('parent_doc_id')  # Optional parent document ID

    # If content_file is provided, read from file
    if content_file:
        if os.path.exists(content_file):
            with open(content_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            return {'status': 'error', 'message': f'❌ Content file not found: {content_file}'}

    collection_id, cleaned_content = _resolve_collection_id(content)

    # Remove hashtag from content if it was used for collection resolution
    if content != cleaned_content:
        tag_pattern = r'#(\w+)'
        cleaned_content = re.sub(tag_pattern, '', cleaned_content).strip()
    else:
        cleaned_content = content

    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')

    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    payload = {
        'title': title,
        'text': cleaned_content,
        'collectionId': collection_id,
        'publish': True
    }

    # Add parent_doc_id if provided to create as child document
    if parent_doc_id:
        payload['parentDocumentId'] = parent_doc_id

    res = requests.post(f'{api_base}/documents.create', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    result = res.json()

    # Update working context with new doc
    _update_working_context(result)

    # Create share link and add to result
    if 'data' in result and 'id' in result['data']:
        doc_id = result['data']['id']
        share_url = _create_share_link(doc_id)
        if share_url:
            result['data']['share_url'] = share_url

    return result


def create_child_doc(params):
    """Create a child document under a specific parent document using hashtag logic"""
    title = params.get('title')
    content = params.get('content') or params.get('text')
    parent_doc_id = params.get('parent_doc_id')

    if not parent_doc_id:
        return {'status': 'error', 'message': '❌ parent_doc_id is required for creating child documents'}

    collection_id, cleaned_content = _resolve_collection_id(content)

    # Remove hashtag from content if it was used for collection resolution
    if content != cleaned_content:
        tag_pattern = r'#(\w+)'
        cleaned_content = re.sub(tag_pattern, '', cleaned_content).strip()
    else:
        cleaned_content = content

    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')

    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    payload = {
        'title': title,
        'text': cleaned_content,
        'collectionId': collection_id,
        'parentDocumentId': parent_doc_id,
        'publish': True
    }

    res = requests.post(f'{api_base}/documents.create', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    result = res.json()

    # Update working context with new doc
    _update_working_context(result)

    # Create share link and add to result
    if 'data' in result and 'id' in result['data']:
        doc_id = result['data']['id']
        share_url = _create_share_link(doc_id)
        if share_url:
            result['data']['share_url'] = share_url

    return result


def get_doc(doc_id):
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    res = requests.post(f'{api_base}/documents.info', json={'id': doc_id}, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def _load_queue():
    """Load outline_queue.json, create if doesn't exist"""
    queue_file = 'data/outline_queue.json'
    if not os.path.exists(queue_file):
        return {}
    with open(queue_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_queue(queue_data):
    """Save outline_queue.json"""
    queue_file = 'data/outline_queue.json'
    with open(queue_file, 'w', encoding='utf-8') as f:
        json.dump(queue_data, f, indent=2)


def _scan_queue_dir():
    """
    Scan outline_docs_queue/ for new markdown files
    Add any new files to outline_queue.json with status 'pending'
    """
    queue_dir = 'outline_docs_queue'
    if not os.path.exists(queue_dir):
        os.makedirs(queue_dir)
        return

    queue_data = _load_queue()

    # Find all .md files
    md_files = [f for f in os.listdir(queue_dir) if f.endswith('.md')]

    for md_file in md_files:
        entry_key = md_file.replace('.md', '')

        # Skip if already in queue
        if entry_key in queue_data:
            continue

        # Read markdown to extract title
        file_path = os.path.join(queue_dir, md_file)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract title from first H1
        title = entry_key.replace('-', ' ').replace('_', ' ').title()  # Fallback
        lines = content.split('\n')
        for line in lines:
            if line.startswith('# '):
                title = line.replace('# ', '').strip()
                break

        # Add to queue
        queue_data[entry_key] = {
            'title': title,
            'file_path': file_path,
            'status': 'pending',
            'doc_id': None
        }

    _save_queue(queue_data)
    return queue_data


def create_doc_from_queue(params):
    """
    Process a single document from queue by entry_key.
    Reads markdown file, creates doc in Outline, marks as completed.

    Supports update routing: if entry_key starts with 'update-', calls update_doc instead.

    Params:
        entry_key: The key in outline_queue.json

    Returns:
        Outline API response + queue status
    """
    entry_key = params.get('entry_key')
    if not entry_key:
        return {'status': 'error', 'message': '❌ Missing entry_key parameter'}

    # Scan for new files first
    _scan_queue_dir()

    # Load queue
    queue_data = _load_queue()

    if entry_key not in queue_data:
        return {'status': 'error', 'message': f'❌ Entry key not found in queue: {entry_key}'}

    entry = queue_data[entry_key]
    file_path = entry['file_path']

    # Check if file still exists
    if not os.path.exists(file_path):
        return {'status': 'error', 'message': f'❌ Markdown file not found: {file_path}'}

    # Read markdown content
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Route based on prefix
    is_update = entry_key.startswith('update-')

    if is_update:
        # UPDATE: Look up existing doc_id
        # Strip prefix to find original entry
        original_key = entry_key.replace('update-', '', 1)

        # Try to find doc_id from previous queue entry
        doc_id = None
        if original_key in queue_data:
            doc_id = queue_data[original_key].get('doc_id')

        if not doc_id:
            return {'status': 'error', 'message': f'❌ Cannot find doc_id for update. Original entry "{original_key}" not found in queue.'}

        # Call update_doc
        result = update_doc({
            'doc_id': doc_id,
            'title': entry['title'],
            'text': content
        })
    else:
        # CREATE: Call create_doc
        result = create_doc({
            'title': entry['title'],
            'content': content
        })

    # If successful, update queue status
    if result.get('data') and result.get('data', {}).get('id'):
        doc_id = result['data']['id']
        queue_data[entry_key]['status'] = 'completed'
        queue_data[entry_key]['doc_id'] = doc_id
        _save_queue(queue_data)

        result['queue_status'] = 'completed'
        result['message'] = f"✅ Document {'updated' if is_update else 'created'}: {entry['title']}"

    return result


def process_queue(params=None):
    """
    Process ALL pending entries in outline_queue.json.
    Scans directory first, then processes each pending entry.

    Returns:
        Summary of processed docs
    """
    # Scan for new files
    _scan_queue_dir()

    # Load queue
    queue_data = _load_queue()

    # Filter pending entries
    pending = {k: v for k, v in queue_data.items() if v.get('status') == 'pending'}

    if not pending:
        return {'status': 'success', 'message': '✅ No pending documents in queue', 'processed': 0}

    results = []
    for entry_key in pending.keys():
        result = create_doc_from_queue({'entry_key': entry_key})
        results.append({
            'entry_key': entry_key,
            'success': result.get('status') != 'error',
            'doc_id': result.get('data', {}).get('id'),
            'message': result.get('message')
        })

    successes = [r for r in results if r['success']]
    failures = [r for r in results if not r['success']]

    return {
        'status': 'success',
        'processed': len(results),
        'successes': len(successes),
        'failures': len(failures),
        'results': results
    }


def update_doc(params):
    doc_id = params.get('doc_id')
    title = params.get('title')
    text = params.get('text') or params.get('content')
    append = params.get('append', False)
    publish = params.get('publish', True)
    
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    if append:
        text = '\n\n' + text.strip()

    payload = {
        'id': doc_id,
        'title': title,
        'text': text,
        'publish': publish
    }
    if append:
        payload['append'] = True

    res = requests.post(f'{api_base}/documents.update', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def delete_doc(doc_id):
    """Archives a document instead of permanently deleting it."""
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    # Use archive endpoint instead of delete - archives can be restored
    res = requests.post(f'{api_base}/documents.archive', json={'id': doc_id}, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def list_docs(params):
    limit = params.get('limit', 25)
    offset = params.get('offset', 0)
    sort = params.get('sort', 'updatedAt')
    direction = params.get('direction', 'DESC')
    collection = params.get('collection')
    
    collection_id = None
    if collection:
        collection_id, _ = _resolve_collection_id(collection)
    
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'limit': limit, 'offset': offset, 'sort': sort, 'direction': direction}
    if collection_id:
        payload['collectionId'] = collection_id
    res = requests.post(f'{api_base}/documents.list', headers=headers, json=payload, verify=False)
    res.raise_for_status()
    return res.json()


def search_docs(params):
    query = params.get('query')
    limit = params.get('limit', 10)
    offset = params.get('offset', 0)
    
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'query': query, 'limit': limit, 'offset': offset}

    res = requests.post(f'{api_base}/documents.search', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def export_doc(params):
    doc_id = params.get('doc_id')
    filename = params.get('filename')
    import os
    from system_settings import load_credential
    
    if not filename:
        doc = get_doc(doc_id)
        title = doc.get('title', f'doc_{doc_id}')
        filename = f"{title.replace(' ', '_').lower()}.md"
        
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
        
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'id': doc_id, 'exportType': 'markdown'}
    
    res = requests.post(f'{api_base}/documents.export', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    
    try:
        raw = json.loads(res.text)
        markdown = raw.get('data', '')
    except json.JSONDecodeError:
        markdown = res.text
        
    output_dir = os.path.join('/orchestrate_user/orchestrate_exports', 'markdown')
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown)
        
    return {'status': 'success', 'message': f'✅ Exported to {filepath}'}


def import_doc_from_file(params):
    file_path = params.get('file_path')
    collection = params.get('collection', 'Inbox')
    parent_document_id = params.get('parentDocumentId')
    template = params.get('template', False)
    publish = params.get('publish', True)
    
    collection_id, _ = _resolve_collection_id(collection)
    
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}'}
    files = {'file': open(file_path, 'rb')}
    data = {'collectionId': collection_id, 
            'parentDocumentId': parent_document_id or '', 
            'template': str(template).lower(),
            'publish': str(publish).lower()}
    res = requests.post(f'{api_base}/documents.import', headers=headers, files=files, data=data, verify=False)
    res.raise_for_status()
    return res.json()


def move_doc(params):
    doc_id = params.get('doc_id')
    collection = params.get('collection')
    parent_document_id = params.get('parentDocumentId')
    
    if not collection:
        return {'status': 'error', 'message': '❌ collection is required (use hashtag like #Projects or name like Projects)'}
    
    collection_id, _ = _resolve_collection_id(collection)
    
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'id': doc_id, 'collectionId': collection_id}
    if parent_document_id:
        payload['parentDocumentId'] = parent_document_id
    
    res = requests.post(f'{api_base}/documents.move', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def get_url(doc_id):
    return {'status': 'success', 'url': f'https://getoutline.com/doc/{doc_id}'}


def create_share_link(params):
    """
    Creates a public share link for an existing document.
    Params:
        doc_id (str): The document ID to create a share link for
    Returns:
        dict with status, share_url
    """
    doc_id = params.get('doc_id')
    if not doc_id:
        return {'status': 'error', 'message': '❌ Missing required parameter: doc_id'}

    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')

    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    try:
        # Create share link via Outline API
        payload = {'documentId': doc_id}
        res = requests.post(f'{api_base}/shares.create', json=payload, headers=headers, verify=False)
        res.raise_for_status()
        result = res.json()

        # Extract share URL from response
        if 'data' in result and 'url' in result['data']:
            return {
                'status': 'success',
                'share_url': result['data']['url'],
                'doc_id': doc_id,
                'message': f'✅ Share link created: {result["data"]["url"]}'
            }
        else:
            return {'status': 'error', 'message': '❌ Share link creation failed - no URL in response'}

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            # Share link might already exist
            return {'status': 'error', 'message': f'❌ Share link may already exist for doc {doc_id}'}
        return {'status': 'error', 'message': f'❌ HTTP error: {str(e)}'}
    except Exception as e:
        return {'status': 'error', 'message': f'❌ Failed to create share link: {str(e)}'}


def create_collection(params):
    name = params.get('name')
    description = params.get('description', '')
    permission = params.get('permission', 'read_write')
    icon = params.get('icon', 'collection')
    color = params.get('color', '#4E5C6E')
    sharing = params.get('sharing', False)
    
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'name': name, 'description': description, 'permission': permission, 'icon': icon, 'color': color, 'sharing': sharing}
    res = requests.post(f'{api_base}/collections.create', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def get_collection(collection_id):
    # Support hashtag resolution
    resolved_id, _ = _resolve_collection_id(collection_id)

    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'id': resolved_id}
    res = requests.post(f'{api_base}/collections.info', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def update_collection(params):
    collection_id = params.get('collection_id')
    name = params.get('name')
    description = params.get('description')
    permission = params.get('permission')
    icon = params.get('icon')
    color = params.get('color')
    sharing = params.get('sharing')

    # Support hashtag resolution
    resolved_id, _ = _resolve_collection_id(collection_id)

    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'id': resolved_id}
    if name: payload['name'] = name
    if description: payload['description'] = description
    if permission: payload['permission'] = permission
    if icon: payload['icon'] = icon
    if color: payload['color'] = color
    if sharing is not None: payload['sharing'] = sharing
    res = requests.post(f'{api_base}/collections.update', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def delete_collection(collection_id):
    # Support hashtag resolution
    resolved_id, _ = _resolve_collection_id(collection_id)

    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {'id': resolved_id}
    res = requests.post(f'{api_base}/collections.delete', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def ask_outline_ai(params):
    query = params.get('query')
    
    from system_settings import load_credential

    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    url = "https://app.getoutline.com/api/documents.answerQuestion"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"query": query}

    res = requests.post(url, headers=headers, json=payload, verify=False)
    if res.status_code != 200:
        return {'status': 'error', 'message': res.text}

    return {'status': 'success', 'data': res.json()}


def get_nested_doc(params):
    doc_id = params.get('doc_id')
    
    from system_settings import load_credential

    token = load_credential("outline_api_key")
    if not token:
        return {"status": "error", "message": "Missing Outline API key."}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    api_base = "https://app.getoutline.com/api"

    res = requests.post(f"{api_base}/documents.info", headers=headers, json={"id": doc_id})
    res.raise_for_status()
    parent = res.json().get("data", {})

    children_res = requests.post(f"{api_base}/documents.list", headers=headers, json={"parentDocumentId": doc_id})
    children_res.raise_for_status()
    children = children_res.json().get("data", [])

    return {"status": "success", "parent": parent, "children": children, "child_count": len(children)}


def list_collection_docs(params):
    collection = params.get('collection')
    
    if not collection:
        return {"status": "error", "message": "❌ collection is required (use hashtag like #Projects or name like Projects)"}
    
    collection_id, _ = _resolve_collection_id(collection)
    
    from system_settings import load_credential

    api_base = "https://app.getoutline.com/api"
    token = load_credential("outline_api_key")
    if not token:
        return {"status": "error", "message": "Missing Outline API key."}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {"collectionId": collection_id, "limit": 100}
    res = requests.post(f"{api_base}/documents.list", headers=headers, json=payload, verify=False)
    if res.status_code != 200:
        return {"status": "error", "message": res.text}

    docs = res.json().get("data", [])
    return {"status": "success", "documents": [{"id": doc.get("id"), "title": doc.get("title")} for doc in docs]}


def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'create_doc':
        result = create_doc(params)
    elif args.action == 'create_child_doc':
        result = create_child_doc(params)
    elif args.action == 'get_doc':
        result = get_doc(**params)
    elif args.action == 'update_doc':
        result = update_doc(params)
    elif args.action == 'delete_doc':
        result = delete_doc(**params)
    elif args.action == 'list_docs':
        result = list_docs(params)
    elif args.action == 'search_docs':
        result = search_docs(params)
    elif args.action == 'get_url':
        result = get_url(**params)
    elif args.action == 'export_doc':
        result = export_doc(params)
    elif args.action == 'import_doc_from_file':
        result = import_doc_from_file(params)
    elif args.action == 'move_doc':
        result = move_doc(params)
    elif args.action == 'create_collection':
        result = create_collection(params)
    elif args.action == 'get_collection':
        result = get_collection(**params)
    elif args.action == 'update_collection':
        result = update_collection(params)
    elif args.action == 'delete_collection':
        result = delete_collection(**params)
    elif args.action == 'ask_outline_ai':
        result = ask_outline_ai(params)
    elif args.action == 'list_collection_docs':
        result = list_collection_docs(params)
    elif args.action == 'get_nested_doc':
        result = get_nested_doc(params)
    elif args.action == 'create_doc_from_queue':
        result = create_doc_from_queue(params)
    elif args.action == 'process_queue':
        result = process_queue(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()