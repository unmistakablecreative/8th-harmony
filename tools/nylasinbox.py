import requests
import json

def check_email(page_token=None):
    import time
    import requests

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    params = {
        'limit': 50,
        'unread': True,
        'in': 'INBOX'
    }

    if page_token:
        params['page_token'] = page_token

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])
    results = []

    skip_folders = {
        "CATEGORY_UPDATES", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL",
        "CATEGORY_FORUMS", "SPAM"
    }

    for msg in messages:
        folders = msg.get('folders', [])
        if "INBOX" not in folders:
            continue
        if any(f in skip_folders for f in folders):
            continue

        sender = msg.get('from', [{}])[0].get('email', '').lower()
        subject = msg.get('subject', '')
        date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0)))

        results.append({
            'from': sender,
            'subject': subject,
            'date': date
        })

    return {
        'status': 'success',
        'data': results,
        'next_cursor': response.json().get('next_cursor')  # for chaining
    }


    import requests

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/send'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    # 🔐 Auto-wrap with basic HTML formatting if not already structured
    if not is_html:
        # Normalize spacing → double line breaks = <p>, singles = <br>
        clean_body = body.strip().replace("\r\n", "\n")  # normalize line endings
        paragraphs = clean_body.split("\n\n")
        html_blocks = [f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs]
        body = "\n".join(html_blocks)
        is_html = True  # force switch to HTML

    payload = {
        'to': [{'email': to}],
        'subject': subject,
        'body': body,
        'content_type': 'text/html'
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}
    return {'status': 'success', 'data': response.json()}

def send_email(to, subject, body, is_html=False):
    import requests
    import markdown2

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/send'
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    if not is_html:
        body = markdown2.markdown(body.strip())
        is_html = True

    payload = {
        'to': [{'email': to}],
        'subject': subject,
        'body': body,
        'content_type': 'text/html'
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}
    return {'status': 'success', 'data': response.json()}



def open_message(message_id):
    import requests

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/{message_id}'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    data = response.json().get('data', {})
    body = data.get('body')

    if not body:
        return {'status': 'error', 'message': 'No message body returned.'}

    return {'status': 'success', 'data': body}


def search_messages(subject=None, from_email=None):
    import requests
    import time

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    params = {'limit': 40}
    if subject:
        params['subject'] = subject
    if from_email:
        params['from'] = from_email

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])
    results = []
    for msg in messages:
        results.append({
            'id': msg.get('id'),
            'from': msg.get('from', [{}])[0].get('email', ''),
            'subject': msg.get('subject', ''),
            'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0)))
        })

    return {'status': 'success', 'data': results}


def list_folders():
    import requests

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/folders'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    folders = response.json().get('data', [])
    results = [{'id': f.get('id'), 'name': f.get('name'), 'attributes': f.get('attributes', [])} for f in folders]
    return {'status': 'success', 'data': results}



def create_folder(name):
    import requests
    import json

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/folders'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    payload = {'name': name}

    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    return {'status': 'success', 'data': response.json()}


def archive_email(message_id):
    import requests
    import json

    grant_id = '8faa0d81-5fc7-4643-aef2-07677ba4152b'
    access_token = 'nyk_v0_WVuMq1MiKKUf5OWo1MM5Gdg4t22zyyx0GRHuzbf6SIJ3H2rM4S3gJYkrUHyocKcw'
    folder_id = 'Label_4284'  # You can replace this with actual folder lookup
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/{message_id}'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    payload = {'folder_id': folder_id}

    response = requests.put(url, headers=headers, data=json.dumps(payload))
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    return {'status': 'success', 'message': 'Message archived to Superhuman/AutoArchived.'}





def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if 'include_ids' in params:
        params['include_ids'] = str(params['include_ids']).lower() == 'true'

    if args.action == 'check_email':
        result = check_email(**params)
    elif args.action == 'open_message':
        result = open_message(**params)
    elif args.action == 'search_messages':
        result = search_messages(**params)
    elif args.action == 'list_folders':
        result = list_folders(**params)
    elif args.action == 'create_folder':
        result = create_folder(**params)
    elif args.action == 'archive_email':
        result = archive_email(**params)
    elif args.action == 'send_email':
        result = send_email(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
