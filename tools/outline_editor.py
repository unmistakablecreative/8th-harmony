import json
import requests
import re

def create_doc(params):
    title = params.get('title')
    content = params.get('content')
    collectionId = params.get('collectionId')
    parentDocumentId = params.get('parentDocumentId', None)

    # 🔁 Name-to-ID resolution
    COLLECTIONS = {
        "Projects": "80d43828-f9fc-4dc6-ba1f-4031e863cc71",
        "Areas": "13768b39-2cc7-4fcc-9444-43a89bed38e9",
        "Resources": "c3bb9da4-8cad-4bed-8429-f9d1ff1a3bf7",
        "Inbox": "d5e76f6d-a87f-44f4-8897-ca15f98fa01a",
        "Content": "c8b717d5-b223-4e3b-9bee-3c669b6b5423"  # ✅ Added archived Content collection
    }

    if collectionId in COLLECTIONS:
        collectionId = COLLECTIONS[collectionId]

    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    if not collectionId:
        collectionId = '6a798b00-6302-42eb-9bbf-b38bef766cd9'  # fallback if all else fails

    payload = {
        'title': title,
        'text': content,
        'collectionId': collectionId,
        'publish': True
    }

    if parentDocumentId:
        payload['parentDocumentId'] = parentDocumentId

    res = requests.post(f'{api_base}/documents.create', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def get_doc(params):
    from system_settings import load_credential
    import requests

    doc_id = params.get("doc_id")
    if not doc_id:
        return {"status": "error", "message": "❌ Missing 'doc_id' in params."}

    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {"status": "error", "message": "❌ Missing Outline API token in credentials.json"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = { "id": doc_id }
    res = requests.post(f"{api_base}/documents.info", json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def get_nested_doc(params):
    import re

    doc_id = params["doc_id"]
    parent = get_doc({"doc_id": doc_id})
    raw_text = parent["data"]["text"]
    title = parent["data"]["title"]

    # ⛏️ Extract all linked document IDs from mentions
    backlink_ids = re.findall(r'document/([a-f0-9\-]{36})', raw_text)
    valid_children = []
    broken_links = []
    all_text = raw_text.strip() + "\n\n"

    for sub_id in backlink_ids:
        try:
            sub_doc = get_doc({"doc_id": sub_id})
            sub_text = sub_doc["data"]["text"].strip()
            sub_title = sub_doc["data"]["title"]
            sub_updated = sub_doc["data"].get("updatedAt", None)

            valid_children.append({
                "doc_id": sub_id,
                "title": sub_title,
                "last_updated": sub_updated
            })

            all_text += sub_text + "\n\n"

        except Exception as e:
            broken_links.append({
                "doc_id": sub_id,
                "error": str(e)
            })

    return {
        "status": "success",
        "doc_id": doc_id,
        "title": title,
        "text": all_text.strip(),
        "sections": len(valid_children),
        "backlinks": [d["doc_id"] for d in valid_children],
        "child_docs": valid_children,
        "broken_links": broken_links
    }



def update_doc(params):
    doc_id = params.get('doc_id')
    title = params.get('title')
    text = params.get('text')
    append = params.get('append')
    publish = params.get('publish')
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message':
            '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type':
        'application/json'}
    if append:
        payload_append = True
        text = '\n\n' + text.strip()
    else:
        payload_append = False
    payload = {'id': doc_id, 'title': title, 'text': text, 'publish': publish}
    if payload_append:
        payload['append'] = True
    res = requests.post(f'{api_base}/documents.update', json=payload,
        headers=headers, verify=False)
    res.raise_for_status()
    return res.json()

def ask_outline_ai(query):
    import requests
    from system_settings import load_credential

    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    url = "https://app.getoutline.com/api/documents.answerQuestion"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {"query": query}

    res = requests.post(url, headers=headers, json=payload, verify=False)
    if res.status_code != 200:
        return {'status': 'error', 'message': res.text}

    return {'status': 'success', 'data': res.json()}



def export_doc(params):
    import requests, os, json
    from system_settings import load_credential
    doc_id = params.get('doc_id')
    filename = params.get('filename')
    if not filename:
        doc = get_doc(doc_id)
        title = doc.get('title', f'doc_{doc_id}')
        filename = f"{title.replace(' ', '_').lower()}.md"
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message':
            '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type':
        'application/json'}
    payload = {'id': doc_id, 'exportType': 'markdown'}
    res = requests.post(f'{api_base}/documents.export', json=payload,
        headers=headers, verify=False)
    res.raise_for_status()
    try:
        raw = json.loads(res.text)
        markdown = raw.get('data', '')
    except json.JSONDecodeError:
        markdown = res.text
    output_dir = (
        '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/blog_sections')
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown)
    return {'status': 'success', 'message': f'✅ Exported to {filepath}'}


def delete_doc(doc_id):
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message':
            '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type':
        'application/json'}
    res = requests.post(f'{api_base}/documents.delete', json={'id': doc_id},
        headers=headers, verify=False)
    res.raise_for_status()
    return res.json()



def list_docs(params):
    """
    Lists documents in Outline.

    Expected params:
        limit (int)          – Number of docs to fetch (default 10)
        offset (int)         – Starting offset (default 0)
        sort (str)           – Sort field (default "createdAt")
        direction (str)      – "ASC" or "DESC" (default "DESC")
        collectionId (str)   – Optional UUID of the collection
    """
    from system_settings import load_credential
    import requests

    limit = params.get("limit", 10)
    offset = params.get("offset", 0)
    sort = params.get("sort", "createdAt")
    direction = params.get("direction", "DESC")
    collectionId = params.get("collectionId")

    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {
            'status': 'error',
            'message': '❌ Missing Outline API token in credentials.json'
        }

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    payload = {
        'limit': limit,
        'offset': offset,
        'sort': sort,
        'direction': direction
    }
    if collectionId:
        payload['collectionId'] = collectionId

    res = requests.post(f'{api_base}/documents.list', headers=headers, json=payload, verify=False)
    res.raise_for_status()
    return res.json()


def search_docs(params):
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token in credentials.json'}

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    query = params.get('query')
    limit = params.get('limit', 5)
    offset = params.get('offset', 0)

    payload = {
        'query': query,
        'limit': limit,
        'offset': offset
    }

    res = requests.post(f'{api_base}/documents.search', json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()



def get_url(doc_id):
    return {'status': 'success', 'url': f'https://getoutline.com/doc/{doc_id}'}


def patch_section(doc_id, section, new_text):
    from time import sleep
    doc = get_doc(doc_id)
    if not doc or not doc.get('text'):
        return {'status': 'error', 'message': 'Original document fetch failed.'
            }
    text = doc['text']
    if section not in text:
        return {'status': 'error', 'message': 'Section not found in document.'}
    updated = text.replace(section, new_text)
    sleep(1)
    return update_doc(doc_id=doc_id, title=doc['title'], text=updated,
        append=False, publish=True)


def append_section(doc_id, new_text):
    doc = get_doc(doc_id)
    if not doc or not doc.get('text'):
        return {'status': 'error', 'message': 'Original document fetch failed.'
            }
    updated = doc['text'].rstrip() + '\n\n' + new_text.strip()
    return update_doc(doc_id=doc_id, title=doc['title'], text=updated,
        append=False, publish=True)


def import_doc_from_file(file_path, collectionId, parentDocumentId,
    template, publish):
    import os
    import requests
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message':
            '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}'}
    data = {'collectionId': collectionId, 'template': 'true' if template else
        'false', 'publish': 'true' if publish else 'false'}
    if parentDocumentId and isinstance(parentDocumentId, str) and len(
        parentDocumentId) >= 36:
        data['parentDocumentId'] = parentDocumentId
    try:
        filename = os.path.basename(file_path)
        with open(file_path, 'rb') as f:
            files = {'file': (filename, f, 'text/markdown')}
            res = requests.post(f'{api_base}/documents.import', headers=
                headers, data=data, files=files)
            res.raise_for_status()
            return res.json()
    except requests.exceptions.HTTPError:
        return {'status': 'error', 'message':
            f'HTTP {res.status_code}: {res.reason}', 'details': res.text}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def move_doc(params):
    """
    Moves a document to a new collection or under a new parent document.

    Expects params = {
        "doc_id": str,
        "collectionId": str,
        "parentDocumentId": Optional[str]
    }
    """
    import requests
    from system_settings import load_credential

    # Extract values from params dict
    doc_id = params.get("doc_id")
    collectionId = params.get("collectionId")
    parentDocumentId = params.get("parentDocumentId")

    # Load token
    token = load_credential("outline_api_key")
    if not token:
        return {
            "status": "error",
            "message": "❌ Missing Outline API token in credentials.json"
        }

    api_base = "https://app.getoutline.com/api"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Build payload
    payload = {
        "id": doc_id,
        "collectionId": collectionId
    }
    if parentDocumentId:
        payload["parentDocumentId"] = parentDocumentId

    # Perform the move request
    res = requests.post(f"{api_base}/documents.move", json=payload, headers=headers, verify=False)
    res.raise_for_status()

    return {
        "status": "success",
        "message": "✅ Document moved successfully.",
        "response": res.json()
    }


def create_collection(params):
    """
    Creates a new collection in Outline.

    Required:
        name (str)         – Collection name
        description (str)  – Short description

    Optional:
        permission (str) – Default "read_write"
        icon (str)       – Default "📁"
        color (str)      – Default "#000000"
        sharing (bool)   – Default False
    """
    import requests
    from system_settings import load_credential

    # Required fields
    name = params.get("name")
    description = params.get("description")

    if not name or not description:
        return {
            "status": "error",
            "message": "❌ 'name' and 'description' are required to create a collection."
        }

    # Optional with defaults
    permission = params.get("permission", "read_write")
    icon = params.get("icon", "📁")
    color = params.get("color", "#000000")
    sharing = params.get("sharing", False)

    api_base = "https://app.getoutline.com/api"
    token = load_credential("outline_api_key")
    if not token:
        return {
            "status": "error",
            "message": "❌ Missing Outline API token in credentials.json"
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "name": name,
        "description": description,
        "permission": permission,
        "icon": icon,
        "color": color,
        "sharing": sharing
    }

    res = requests.post(f"{api_base}/collections.create", json=payload, headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def get_collection(collection_id):
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message':
            '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type':
        'application/json'}
    payload = {'id': collection_id}
    res = requests.post(f'{api_base}/collections.info', json=payload,
        headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def update_collection(collection_id, name, description, permission, icon,
    color, sharing):
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message':
            '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type':
        'application/json'}
    payload = {'id': collection_id, 'name': name, 'description':
        description, 'permission': permission, 'icon': icon, 'color': color,
        'sharing': sharing}
    res = requests.post(f'{api_base}/collections.update', json=payload,
        headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def delete_collection(collection_id):
    from system_settings import load_credential
    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message':
            '❌ Missing Outline API token in credentials.json'}
    headers = {'Authorization': f'Bearer {token}', 'Content-Type':
        'application/json'}
    payload = {'id': collection_id}
    res = requests.post(f'{api_base}/collections.delete', json=payload,
        headers=headers, verify=False)
    res.raise_for_status()
    return res.json()


def archive_doc(params):
    from system_settings import load_credential
    import requests
    doc_id = params.get('doc_id')
    if not doc_id:
        return {'status': 'error', 'message': '❌ Missing doc_id'}
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token'}
    url = 'https://app.getoutline.com/api/documents.archive'
    headers = {'Authorization': f'Bearer {token}', 'Content-Type':
        'application/json'}
    res = requests.post(url, json={'id': doc_id}, headers=headers)
    if res.status_code == 200:
        return {'status': 'success', 'message': f'✅ Document {doc_id} archived'
            }
    else:
        return {'status': 'error', 'message':
            f'❌ Failed to archive: {res.text}'}


def share_doc_publicly(doc_id):
    from system_settings import load_credential
    import requests

    api_base = 'https://app.getoutline.com/api'
    token = load_credential('outline_api_key')
    if not token:
        return {'status': 'error', 'message': '❌ Missing Outline API token'}

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    # Step 1 — Create the share object
    payload = {'documentId': doc_id}
    res = requests.post(f'{api_base}/shares.create', json=payload, headers=headers, verify=False)

    if res.status_code != 200:
        return {
            'status': 'error',
            'step': 'create',
            'code': res.status_code,
            'message': res.text
        }

    data = res.json().get('data', {})
    share_id = data.get('id')

    # Step 2 — Immediately publish the share link
    publish_payload = {'id': share_id, 'published': True}
    pub_res = requests.post(f'{api_base}/shares.update', json=publish_payload, headers=headers, verify=False)

    if pub_res.status_code != 200:
        return {
            'status': 'error',
            'step': 'publish',
            'code': pub_res.status_code,
            'message': pub_res.text
        }

    return {
        'status': 'success',
        'shared_url': data.get('url'),
        'doc_title': data.get('documentTitle'),
        'published': True
    }

# --- Action Router ---
def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()

    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError:
        print(json.dumps({'status': 'error', 'message': '❌ Invalid JSON format.'}, indent=2))
        return

    if args.action == 'create_doc':
        result = create_doc(params)
    elif args.action == 'get_doc':
        result = get_doc(params)
    elif args.action == 'update_doc':
        result = update_doc(params)
    elif args.action == 'delete_doc':
        result = delete_doc(params)
    elif args.action == 'list_docs':
        result = list_docs(params)
    elif args.action == 'search_docs':
        result = search_docs(params)
    elif args.action == 'get_url':
        result = get_url(params)
    elif args.action == 'patch_section':
        result = patch_section(params)
    elif args.action == 'append_section':
        result = append_section(params)
    elif args.action == 'export_doc':
        result = export_doc(params)
    elif args.action == 'import_doc_from_file':
        result = import_doc_from_file(params)
    elif args.action == 'move_doc':
        result = move_doc(params)
    elif args.action == 'create_collection':
        result = create_collection(params)
    elif args.action == 'get_collection':
        result = get_collection(params)
    elif args.action == 'update_collection':
        result = update_collection(params)
    elif args.action == 'delete_collection':
        result = delete_collection(params)
    elif args.action == 'archive_doc':
        result = archive_doc(params)
    elif args.action == 'share_doc_publicly':
        result = share_doc_publicly(params)
    elif args.action == 'ask_outline_ai':
        query = params["query"] if isinstance(params, dict) and "query" in params else params
        result = ask_outline_ai(query)
    elif args.action == 'get_nested_doc':
        result = get_nested_doc(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()