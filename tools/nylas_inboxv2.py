import json
import math
import os
import requests
import time
from collections import defaultdict
from system_settings import load_credential
import markdown2

# =============================================================================
# Email Template Configuration - loaded from data/email_template_config.json
# =============================================================================
def _load_email_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data/email_template_config.json')
    with open(config_path, 'r') as f:
        return json.load(f)

def get_context_map():
    return _load_email_config()['context_map']

def get_test_crm_map():
    return _load_email_config()['test_crm_map']


def clean_email_content(raw_content):
    """Clean email content by stripping HTML and formatting"""
    if not raw_content:
        return "(No content)"
    
    import re
    
    content = raw_content
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    content = re.sub(r'<[^>]+>', '', content)
    
    content = content.replace('&nbsp;', ' ')
    content = content.replace('&amp;', '&')
    content = content.replace('&lt;', '<')
    content = content.replace('&gt;', '>')
    content = content.replace('&quot;', '"')
    content = content.replace('&#39;', "'")
    content = content.replace('&apos;', "'")
    
    content = re.sub(r'\s+', ' ', content)
    content = content.strip()
    
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line and not any(skip in line.lower() for skip in [
            'unsubscribe', 'privacy policy', 'copyright', 'all rights reserved',
            'this email was sent', 'update your preferences', 'click here to'
        ]):
            cleaned_lines.append(line)
    
    final_content = ' '.join(cleaned_lines).strip()
    return final_content if final_content else "(No content)"


def fetch_inbox(params):
    """Get inbox emails with clean content and auto-tags"""
    page_token = params.get("page_token")
    limit = params.get("limit", 50)
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    api_params = {'limit': limit, 'in': 'INBOX'}
    if page_token:
        api_params['page_token'] = page_token

    response = requests.get(url, headers=headers, params=api_params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])
    results = []
    
    for msg in messages:
        raw_body = msg.get('body', '') or msg.get('snippet', '')
        clean_body = clean_email_content(raw_body)

        subject = msg.get('subject', '')
        sender = msg.get('from', [{}])[0].get('email', '')

        results.append({
            'subject': subject,
            'sender': sender,
            'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0))),
            'message_id': msg.get('id'),
            'thread_id': msg.get('thread_id'),
            'body': clean_body
        })

    return {'status': 'success', 'data': results, 'next_cursor': response.json().get('next_cursor')}


def _chain_inbox_dashboard_steps():
    """Chain prepare_inbox_dashboard and assign FILL task after inbox_summary.json is written.
    
    Called from build_summary early return path. Agent merge path handles this via task instructions.
    """
    import urllib.request
    
    # Step 1: Run prepare_inbox_dashboard
    try:
        result = prepare_inbox_dashboard({})
        print(f"prepare_inbox_dashboard result: {result.get('status')}")
    except Exception as e:
        print(f"prepare_inbox_dashboard failed: {e}")
        return
    
    # Step 2: Assign FILL task via execution_hub
    fill_task = {
        "tool_name": "claude_assistant",
        "action": "assign_task",
        "params": {
            "description": "Read data/inbox_latest.json and fill ALL FILL fields: what_happened.summary (1-2 sentences), updates.worth_knowing (notable items), updates.pointless_shit (roast spam), and each action.items[].action_needed (1 sentence). Write completed file to BOTH data/inbox_latest.json AND semantic_memory/data/inbox_latest.json. Verify zero FILL markers remain."
        }
    }
    
    try:
        req = urllib.request.Request(
            "http://localhost:5001/execute_task",
            data=json.dumps(fill_task).encode(),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        task_result = json.loads(resp.read().decode())
        print(f"FILL task assigned: {task_result.get('task_id', 'unknown')}")
    except Exception as e:
        print(f"Failed to assign FILL task: {e}")


def build_summary(params):
    """Fetch ALL inbox emails and send to single agent for categorization.

    MERGE BEHAVIOR: Preserves existing classifications from inbox_summary.json.
    Only sends NEW emails (not in existing file) to agent for classification.
    Removes emails no longer in Nylas (archived/deleted) from the summary.
    """
    from datetime import datetime
    import glob as glob_module
    import urllib.request

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    # Clean up old chunk files before starting
    for old_file in glob_module.glob(os.path.join(data_dir, "inbox_chunk_*.json")):
        os.remove(old_file)

    # === STEP 1: Fetch all emails from Nylas with pagination ===
    all_messages = []
    page_token = None
    page_count = 0

    while True:
        check_params = {"limit": 50}
        if page_token:
            check_params["page_token"] = page_token

        check_result = fetch_inbox(check_params)
        if check_result.get("status") != "success":
            return {"status": "error", "message": "Failed to fetch email list"}

        messages = check_result.get("data", [])
        all_messages.extend(messages)
        page_count += 1

        next_cursor = check_result.get("next_cursor")
        if not next_cursor or not messages:
            break
        page_token = next_cursor

    # Build flat list of emails from Nylas
    fetched_emails = []
    fetched_ids = set()
    for msg in all_messages:
        msg_id = msg.get("message_id")
        fetched_ids.add(msg_id)
        fetched_emails.append({
            "message_id": msg_id,
            "thread_id": msg.get("thread_id"),
            "subject": msg.get("subject", ""),
            "sender": msg.get("sender", ""),
            "date": msg.get("date", ""),
            "body": msg.get("body", "")
        })

    total_fetched = len(fetched_emails)
    os.makedirs(data_dir, exist_ok=True)

    # === STEP 2: Load existing classifications ===
    inbox_file = os.path.join(data_dir, "inbox_summary.json")
    existing_classifications = {}  # message_id -> {email_obj, category}

    if os.path.exists(inbox_file):
        try:
            with open(inbox_file, "r") as f:
                existing_data = json.load(f)

            # Build map of existing message_ids to their category and full email object
            for category in ["reply", "read", "update", "podcast", "signal", "action", "revisit"]:
                for email in existing_data.get(category, []):
                    msg_id = email.get("message_id")
                    if msg_id:
                        existing_classifications[msg_id] = {
                            "email": email,
                            "category": category
                        }
        except (json.JSONDecodeError, IOError):
            existing_classifications = {}

    # === STEP 3: Diff to find only NEW emails ===
    already_classified = []
    unclassified_emails = []

    for email in fetched_emails:
        msg_id = email.get("message_id")
        if msg_id in existing_classifications:
            already_classified.append(existing_classifications[msg_id])
        else:
            unclassified_emails.append(email)

    # === STEP 4: If no new emails, chain dashboard and return early ===
    if not unclassified_emails:
        final_summary = {
            "reply": [],
            "read": [],
            "update": [],
            "podcast": [],
            "signal": [],
            "action": [],
            "revisit": [],
            "meta": {
                "total": len(already_classified),
                "auto_archived_count": 0,
                "generated_at": datetime.now().isoformat()
            }
        }
        for item in already_classified:
            cat = item["category"]
            if cat in final_summary:
                final_summary[cat].append(item["email"])

        with open(inbox_file, "w") as f:
            json.dump(final_summary, f, indent=2)

        _chain_inbox_dashboard_steps()

        return {
            "status": "success",
            "message": "No new emails to classify. Existing classifications preserved.",
            "total_emails": total_fetched,
            "already_classified": len(already_classified),
            "new_emails": 0,
            "pages_fetched": page_count
        }

    # === STEP 5: Send ALL new emails to ONE agent ===
    # Store already_classified for merge after agent finishes
    classified_cache_file = os.path.join(data_dir, "inbox_classified_cache.json")
    with open(classified_cache_file, "w") as f:
        json.dump(already_classified, f, indent=2)

    # Build the task description with inline email data
    emails_json = json.dumps(unclassified_emails, indent=2)
    task_description = f"""Categorize these emails as reply/read/update/revisit/relax.

Rules:
- reply: emails from real humans that need a personal response from Srini
- read: informational content worth reading (industry news, articles, substantive newsletters)
- update: service notifications, receipts, shipping updates, account alerts
- revisit: emails Srini has already replied to where he is waiting for a response back (thread where Srini sent the last message)
- relax: marketing spam, cold outreach, promotional newsletters, anything Srini doesn't need to see

Write the categorized results to data/inbox_chunk_result_1.json. Each email object should have a 'category' field with the classification.

Here are the emails to categorize:
{emails_json}"""

    # Assign task to single agent
    assign_payload = json.dumps({
        "tool_name": "claude_assistant",
        "action": "assign_task",
        "params": {
            "description": task_description,
            "priority": "high"
        }
    })

    try:
        req = urllib.request.Request(
            "http://localhost:5001/execute_task",
            data=assign_payload.encode(),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=60)
        assign_result = json.loads(resp.read().decode())
        task_id = assign_result.get("task_id", "unknown")
    except Exception as e:
        return {"status": "error", "message": f"Failed to assign categorization task: {str(e)}"}

    # === STEP 6: Poll for result file ===
    result_file = os.path.join(data_dir, "inbox_chunk_result_1.json")
    max_wait = 120
    poll_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        if os.path.exists(result_file):
            break
        time.sleep(poll_interval)
        elapsed += poll_interval

    if not os.path.exists(result_file):
        return {
            "status": "error",
            "message": f"Timed out waiting for categorization result after {max_wait}s",
            "task_id": task_id
        }

    # === STEP 7: Merge new categorized emails with existing ===
    try:
        with open(result_file, "r") as f:
            new_categorized = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return {"status": "error", "message": f"Failed to read categorization result: {str(e)}"}

    # Build final summary
    final_summary = {
        "reply": [],
        "read": [],
        "update": [],
        "podcast": [],
        "signal": [],
        "action": [],
        "revisit": [],
        "meta": {
            "total": 0,
            "auto_archived_count": 0,
            "generated_at": datetime.now().isoformat()
        }
    }

    # Add existing classified emails
    for item in already_classified:
        cat = item["category"]
        if cat in final_summary:
            final_summary[cat].append(item["email"])

    # Add newly categorized emails
    relax_count = 0
    for email in new_categorized:
        cat = email.get("category", "update")
        if cat == "relax":
            relax_count += 1
            continue
        if cat in final_summary:
            final_summary[cat].append(email)

    # Update meta
    total_non_relax = sum(len(final_summary[cat]) for cat in final_summary if cat != "meta")
    final_summary["meta"]["total"] = total_non_relax
    final_summary["meta"]["auto_archived_count"] = relax_count

    with open(inbox_file, "w") as f:
        json.dump(final_summary, f, indent=2)

    # === STEP 8: Cleanup temp files ===
    try:
        os.remove(result_file)
    except OSError:
        pass
    try:
        os.remove(classified_cache_file)
    except OSError:
        pass

    # === STEP 9: Chain dashboard steps ===
    _chain_inbox_dashboard_steps()

    return {
        "status": "success",
        "total_emails": total_fetched,
        "already_classified": len(already_classified),
        "new_emails": len(unclassified_emails),
        "relax_filtered": relax_count,
        "task_id": task_id,
        "pages_fetched": page_count,
        "message": f"Categorized {len(unclassified_emails)} new emails (preserved {len(already_classified)} existing). {relax_count} marked as relax."
    }

def read_inbox_summary(params):
    """Read the grouped inbox summary JSON file - returns FULL data (actionable items only)"""
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")

        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}

        with open(inbox_file, "r") as f:
            data = json.load(f)

        if isinstance(data, list):
            return {"status": "success", "data": data, "count": len(data), "format": "legacy"}

        return {
            "status": "success",
            "data": data,
            "count": data.get("meta", {}).get("total", 0),
            "auto_archived_count": data.get("meta", {}).get("auto_archived_count", 0),
            "breakdown": {
                "reply": len(data.get("reply", [])),
                "podcast": len(data.get("podcast", [])),
                "read": len(data.get("read", [])),
                "update": len(data.get("update", []))
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}



def generate_inbox_latest_template(params):
    result = read_inbox_summary({})
    if result.get("status") != "success":
        return {"status": "error", "message": "Failed to read inbox_summary.json"}
    data = result.get("data", {})
    reply_emails = data.get("reply", [])
    template = {"what_happened": {"summary": "FILL THIS"}, "what_matters": {"summary": "FILL THIS"}, "what_to_do": []}
    for email in reply_emails:
        template["what_to_do"].append({"message_id": email.get("message_id", ""), "sender": email.get("sender", "Unknown"), "subject": email.get("subject", "No subject"), "summary": "FILL THIS"})
    return {"status": "template", "template": template}
def build_updates_summary(params):
    """Generate grouped summary of all Update emails"""
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")

        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}

        with open(inbox_file, "r") as f:
            data = json.load(f)

        update_emails = data.get("update", [])
        
        if not update_emails:
            return {"status": "success", "summary": "No updates found.", "count": 0}
        
        grouped = defaultdict(list)
        for email in update_emails:
            sender = email.get('sender', '')
            domain = sender.split('@')[1] if '@' in sender else sender
            service_name = domain.split('.')[0].title()
            grouped[service_name].append(email)
        
        summary = f"# 🔄 Updates Summary\n\n**Total Updates:** {len(update_emails)}\n\n"
        
        for service, emails in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
            summary += f"## {service} ({len(emails)} updates)\n\n"
            for email in emails[:3]:
                subject = email['subject'][:60] if email['subject'] else "(No subject)"
                summary += f"- {subject}\n"
            
            if len(emails) > 3:
                summary += f"- *...and {len(emails) - 3} more*\n"
            
            summary += "\n"
        
        return {
            "status": "success",
            "summary": summary,
            "count": len(update_emails),
            "grouped_data": {service: len(emails) for service, emails in grouped.items()}
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_by_tag(params):
    """Get emails by category (reply, podcast, read, update) - returns FULL category.
    Note: Relax emails are auto-archived and not stored in summary."""
    tag_filter = params.get("tag_filter", "").lower()

    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")

        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}

        with open(inbox_file, "r") as f:
            data = json.load(f)

        tag_map = {"reply": "reply", "podcast": "podcast", "read": "read", "update": "update"}

        if tag_filter and tag_filter in tag_map:
            cat_data = data.get(tag_map[tag_filter], [])
            return {"status": "success", "data": cat_data, "count": len(cat_data), "category": tag_filter}
        elif tag_filter == "relax":
            return {"status": "success", "data": [], "count": 0, "category": "relax",
                    "note": "Relax emails are auto-archived and not stored in summary"}
        else:
            all_emails = (data.get("reply", []) + data.get("podcast", []) +
                         data.get("read", []) + data.get("update", []))
            return {"status": "success", "data": all_emails, "count": len(all_emails)}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def search(params):
    """Search Gmail directly via Nylas API using Gmail native search syntax.

    All inputs are normalized to a single query string sent to search_query_native.

    Args:
        query: Gmail native search syntax, used as-is (e.g., "from:quinn anthropic")
        sender: Converted to "from:value" and appended to query
        subject: Converted to "subject:value" and appended to query
        tag: Falls back to local inbox_summary.json search for backward compatibility
        limit: Max results (default 10)

    Examples:
        search(params={'sender': 'Quinn'}) -> query="from:Quinn"
        search(params={'subject': 'refund'}) -> query="subject:refund"
        search(params={'query': 'anthropic refund'}) -> query="anthropic refund"
        search(params={'sender': 'Quinn', 'subject': 'API'}) -> query="from:Quinn subject:API"
    """
    sender = params.get("sender")
    subject = params.get("subject")
    query = params.get("query")
    tag = params.get("tag", "").lower()
    limit = params.get("limit", 10)

    # If tag is provided, fall back to local search for backward compatibility
    if tag:
        return search_messages_local(params)

    # Build single query string from all inputs
    query_parts = []
    if sender:
        query_parts.append(f'from:{sender}')
    if subject:
        query_parts.append(f'subject:{subject}')
    if query:
        query_parts.append(query)

    final_query = ' '.join(query_parts)

    if not final_query:
        return {"status": "error", "message": "Must provide at least one search parameter: query, sender, subject, or tag"}

    try:
        creds = load_credential("nylas_inbox")
        GRANT_ID = creds['grant_id']
        ACCESS_TOKEN = creds['access_token']

        url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages'
        headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}

        api_params = {'limit': limit, 'search_query_native': final_query}

        response = requests.get(url, headers=headers, params=api_params)
        if response.status_code != 200:
            return {'status': 'error', 'message': response.text}

        messages = response.json().get('data', [])
        results = []

        for msg in messages:
            raw_body = msg.get('body', '') or msg.get('snippet', '')
            clean_body = clean_email_content(raw_body)

            results.append({
                'subject': msg.get('subject', ''),
                'sender': msg.get('from', [{}])[0].get('email', ''),
                'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0))),
                'message_id': msg.get('id'),
                'body': clean_body[:500] if clean_body else ''
            })

        return {
            "status": "success",
            "data": results,
            "count": len(results),
            "query_sent": final_query
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_messages_local(params):
    """Search local inbox_summary.json by sender, subject, or category. Legacy function for tag-based searches."""
    sender = params.get("sender")
    subject = params.get("subject")
    tag = params.get("tag", "").lower()

    if not any([sender, subject, tag]):
        return {"status": "error", "message": "Must provide at least one search parameter: sender, subject, or tag"}

    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")

        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}

        with open(inbox_file, "r") as f:
            data = json.load(f)

        tag_map = {"reply": "reply", "podcast": "podcast", "read": "read", "update": "update"}
        if tag and tag in tag_map:
            results = data.get(tag_map[tag], [])
        elif tag == "relax":
            return {"status": "success", "data": [], "count": 0,
                    "filters": {"sender": sender, "subject": subject, "category": tag},
                    "note": "Relax emails are auto-archived and not stored in summary"}
        else:
            results = (data.get("reply", []) + data.get("podcast", []) +
                      data.get("read", []) + data.get("update", []))

        if sender:
            results = [e for e in results if sender.lower() in e.get("sender", "").lower()]

        if subject:
            results = [e for e in results if subject.lower() in e.get("subject", "").lower()]

        return {
            "status": "success",
            "data": results,
            "count": len(results),
            "filters": {"sender": sender, "subject": subject, "category": tag}
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def read_message(params):
    """Get single message with cleaned content"""
    message_id = params.get("message_id")
    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {"status": "error", "message": response.text}

    response_data = response.json()
    # Nylas v3 API nests message under 'data' key
    msg_data = response_data.get('data', response_data)

    raw_body = msg_data.get("body_plain") or msg_data.get("body") or msg_data.get("snippet") or ""
    body = clean_email_content(raw_body)

    # Get sender email from 'from' array
    from_list = msg_data.get('from', [])
    sender_email = from_list[0].get('email', '') if from_list else ''

    return {
        "status": "success",
        "subject": msg_data.get('subject', ''),
        "sender": sender_email,
        "date": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg_data.get('date', 0))),
        "message_id": message_id,
        "body": body
    }


def read_thread(params):
    """Get all messages in a thread from a single message_id.

    Takes a message_id, fetches the thread_id from that message,
    then retrieves ALL messages in the thread via Nylas threads API.

    Args:
        message_id: Any message ID in the thread

    Returns:
        All messages in chronological order with sender, date, subject, and cleaned body.
    """
    message_id = params.get("message_id")
    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

    # Step 1: Get the message to find its thread_id
    msg_url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    msg_response = requests.get(msg_url, headers=headers)
    if msg_response.status_code != 200:
        return {"status": "error", "message": f"Failed to fetch message: {msg_response.text}"}

    msg_data = msg_response.json().get('data', {})
    thread_id = msg_data.get('thread_id')
    if not thread_id:
        return {"status": "error", "message": "Message has no thread_id"}

    # Step 2: Get the thread with all messages
    thread_url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/threads/{thread_id}"
    thread_response = requests.get(thread_url, headers=headers)
    if thread_response.status_code != 200:
        return {"status": "error", "message": f"Failed to fetch thread: {thread_response.text}"}

    thread_data = thread_response.json().get('data', {})
    message_ids = thread_data.get('message_ids', [])

    # Step 3: Fetch each message in the thread
    messages = []
    for mid in message_ids:
        try:
            m_url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{mid}"
            m_resp = requests.get(m_url, headers=headers)
            if m_resp.status_code == 200:
                m_data = m_resp.json().get('data', {})
                from_list = m_data.get('from', [])
                sender_email = from_list[0].get('email', '') if from_list else ''
                sender_name = from_list[0].get('name', '') if from_list else ''
                raw_body = m_data.get('body_plain') or m_data.get('body') or m_data.get('snippet') or ''
                messages.append({
                    'message_id': mid,
                    'sender': sender_email,
                    'sender_name': sender_name,
                    'subject': m_data.get('subject', ''),
                    'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m_data.get('date', 0))),
                    'date_epoch': m_data.get('date', 0),
                    'body': clean_email_content(raw_body)
                })
        except Exception:
            continue  # Skip messages that fail to fetch

    # Sort chronologically (oldest first)
    messages.sort(key=lambda x: x.get('date_epoch', 0))

    return {
        "status": "success",
        "thread_id": thread_id,
        "message_count": len(messages),
        "subject": thread_data.get('subject', ''),
        "messages": messages
    }



def send(params):
    """Send beautifully formatted email with automatic styling. Supports scheduled sending via send_at and file attachments."""
    to = params.get("to")
    subject = params.get("subject")
    body = params.get("body")
    send_at = params.get("send_at")
    attachments = params.get("attachments", [])  # List of file paths
    to_override = params.get("to_override")  # Override recipient for testing

    if not all([to, subject, body]):
        return {"status": "error", "message": "Missing required parameters: to, subject, body"}

    # Apply to_override if set (for test_rule safe testing)
    if to_override:
        to = to_override

    import re
    import base64
    import mimetypes

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/send'
    
    # Determine if we need multipart (for attachments > 3MB total) or JSON
    use_multipart = False
    attachment_data = []
    total_attachment_size = 0
    
    for file_path in attachments:
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"Attachment file not found: {file_path}"}
        file_size = os.path.getsize(file_path)
        total_attachment_size += file_size
        
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        attachment_data.append({
            'filename': filename,
            'content_type': content_type,
            'content': file_content,
            'size': file_size
        })
    
    # Use multipart if total attachments exceed 3MB
    if total_attachment_size > 3 * 1024 * 1024:
        use_multipart = True

    formatted_body = body
    formatted_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', formatted_body)
    formatted_body = re.sub(r'\*(.+?)\*', r'<em>\1</em>', formatted_body)

    lines = formatted_body.split('\n')
    table_lines = []
    processed_lines = []
    in_table = False
    in_list = False

    for line in lines:
        stripped = line.strip()

        header_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if header_match:
            level = len(header_match.group(1))
            header_text = header_match.group(2)
            font_size = max(14, 26 - (level * 2))
            processed_lines.append(f'<h{level} style="margin: 15px 0 10px 0; font-size: {font_size}px; font-weight: bold; color: #222;">{header_text}</h{level}>')
            continue

        if '|' in stripped and stripped.count('|') >= 2:
            if not in_table:
                if in_list:
                    processed_lines.append('</ul>')
                    in_list = False
                table_lines = []
                in_table = True
            table_lines.append(stripped)
            continue

        if in_table:
            in_table = False
            if len(table_lines) >= 2:
                html_table = '<table style="border-collapse: collapse; width: 100%; margin: 20px 0;">'
                header_row = table_lines[0].strip('|').split('|')
                html_table += '<thead><tr>'
                for cell in header_row:
                    html_table += f'<th style="border: 1px solid #ddd; padding: 12px; text-align: left; background-color: #f4f4f4; font-weight: bold;">{cell.strip()}</th>'
                html_table += '</tr></thead>'
                html_table += '<tbody>'
                for row in table_lines[2:]:
                    cells = row.strip('|').split('|')
                    html_table += '<tr>'
                    for cell in cells:
                        html_table += f'<td style="border: 1px solid #ddd; padding: 12px;">{cell.strip()}</td>'
                    html_table += '</tr>'
                html_table += '</tbody></table>'
                processed_lines.append(html_table)
            table_lines = []

        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                processed_lines.append('<ul style="margin: 10px 0; padding-left: 20px;">')
                in_list = True
            item_text = stripped[2:]
            processed_lines.append(f'<li style="margin: 5px 0;">{item_text}</li>')
        else:
            if in_list:
                processed_lines.append('</ul>')
                in_list = False
            if stripped:
                processed_lines.append(f'<p style="margin: 10px 0; line-height: 1.6;">{stripped}</p>')

    if in_list:
        processed_lines.append('</ul>')

    if in_table and len(table_lines) >= 2:
        html_table = '<table style="border-collapse: collapse; width: 100%; margin: 20px 0;">'
        header_row = table_lines[0].strip('|').split('|')
        html_table += '<thead><tr>'
        for cell in header_row:
            html_table += f'<th style="border: 1px solid #ddd; padding: 12px; text-align: left; background-color: #f4f4f4; font-weight: bold;">{cell.strip()}</th>'
        html_table += '</tr></thead><tbody>'
        for row in table_lines[2:]:
            cells = row.strip('|').split('|')
            html_table += '<tr>'
            for cell in cells:
                html_table += f'<td style="border: 1px solid #ddd; padding: 12px;">{cell.strip()}</td>'
            html_table += '</tr>'
        html_table += '</tbody></table>'
        processed_lines.append(html_table)

    formatted_body = '\n'.join(processed_lines)

    formatted_body = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2" style="color: #1a73e8; text-decoration: none;">\1</a>',
        formatted_body
    )

    formatted_body = re.sub(
        r'(?<!href=")(https?://[^\s<>"]+)(?!")',
        r'<a href="\1" style="color: #1a73e8; text-decoration: none;">\1</a>',
        formatted_body
    )

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    {formatted_body}
</body>
</html>
"""

    payload = {
        'to': [{'email': to}],
        'subject': subject,
        'body': html_body,
        'content_type': 'text/html'
    }

    if send_at:
        payload['send_at'] = int(send_at)

    # Handle attachments
    if attachment_data:
        if use_multipart:
            # Multipart form-data for large attachments (>3MB total)
            headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Accept': 'application/json'}
            files = []
            for i, att in enumerate(attachment_data):
                files.append(('file', (att['filename'], att['content'], att['content_type'])))
            
            # Message payload as JSON string
            message_json = json.dumps(payload)
            response = requests.post(url, headers=headers, data={'message': message_json}, files=files)
        else:
            # JSON with base64 for small attachments (<3MB total)
            headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
            payload['attachments'] = []
            for att in attachment_data:
                payload['attachments'].append({
                    'filename': att['filename'],
                    'content_type': att['content_type'],
                    'content': base64.b64encode(att['content']).decode('utf-8')
                })
            response = requests.post(url, headers=headers, json=payload)
    else:
        # No attachments - standard JSON request
        headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=payload)

    result = {
        'status': 'success' if response.status_code == 200 else 'error',
        'data': response.json() if response.status_code == 200 else response.text,
        'message': 'Email sent successfully' if response.status_code == 200 else 'Failed to send email'
    }

    if attachment_data and response.status_code == 200:
        result['attachments_sent'] = [att['filename'] for att in attachment_data]

    if send_at and response.status_code == 200:
        from datetime import datetime
        scheduled_time = datetime.fromtimestamp(int(send_at)).strftime('%Y-%m-%d %H:%M:%S')
        result['message'] = f'Email scheduled for {scheduled_time}'
        result['scheduled_at'] = scheduled_time

    return result


def list_scheduled(params):
    """List all scheduled emails that haven't been sent yet"""
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/schedules'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    schedules = response.json().get('data', [])

    from datetime import datetime
    results = []
    for sched in schedules:
        send_at = sched.get('send_at')
        results.append({
            'schedule_id': sched.get('schedule_id'),
            'subject': sched.get('subject', '(No subject)'),
            'to': sched.get('to', []),
            'scheduled_for': datetime.fromtimestamp(send_at).strftime('%Y-%m-%d %H:%M:%S') if send_at else None,
            'status': sched.get('status')
        })

    return {
        'status': 'success',
        'count': len(results),
        'scheduled_emails': results
    }


def cancel_scheduled(params):
    """Cancel a scheduled email by schedule_id"""
    schedule_id = params.get("schedule_id")
    if not schedule_id:
        return {"status": "error", "message": "Missing schedule_id parameter"}

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/schedules/{schedule_id}'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}

    response = requests.delete(url, headers=headers)

    return {
        'status': 'success' if response.status_code == 200 else 'error',
        'message': 'Scheduled email cancelled' if response.status_code == 200 else response.text
    }


def reply(params):
    """Reply to an email with proper threading. Supports file attachments."""
    message_id = params.get("message_id")
    body = params.get("body")
    attachments = params.get("attachments", [])  # List of file paths
    
    if not message_id or not body:
        return {"status": "error", "message": "Missing message_id or body parameters"}
    
    import base64
    import mimetypes
    
    msg_result = read_message({"message_id": message_id})
    if msg_result.get("status") != "success":
        return {"status": "error", "message": "Failed to fetch original message"}
    
    original_sender = msg_result.get("sender")
    original_subject = msg_result.get("subject")
    
    if not original_subject.startswith("Re:"):
        reply_subject = f"Re: {original_subject}"
    else:
        reply_subject = original_subject
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/send'

    html_body = markdown2.markdown(body.strip())

    # Process attachments
    use_multipart = False
    attachment_data = []
    total_attachment_size = 0
    
    for file_path in attachments:
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"Attachment file not found: {file_path}"}
        file_size = os.path.getsize(file_path)
        total_attachment_size += file_size
        
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        attachment_data.append({
            'filename': filename,
            'content_type': content_type,
            'content': file_content,
            'size': file_size
        })
    
    if total_attachment_size > 3 * 1024 * 1024:
        use_multipart = True

    payload = {
        'to': [{'email': original_sender}],
        'subject': reply_subject,
        'body': html_body,
        'reply_to_message_id': message_id,
        'content_type': 'text/html'
    }

    # Handle attachments
    if attachment_data:
        if use_multipart:
            headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Accept': 'application/json'}
            files = []
            for att in attachment_data:
                files.append(('file', (att['filename'], att['content'], att['content_type'])))
            message_json = json.dumps(payload)
            response = requests.post(url, headers=headers, data={'message': message_json}, files=files)
        else:
            headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
            payload['attachments'] = []
            for att in attachment_data:
                payload['attachments'].append({
                    'filename': att['filename'],
                    'content_type': att['content_type'],
                    'content': base64.b64encode(att['content']).decode('utf-8')
                })
            response = requests.post(url, headers=headers, json=payload)
    else:
        headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        tag_result = tag_message({
            "message_id": message_id,
            "tags": ["Replied", "Archive"]
        })

        # Remove from inbox JSON files
        remove_from_inbox_json(message_id)

        result = {
            'status': 'success',
            'message': 'Reply sent and email archived',
            'data': response.json(),
            'tag_result': tag_result
        }
        if attachment_data:
            result['attachments_sent'] = [att['filename'] for att in attachment_data]
        return result
    else:
        return {
            'status': 'error',
            'message': response.text
        }


def delete(params):
    """Delete an email permanently"""
    message_id = params.get("message_id")
    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

    response = requests.delete(url, headers=headers)
    
    return {
        "status": "success" if response.status_code == 200 else "error",
        "message": "Email deleted" if response.status_code == 200 else response.text
    }


def archive(params):
    """Archive an email to the Unmistakable Archive folder and remove from INBOX"""
    message_id = params.get("message_id")
    folder_id = params.get("folder_id", "Label_4287")

    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

    payload = {
        "folders": [folder_id],
        "remove_folders": ["INBOX"]
    }

    response = requests.put(url, headers=headers, json=payload)

    if response.status_code == 200:
        # Remove from both inbox_summary.json and inbox_latest.json
        remove_from_inbox_json(message_id)

    return {
        "status": "success" if response.status_code == 200 else "error",
        "message": "Email archived and removed from inbox" if response.status_code == 200 else response.text,
        "folder_used": folder_id
    }


def unarchive(params):
    """Restore an email from archive back to INBOX"""
    message_id = params.get("message_id")
    archive_folder = params.get("folder_id", "Label_4287")

    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

    # Reverse of archive: add INBOX, remove archive folder
    payload = {
        "folders": ["INBOX"],
        "remove_folders": [archive_folder]
    }

    response = requests.put(url, headers=headers, json=payload)

    return {
        "status": "success" if response.status_code == 200 else "error",
        "message": "Email restored to inbox" if response.status_code == 200 else response.text
    }


def batch_unarchive(params):
    """Restore ALL emails from archive folder back to INBOX"""
    archive_folder = params.get("folder_id", "Label_4287")
    limit = params.get("limit", 100)

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

    # Get all emails in archive folder
    list_url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages"
    list_params = {"in": archive_folder, "limit": limit}
    list_resp = requests.get(list_url, headers=headers, params=list_params)

    if list_resp.status_code != 200:
        return {"status": "error", "message": f"Failed to list archived emails: {list_resp.text}"}

    messages = list_resp.json().get("data", [])

    if not messages:
        return {"status": "success", "message": "No emails in archive", "restored": 0}

    # Restore each email to INBOX
    restored = 0
    failed = []
    for msg in messages:
        msg_id = msg.get("id")
        url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{msg_id}"
        payload = {
            "folders": ["INBOX"],
            "remove_folders": [archive_folder]
        }
        resp = requests.put(url, headers=headers, json=payload)
        if resp.status_code == 200:
            restored += 1
        else:
            failed.append(msg_id)

    return {
        "status": "success",
        "message": f"Restored {restored} emails to inbox",
        "restored": restored,
        "failed": len(failed)
    }


def remove_from_inbox_json(message_id):
    """Remove an email from inbox_summary.json and inbox_latest.json.
    Called after archive or reply to keep the JSON files current."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    # Remove from inbox_summary.json
    summary_file = os.path.join(data_dir, "inbox_summary.json")
    if os.path.exists(summary_file):
        try:
            with open(summary_file, "r") as f:
                data = json.load(f)
            # Remove from reply/read/update/podcast arrays
            for cat in ["reply", "read", "update", "podcast"]:
                if cat in data:
                    data[cat] = [e for e in data[cat] if e.get("message_id") != message_id]
            # Update meta counts
            if "meta" in data:
                total = sum(len(data.get(c, [])) for c in ["reply", "read", "update", "podcast"])
                data["meta"]["total"] = total
            with open(summary_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            pass  # Don't fail if JSON update fails

    # Remove from inbox_latest.json
    latest_file = os.path.join(data_dir, "inbox_latest.json")
    if os.path.exists(latest_file):
        try:
            with open(latest_file, "r") as f:
                data = json.load(f)
            # Remove from updates.items
            if "updates" in data and "items" in data["updates"]:
                data["updates"]["items"] = [e for e in data["updates"]["items"] if e.get("message_id") != message_id]
            # Remove from action.items
            if "action" in data and "items" in data["action"]:
                data["action"]["items"] = [e for e in data["action"]["items"] if e.get("message_id") != message_id]
            # Update stats
            if "what_happened" in data and "stats" in data["what_happened"]:
                data["what_happened"]["stats"]["signal_count"] = len(data.get("updates", {}).get("items", []))
                data["what_happened"]["stats"]["action_count"] = len(data.get("action", {}).get("items", []))
            with open(latest_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            pass  # Don't fail if JSON update fails


def batch_delete_emails(params):
    """Delete multiple emails"""
    message_ids = params.get("message_ids", [])
    if not message_ids:
        return {"status": "error", "message": "Missing message_ids parameter"}
    
    results = []
    for msg_id in message_ids:
        result = delete({"message_id": msg_id})
        results.append({"id": msg_id, "status": result["status"]})
    
    return {"status": "complete", "results": results}


def sync_archived_emails(params):
    """Archive emails by message_ids - removes from grouped structure and calls Nylas API"""
    message_ids = params.get("message_ids", [])

    if not message_ids:
        return {"status": "success", "archived_count": 0, "message": "No message_ids provided"}

    if isinstance(message_ids, str):
        message_ids = [message_ids]

    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")

        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}

        with open(inbox_file, "r") as f:
            data = json.load(f)

        archived_count = 0
        errors = []

        for category in ["reply", "podcast", "read", "update"]:
            remaining = []
            for email in data.get(category, []):
                if email.get("message_id") in message_ids:
                    result = archive({"message_id": email["message_id"]})
                    if result.get("status") == "success":
                        archived_count += 1
                    else:
                        errors.append({"id": email["message_id"], "error": result.get("message")})
                        remaining.append(email)
                else:
                    remaining.append(email)
            data[category] = remaining

        total = (len(data.get("reply", [])) + len(data.get("podcast", [])) +
                len(data.get("read", [])) + len(data.get("update", [])))
        if "meta" in data:
            data["meta"]["total"] = total

        with open(inbox_file, "w") as f:
            json.dump(data, f, indent=2)

        return {
            "status": "success",
            "archived_count": archived_count,
            "remaining_count": total,
            "errors": errors if errors else None,
            "message": f"Archived {archived_count} emails, {total} remaining in inbox"
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def tag_message(params):
    """Archive a single email by message_id"""
    message_id = params.get("message_id")
    tags = params.get("tags", [])

    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}

    if isinstance(tags, str):
        tags = [tags]

    if "Archive" in tags:
        return sync_archived_emails({"message_ids": [message_id]})

    return {"status": "success", "message": "Noted. Use Archive to remove emails from inbox."}


def batch_tag_messages(params):
    """Batch archive multiple emails"""
    message_ids = params.get("message_ids")
    tags = params.get("tags", ["Archive"])

    if not message_ids:
        return {"status": "error", "message": "Missing 'message_ids' parameter"}

    if isinstance(message_ids, str):
        message_ids = [message_ids]

    if isinstance(tags, str):
        tags = [tags]

    if "Archive" in tags:
        return sync_archived_emails({"message_ids": message_ids})

    return {"status": "success", "message": "Non-archive tags noted. Categories are structural."}


def search_sent_messages(params):
    """Search sent folder for emails to a specific recipient - duplicate detection"""
    from datetime import datetime, timedelta

    to_email = params.get("to_email")
    days_back = params.get("days_back", 30)
    subject_contains = params.get("subject_contains")

    if not to_email:
        return {"status": "error", "message": "Missing required parameter: to_email"}

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    since_date = datetime.now() - timedelta(days=days_back)
    since_timestamp = int(since_date.timestamp())

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}

    api_params = {
        'limit': 50,
        'in': 'SENT',
        'to': to_email,
        'received_after': since_timestamp
    }

    response = requests.get(url, headers=headers, params=api_params)

    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])

    if subject_contains:
        messages = [m for m in messages if subject_contains.lower() in m.get('subject', '').lower()]

    results = []
    for msg in messages:
        results.append({
            'subject': msg.get('subject', ''),
            'to': [r.get('email') for r in msg.get('to', [])],
            'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0))),
            'message_id': msg.get('id'),
            'thread_id': msg.get('thread_id')
        })

    return {
        'status': 'success',
        'found': len(results) > 0,
        'count': len(results),
        'messages': results,
        'searched_email': to_email,
        'days_back': days_back
    }


def send_from_template(params):
    """
    Universal email-from-template function with duplicate protection.

    Required params:
        name: Person's name, key, or email to look up in CRM
        context: "investor", "beta_user", or "journalist"
        email_type: "initial" or "followup"

    Optional params:
        test_mode: If True, uses test CRM files (default: False)
        send_at: Unix timestamp for scheduled send
        to_override: If set, sends to this email instead of CRM email (for testing)
    """
    import subprocess
    import re
    from datetime import datetime

    name = params.get("name")
    context = params.get("context")
    email_type = params.get("email_type")
    test_mode = params.get("test_mode", False)
    send_at = params.get("send_at")
    to_override = params.get("to_override")  # Force send to this email for testing

    if not name:
        return {"status": "error", "message": "Missing required parameter: name"}
    if not context:
        return {"status": "error", "message": "Missing required parameter: context"}
    if not email_type:
        return {"status": "error", "message": "Missing required parameter: email_type"}

    if context not in get_context_map():
        return {
            "status": "error",
            "message": f"Unknown context: {context}. Valid contexts: {list(get_context_map().keys())}"
        }

    if email_type not in ["initial", "followup"]:
        return {"status": "error", "message": "email_type must be 'initial' or 'followup'"}

    context_config = get_context_map()[context]

    if test_mode:
        crm_file = get_test_crm_map().get(context)
        if not crm_file:
            return {"status": "error", "message": f"No test CRM configured for context: {context}"}
    else:
        crm_file = context_config["crm_file"]

    template_doc_id = context_config["templates"].get(email_type)
    if not template_doc_id:
        return {"status": "error", "message": f"No template configured for {context}/{email_type}"}

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    crm_path = os.path.join(base_dir, crm_file)

    if not os.path.exists(crm_path):
        return {"status": "error", "message": f"CRM file not found: {crm_file}"}

    try:
        with open(crm_path, "r") as f:
            crm_data = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to load CRM: {str(e)}"}

    person_key = None
    person = None

    for key, entry in crm_data.get('entries', {}).items():
        if (key.lower() == name.lower() or
            entry.get("name", "").lower() == name.lower() or
            entry.get("first_name", "").lower() == name.lower() or
            entry.get("email", "").lower() == name.lower()):
            person_key = key
            person = entry
            break

    if not person:
        return {"status": "error", "message": f"Person '{name}' not found in {crm_file}"}

    thread_field = f"{email_type}_thread_id"
    if person.get(thread_field):
        return {
            "status": "error",
            "message": f"{email_type} email already sent to {person.get('name', name)}",
            "existing_thread_id": person[thread_field]
        }

    email_to = person.get("email")
    if not email_to:
        return {"status": "error", "message": f"No email address for {person.get('name', name)}"}

    # Apply to_override if set (for test_rule safe testing)
    original_email = email_to
    if to_override:
        email_to = to_override

    # DUPLICATE PROTECTION (skip for test emails)
    TEST_EMAILS = ["srinirao@gmail.com"]
    
    if email_to not in TEST_EMAILS:
        duplicate_check = search_sent_messages({
            "to_email": email_to,
            "days_back": 90,
            "subject_contains": None
        })
        
        if duplicate_check.get("found"):
            return {
                "status": "error",
                "message": f"Already sent email to {email_to} - found {duplicate_check.get('count')} existing emails in sent folder",
                "duplicate_prevention": True,
                "existing_emails": duplicate_check.get("messages", [])[:3]
            }

    try:
        result = subprocess.run(
            ["python3", "execution_hub.py", "execute_task", "--params", json.dumps({
                "tool_name": "docs",
                "action": "read_doc",
                "params": {"doc_id": template_doc_id}
            })],
            cwd=base_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {"status": "error", "message": f"Failed to fetch template: {result.stderr}"}

        template_result = json.loads(result.stdout)
        template_text = template_result.get("doc", {}).get("content", "")

        if not template_text:
            return {"status": "error", "message": "Template document is empty"}

    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch template: {str(e)}"}

    # ============================================
    # CLEAN TEMPLATE CONTENT
    # ============================================
    # Strip HTML tags from template (it comes as HTML from doc_editor)
    template_text = re.sub(r'<p><strong>Subject:</strong>\s*', 'Subject: ', template_text)
    template_text = re.sub(r'</?p>', '\n', template_text)
    template_text = re.sub(r'</?strong>', '', template_text)
    template_text = re.sub(r'<hr\s*/?>', '\n---\n', template_text)
    template_text = re.sub(r'<h3>(.*?)</h3>', r'### \1', template_text)
    template_text = re.sub(r'<code>(.*?)</code>', r'`\1`', template_text)

    # Clean escaped backslashes and newlines
    template_text = template_text.replace('\\\\n', '\n')  # \\n -> newline
    template_text = template_text.replace('\\n', '\n')    # \n -> newline
    template_text = re.sub(r'<p>\\</p>', '', template_text)  # Remove <p>\</p> artifacts
    template_text = re.sub(r'^\\$', '', template_text, flags=re.MULTILINE)  # Remove lone backslashes on lines
    template_text = template_text.replace('\\\\', '')     # Remove double backslashes
    template_text = template_text.replace('\\', '')       # Remove single backslashes (escaped chars)

    # Clean multiple blank lines
    template_text = re.sub(r'\n{3,}', '\n\n', template_text)

    lines = template_text.split('\n')
    subject = f"Hello from OrchestrateOS"
    body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("**Subject:**"):
            subject = stripped.replace("**Subject:**", "").strip()
            body_start = i + 1
            break
        elif stripped.startswith("Subject:"):
            subject = stripped.replace("Subject:", "").strip()
            body_start = i + 1
            break

    body_lines = []
    for line in lines[body_start:]:
        body_lines.append(line)

    body = '\n'.join(body_lines).strip()

    # ============================================
    # EXTRACT FIRST NAME
    # ============================================
    # Priority: first_name field > first word of name (split on space OR hyphen)
    raw_name = person.get("name", "")
    if person.get("first_name"):
        first_name = person.get("first_name")
    elif raw_name:
        # Split on space or hyphen, take first part, capitalize
        first_name = re.split(r'[\s\-]', raw_name)[0].capitalize()
    else:
        first_name = "there"  # Fallback

    body = body.replace("`Name`", first_name)
    body = body.replace("\\[First Name\\]", first_name)
    body = body.replace("[First Name]", first_name)
    body = body.replace("{{first_name}}", first_name)
    body = body.replace("{{name}}", person.get("name", ""))
    body = body.replace("{{firm}}", person.get("firm", ""))
    body = body.replace("{{company}}", person.get("company", ""))

    formatted_body = body

    formatted_body = re.sub(
        r'\*\*<(https?://[^>]+)>\*\*',
        r'<a href="\1" style="color: #1a73e8; text-decoration: none;">\1</a>',
        formatted_body
    )

    formatted_body = re.sub(
        r'<(https?://[^>]+)>',
        r'<a href="\1" style="color: #1a73e8; text-decoration: none;">\1</a>',
        formatted_body
    )

    formatted_body = re.sub(
        r'\[([^\]]+)\]\(([^\)]+)\)',
        r'<a href="\2" style="color: #1a73e8; text-decoration: none;">\1</a>',
        formatted_body
    )

    formatted_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', formatted_body)
    formatted_body = re.sub(r'\*(.+?)\*', r'<em>\1</em>', formatted_body)

    lines = formatted_body.split('\n')
    processed_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if stripped == '---':
            if in_list:
                processed_lines.append('</ul>')
                in_list = False
            processed_lines.append('<hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">')
        elif stripped.startswith('## '):
            if in_list:
                processed_lines.append('</ul>')
                in_list = False
            header_text = stripped[3:]
            processed_lines.append(f'<h2 style="margin: 20px 0 10px 0; font-size: 18px; font-weight: bold; color: #222;">{header_text}</h2>')
        elif stripped.startswith('### '):
            if in_list:
                processed_lines.append('</ul>')
                in_list = False
            header_text = stripped[4:]
            processed_lines.append(f'<h3 style="margin: 15px 0 8px 0; font-size: 16px; font-weight: bold; color: #333;">{header_text}</h3>')
        elif stripped.startswith('* ') or stripped.startswith('- '):
            if not in_list:
                processed_lines.append('<ul style="margin: 10px 0; padding-left: 20px;">')
                in_list = True
            item_text = stripped[2:]
            processed_lines.append(f'<li style="margin: 5px 0;">{item_text}</li>')
        else:
            if in_list:
                processed_lines.append('</ul>')
                in_list = False
            if stripped:
                processed_lines.append(f'<p style="margin: 10px 0; line-height: 1.6;">{stripped}</p>')

    if in_list:
        processed_lines.append('</ul>')

    formatted_body = '\n'.join(processed_lines)

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    {formatted_body}
</body>
</html>
"""

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/send'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}

    payload = {
        'to': [{'email': email_to}],
        'subject': subject,
        'body': html_body,
        'content_type': 'text/html'
    }

    if send_at:
        payload['send_at'] = int(send_at)

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        return {
            'status': 'error',
            'message': f'Failed to send email: {response.text}'
        }

    response_data = response.json()
    thread_id = response_data.get('data', {}).get('thread_id') or response_data.get('data', {}).get('id')

    if not send_at:
        now = datetime.now().isoformat()
        crm_data['entries'][person_key][f"{email_type}_thread_id"] = thread_id
        crm_data['entries'][person_key][f"{email_type}_sent_date"] = now
        crm_data['entries'][person_key][f"{email_type}_replied"] = False
        crm_data['entries'][person_key]["last_contact"] = now

        try:
            with open(crm_path, "w") as f:
                json.dump(crm_data, f, indent=2)
        except Exception as e:
            return {
                "status": "partial_success",
                "message": f"Email sent but CRM update failed: {str(e)}",
                "thread_id": thread_id,
                "sent_to": email_to
            }

    return {
        "status": "success",
        "message": f"Email {'scheduled' if send_at else 'sent'} to {person.get('name', name)}",
        "thread_id": thread_id,
        "sent_to": email_to,
        "context": context,
        "email_type": email_type,
        "crm_updated": not send_at,
        "test_mode": test_mode,
        "template_used": template_doc_id
    }



def sync_tracking(params):
    """
    Universal tracking sync for any CRM context (investor, beta_user, journalist).
    Checks for replies by querying thread messages.
    """
    from datetime import datetime

    context = params.get("context")
    
    if not context:
        return {"status": "error", "message": "Missing required parameter: context"}
    
    if context not in get_context_map():
        return {
            "status": "error",
            "message": f"Unknown context: {context}. Valid contexts: {list(get_context_map().keys())}"
        }

    crm_file = get_context_map()[context]["crm_file"]
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    crm_path = os.path.join(base_dir, crm_file)

    if not os.path.exists(crm_path):
        return {"status": "error", "message": f"CRM file not found: {crm_file}"}

    try:
        with open(crm_path, "r") as f:
            crm_data = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to load CRM: {str(e)}"}

    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    sender_email = "srini@unmistakablemedia.com"

    updated_entries = []
    errors = []

    thread_fields = ["initial_thread_id", "followup_thread_id"]

    for person_key, person in crm_data.items():
        for field in thread_fields:
            thread_id = person.get(field)
            if not thread_id:
                continue

            email_type = field.replace("_thread_id", "")

            try:
                url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages"
                headers = {
                    "Authorization": f"Bearer {ACCESS_TOKEN}",
                    "Content-Type": "application/json"
                }
                api_params = {"thread_id": thread_id, "limit": 10}

                response = requests.get(url, headers=headers, params=api_params)

                if response.status_code != 200:
                    errors.append({
                        "person": person_key,
                        "thread_id": thread_id,
                        "error": response.text
                    })
                    continue

                messages = response.json().get("data", [])

                has_reply = False
                for msg in messages:
                    msg_from = msg.get("from", [{}])[0].get("email", "")
                    if msg_from and msg_from.lower() != sender_email.lower():
                        has_reply = True
                        break

                replied_field = f"{email_type}_replied"
                if has_reply and not person.get(replied_field):
                    crm_data[person_key][replied_field] = True
                    updated_entries.append({
                        "person": person_key,
                        "email_type": email_type,
                        "field": replied_field,
                        "new_value": True
                    })

                opened_field = f"{email_type}_opened"
                if has_reply and not person.get(opened_field):
                    crm_data[person_key][opened_field] = True
                    updated_entries.append({
                        "person": person_key,
                        "email_type": email_type,
                        "field": opened_field,
                        "new_value": True
                    })

            except Exception as e:
                errors.append({
                    "person": person_key,
                    "thread_id": thread_id,
                    "error": str(e)
                })

    if updated_entries:
        try:
            with open(crm_path, "w") as f:
                json.dump(crm_data, f, indent=2)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to save CRM updates: {str(e)}",
                "updates_pending": updated_entries
            }

    return {
        "status": "success",
        "message": f"Sync complete. {len(updated_entries)} fields updated.",
        "context": context,
        "updated_entries": updated_entries,
        "errors": errors if errors else None,
        "sync_time": datetime.now().isoformat()
    }


def check_and_send_followups(params):
    """
    Universal followup checker for any CRM context.
    Sends followup emails to people who haven't replied after X time.
    """
    from datetime import datetime, timedelta
    
    context = params.get("context")
    followup_delay_minutes = params.get("followup_delay_minutes", 2880)  # Default: 2 days
    
    if not context:
        return {"status": "error", "message": "Missing required parameter: context"}
    
    if context not in get_context_map():
        return {
            "status": "error",
            "message": f"Unknown context: {context}. Valid contexts: {list(get_context_map().keys())}"
        }
    
    crm_file = get_context_map()[context]["crm_file"]
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    crm_path = os.path.join(base_dir, crm_file)
    
    if not os.path.exists(crm_path):
        return {"status": "error", "message": f"CRM file not found: {crm_file}"}
    
    try:
        with open(crm_path, "r") as f:
            crm_data = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Failed to load CRM: {str(e)}"}
    
    candidates = []
    now = datetime.now()
    
    for person_key, person in crm_data.items():
        if not person.get("initial_sent_date"):
            continue
        
        if person.get("initial_replied"):
            continue
        
        if person.get("followup_sent_date"):
            continue
        
        sent_date = datetime.fromisoformat(person["initial_sent_date"])
        time_passed = (now - sent_date).total_seconds() / 60
        
        if time_passed >= followup_delay_minutes:
            candidates.append(person_key)
    
    if not candidates:
        return {
            "status": "success",
            "message": "No follow-ups needed",
            "context": context,
            "checked": len(crm_data),
            "candidates": 0
        }
    
    results = []
    for person_key in candidates:
        result = send_from_template({
            "name": person_key,
            "context": context,
            "email_type": "followup"
        })
        results.append({
            "person": person_key,
            "status": result.get("status"),
            "message": result.get("message")
        })
    
    return {
        "status": "success",
        "message": f"Sent {len(results)} follow-up emails",
        "context": context,
        "results": results
    }


def parse_financial_transaction(email):
    """
    Parse a financial transaction from an email.
    Returns dict with {source, description, amount, type, date} or None if not parseable.

    Financial senders: mercury, stripe, privacy, anthropic billing, aws, google cloud, t-mobile, apple

    CRITICAL: Must filter by SUBJECT LINE keywords, not just sender domain.
    Support tickets, bug reports, refund requests are NOT financial transactions.
    """
    import re
    from datetime import datetime

    sender = email.get("sender", "").lower()
    subject = email.get("subject", "")
    subject_lower = subject.lower()
    body = email.get("body", "")
    date_sent = email.get("date", "")

    # Subject patterns that indicate actual financial transactions
    FINANCIAL_SUBJECT_PATTERNS = [
        r"receipt", r"invoice", r"payment", r"charge", r"transaction",
        r"bill", r"past due", r"transfer", r"subscription renewal",
        r"order confirmed", r"deposit", r"withdrawal", r"refund processed",
        r"credit applied", r"statement ready", r"statement available",
        r"monthly statement", r"spending report", r"usage report",
        r"your .* is ready", r"card .* approved", r"card .* declined",
        r"payment received", r"payment confirmed", r"payment failed",
        r"auto.?pay", r"debit", r"wire transfer", r"ach transfer",
        r"balance", r"billing statement"
    ]

    # Subject patterns that EXCLUDE emails from being financial
    # These are support/correspondence even if from financial senders
    EXCLUDE_SUBJECT_PATTERNS = [
        r"^re:", r"support", r"ticket", r"bug", r"issue",
        r"refund request", r"billing dispute", r"case", r"question",
        r"help", r"problem", r"error", r"fix", r"feedback",
        r"feature request", r"suggestion", r"thank you for contacting",
        r"following up", r"update on your", r"status update"
    ]

    # Check if subject is explicitly excluded (support tickets, etc.)
    for pattern in EXCLUDE_SUBJECT_PATTERNS:
        if re.search(pattern, subject_lower):
            return None

    # First, check if sender is from a financial-related domain
    financial_senders = ["mercury", "stripe", "privacy", "anthropic", "aws", "amazon", "google", "t-mobile", "apple", "billing"]
    is_from_financial_sender = any(fs in sender for fs in financial_senders)

    # Must be from financial sender AND have financial subject keyword
    if not is_from_financial_sender:
        return None

    # Check if subject contains financial keywords
    has_financial_subject = any(re.search(pattern, subject_lower) for pattern in FINANCIAL_SUBJECT_PATTERNS)

    if not has_financial_subject:
        return None

    # Extract source name
    if "privacy" in sender:
        source = "Privacy.com"
    elif "mercury" in sender:
        source = "Mercury"
    elif "stripe" in sender:
        source = "Stripe"
    elif "anthropic" in sender:
        source = "Anthropic"
    elif "aws" in sender or "amazon" in sender:
        source = "AWS"
    elif "google" in sender:
        source = "Google Cloud"
    elif "t-mobile" in sender:
        source = "T-Mobile"
    elif "apple" in sender:
        source = "Apple"
    else:
        source = sender.split("@")[0].title() if "@" in sender else sender[:20]

    # Try to extract amount from subject or body
    amount_pattern = r'\$[\d,]+\.?\d*'
    amount_match = re.search(amount_pattern, subject) or re.search(amount_pattern, body[:500])
    amount = amount_match.group(0) if amount_match else None

    # Determine transaction type from keywords
    text_to_check = (subject + " " + body[:500]).lower()
    if any(kw in text_to_check for kw in ["declined", "failed", "past due", "overdue", "dispute"]):
        tx_type = "alert"
    elif any(kw in text_to_check for kw in ["charge", "payment", "debit", "withdrawal", "purchase"]):
        tx_type = "debit"
    elif any(kw in text_to_check for kw in ["credit", "refund", "deposit", "received"]):
        tx_type = "credit"
    else:
        tx_type = "notification"

    # Format date
    try:
        if date_sent:
            dt = datetime.fromisoformat(date_sent.replace("Z", "+00:00")) if "T" in date_sent else datetime.strptime(date_sent[:10], "%Y-%m-%d")
            formatted_date = dt.strftime("%b %d")
        else:
            formatted_date = "Unknown"
    except:
        formatted_date = date_sent[:10] if date_sent else "Unknown"

    # Build description from subject
    description = subject[:80] if subject else "(No subject)"

    return {
        "source": source,
        "description": description,
        "amount": amount if amount else "",
        "type": tx_type,
        "date": formatted_date
    }


def prepare_inbox_dashboard(params):
    """
    Prepare inbox_latest.json for dashboard rendering.

    DOES NOT call the Nylas API - reads cached inbox_summary.json instead.
    Creates dual-layer structure:
    - Raw data layer: Full email content for context
    - Summary layer: "FILL" fields that Claude fills in

    CLASSIFICATION FIX: If inbox_latest.json exists with filled action_needed values,
    emails where action_needed indicates no real action (confirmations, acknowledgements)
    get moved to updates instead of action.items.

    Claude cannot drop emails - structure is pre-created with all items.
    """
    import os
    import re
    from datetime import datetime

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    inbox_file = os.path.join(data_dir, "inbox_summary.json")
    latest_file = os.path.join(data_dir, "inbox_latest.json")

    # Read cached inbox_summary.json (NO API CALL)
    if not os.path.exists(inbox_file):
        return {"status": "error", "message": "inbox_summary.json not found. Run generate_inbox_summary first."}

    print("Reading cached inbox_summary.json (no API call)...")
    with open(inbox_file, "r") as f:
        inbox_data = json.load(f)

    # Check for existing inbox_latest.json with filled action_needed values
    # Used to re-classify emails that don't actually need action
    existing_action_needed = {}
    if os.path.exists(latest_file):
        try:
            with open(latest_file, "r") as f:
                existing_data = json.load(f)
            for item in existing_data.get("action", {}).get("items", []):
                msg_id = item.get("message_id")
                action_val = item.get("action_needed", "")
                if msg_id and action_val and action_val != "FILL":
                    existing_action_needed[msg_id] = action_val
        except (json.JSONDecodeError, IOError):
            pass

    # Patterns that indicate no real action is needed
    NO_ACTION_PATTERNS = [
        r"no action needed",
        r"no response (needed|required)",
        r"just (an? )?acknowledgement",
        r"confirming (they|she|he) will",
        r"confirmation that",
        r"(they|she|he) ('ll|will) (do|complete|send|handle)",
        r"fyi only",
        r"informational only",
        r"no reply (needed|required|necessary)",
    ]

    def needs_action(action_needed_text):
        """Return False if action_needed text indicates no real action required."""
        if not action_needed_text or action_needed_text == "FILL":
            return True  # Assume yes if not yet filled
        text_lower = action_needed_text.lower()
        for pattern in NO_ACTION_PATTERNS:
            if re.search(pattern, text_lower):
                return False
        return True

    # Action = reply emails, Signal = read + update + podcast
    action_emails = inbox_data.get("reply", [])
    signal_emails = inbox_data.get("read", []) + inbox_data.get("update", []) + inbox_data.get("podcast", [])
    meta = inbox_data.get("meta", {})

    # === ENRICH: Fetch thread_id for emails that don't have it ===
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    # Find action emails missing thread_id
    missing_thread_ids = [e for e in action_emails if not e.get("thread_id")]
    if missing_thread_ids:
        print(f"Enriching {len(missing_thread_ids)} emails with thread_id...")
        headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
        for email in missing_thread_ids:
            msg_id = email.get("message_id")
            if msg_id:
                try:
                    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{msg_id}'
                    resp = requests.get(url, headers=headers)
                    if resp.status_code == 200:
                        msg_data = resp.json().get('data', {})
                        email['thread_id'] = msg_data.get('thread_id')
                except Exception:
                    pass  # Skip if can't fetch
        enriched_count = len([e for e in action_emails if e.get('thread_id')])
        print(f"Enriched: {enriched_count}/{len(action_emails)} action emails now have thread_id")

    # === THREAD GROUPING: Fetch full thread data to determine most recent sender ===
    # Key logic:
    # - If Srini's message is the MOST RECENT in thread → revisit (waiting for their response)
    # - If someone else's message is the MOST RECENT → action (needs Srini's reply)
    # - Never show Srini's own sent messages as revisit cards - show counterparty's last message
    print("Fetching thread data for proper reply detection...")

    SRINI_EMAIL = "srini@unmistakablemedia.com"
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}

    # Group action emails by thread_id first
    from collections import defaultdict
    threads = defaultdict(list)  # thread_id -> list of emails from action_emails
    no_thread_emails = []  # Emails without thread_id

    for email in action_emails:
        thread_id = email.get("thread_id")
        if thread_id:
            threads[thread_id].append(email)
        else:
            no_thread_emails.append(email)

    # For each thread, fetch full thread to determine actual most recent message
    replied_threads = []  # Threads where Srini's reply is most recent (→ revisit)
    needs_reply_threads = []  # Threads where someone else's message is most recent (→ action)

    for thread_id, emails in threads.items():
        try:
            # Fetch full thread from Nylas API
            thread_url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/threads/{thread_id}'
            thread_resp = requests.get(thread_url, headers=headers)

            if thread_resp.status_code == 200:
                thread_data = thread_resp.json().get('data', {})
                all_messages = thread_data.get('message_ids', [])

                # Get the latest message details
                latest_draft = thread_data.get('latest_draft_or_message', {})
                latest_from = latest_draft.get('from', [])
                latest_sender_email = latest_from[0].get('email', '').lower() if latest_from else ''

                # Find the counterparty's last inbound message (not from Srini)
                counterparty_message = None
                for email in sorted(emails, key=lambda e: e.get("date", ""), reverse=True):
                    sender = email.get("sender", "").lower()
                    if SRINI_EMAIL not in sender:
                        counterparty_message = email
                        break

                # If no counterparty message in our emails, use the first one that's not from Srini
                if not counterparty_message:
                    counterparty_message = emails[0]  # Fallback

                thread_info = {
                    "thread_id": thread_id,
                    "most_recent": counterparty_message,  # Always show counterparty's message
                    "thread_messages": all_messages,
                    "message_count": len(all_messages),
                    "latest_sender": latest_sender_email
                }

                # Determine placement based on who sent the ACTUAL most recent message
                if SRINI_EMAIL in latest_sender_email:
                    # Srini's reply is most recent → waiting for their response
                    replied_threads.append(thread_info)
                else:
                    # Someone else's message is most recent → needs Srini's reply
                    needs_reply_threads.append(thread_info)
            else:
                # API error - fall back to treating as needs reply
                most_recent = sorted(emails, key=lambda e: e.get("date", ""), reverse=True)[0]
                needs_reply_threads.append({
                    "thread_id": thread_id,
                    "most_recent": most_recent,
                    "thread_messages": [e.get("message_id") for e in emails],
                    "message_count": len(emails)
                })
        except Exception as e:
            # Error fetching thread - fall back to treating as needs reply
            most_recent = sorted(emails, key=lambda e: e.get("date", ""), reverse=True)[0]
            needs_reply_threads.append({
                "thread_id": thread_id,
                "most_recent": most_recent,
                "thread_messages": [e.get("message_id") for e in emails],
                "message_count": len(emails)
            })

    print(f"Thread grouping: {len(replied_threads)} replied (→ revisit), {len(needs_reply_threads)} needs reply (→ action), {len(no_thread_emails)} ungrouped")

    # Re-classify action threads based on existing action_needed values
    true_action_threads = []
    demoted_to_updates = []

    # Check needs-reply threads against existing action_needed values
    for thread_data in needs_reply_threads:
        msg_id = thread_data["most_recent"].get("message_id", "")
        existing_action = existing_action_needed.get(msg_id, "")
        if existing_action and not needs_action(existing_action):
            # This thread doesn't actually need action - demote most recent email to updates
            demoted_to_updates.append(thread_data["most_recent"])
        else:
            true_action_threads.append(thread_data)

    # Check ungrouped emails (no thread_id)
    true_ungrouped_emails = []
    for email in no_thread_emails:
        msg_id = email.get("message_id", "")
        existing_action = existing_action_needed.get(msg_id, "")
        if existing_action and not needs_action(existing_action):
            demoted_to_updates.append(email)
        else:
            true_ungrouped_emails.append(email)

    if demoted_to_updates:
        print(f"Re-classified {len(demoted_to_updates)} emails from action to updates (no real action needed)")

    # Count total action items (threads + ungrouped)
    total_action_count = len(true_action_threads) + len(true_ungrouped_emails)

    # Build dual-layer structure: raw data + summary fields
    inbox_latest = {
        "generated_at": datetime.now().isoformat(),

        # What Happened: Executive summary of inbox
        "what_happened": {
            "stats": {
                "total_processed": meta.get("total_processed", 0),
                "signal_count": len(signal_emails) + len(demoted_to_updates),
                "action_count": total_action_count,
                "auto_archived": meta.get("auto_archived_count", 0)
            },
            "summary": "FILL"  # Claude writes 1-2 sentences
        },

        # What Matters: Signal items (FYI, no action needed)
        # financial = array of parsed transactions, others = text FILL fields
        "updates": {
            "items": [],  # Raw data for context
            "financial": [],  # Array of transaction objects: [{source, description, amount, type, date}, ...]
            "worth_knowing": "FILL",  # Agent summarizes newsletters and informational content worth reading
            "pointless_shit": "FILL"  # Agent roasts spam, marketing garbage, and pointless notifications
        },

        # Revisit: Threads Srini has replied to, waiting for response back
        "revisit": {
            "items": []  # [{message_id, thread_id, sender, subject, date_sent, thread_messages}, ...]
        },

        # What To Do: Action items (real replies needed)
        "action": {
            "items": []  # Each item has its own summary field + optional thread_messages array
        }
    }

    # Populate updates (SIGNAL emails + demoted action emails)
    all_update_emails = signal_emails + demoted_to_updates
    for email in all_update_emails:
        body = email.get("body", "")
        if len(body) > 500:
            body = body[:500] + "..."

        inbox_latest["updates"]["items"].append({
            "message_id": email.get("message_id", ""),
            "sender": email.get("sender", "Unknown"),
            "subject": email.get("subject", "No subject"),
            "body": body,
            "date": email.get("date", "")
        })

        # Parse financial transactions from update emails
        tx = parse_financial_transaction(email)
        if tx:
            inbox_latest["updates"]["financial"].append(tx)

    # Populate revisit section from:
    # 1. inbox_summary.json revisit category (legacy) - filtered to exclude Srini's own messages
    # 2. replied_threads (new: threads where Srini has replied, detected from sent folder)
    # Track seen thread_ids to prevent duplicates
    seen_revisit_threads = set()

    revisit_emails = inbox_data.get("revisit", [])
    for email in revisit_emails:
        # Skip Srini's own sent messages - never show in revisit
        sender = email.get("sender", "").lower()
        if SRINI_EMAIL in sender:
            continue
        # Skip if thread already seen (deduplication)
        thread_id = email.get("thread_id", "")
        if thread_id and thread_id in seen_revisit_threads:
            continue
        if thread_id:
            seen_revisit_threads.add(thread_id)
        inbox_latest["revisit"]["items"].append({
            "message_id": email.get("message_id", ""),
            "thread_id": thread_id,
            "sender": email.get("sender", "Unknown"),
            "subject": email.get("subject", "No subject"),
            "date_sent": email.get("date", "")
        })

    # Add replied threads to revisit (these are waiting for response)
    for thread_data in replied_threads:
        thread_id = thread_data["thread_id"]
        # Skip if already added from legacy revisit
        if thread_id in seen_revisit_threads:
            continue
        seen_revisit_threads.add(thread_id)
        email = thread_data["most_recent"]
        inbox_latest["revisit"]["items"].append({
            "message_id": email.get("message_id", ""),
            "thread_id": thread_id,
            "sender": email.get("sender", "Unknown"),
            "subject": email.get("subject", "No subject"),
            "date_sent": email.get("date", ""),
            "thread_messages": thread_data["thread_messages"],  # All message IDs in thread
            "message_count": thread_data["message_count"]
        })

    # Populate action items from threads (each thread = one card)
    for thread_data in true_action_threads:
        email = thread_data["most_recent"]
        body = email.get("body", "")

        item = {
            "message_id": email.get("message_id", ""),
            "thread_id": thread_data["thread_id"],
            "sender": email.get("sender", "Unknown"),
            "subject": email.get("subject", "No subject"),
            "body": body,
            "date": email.get("date", ""),
            "urgency": email.get("urgency", ""),
            "action_needed": "FILL"
        }

        # Only add thread_messages if there are multiple messages
        if thread_data["message_count"] > 1:
            item["thread_messages"] = thread_data["thread_messages"]
            item["message_count"] = thread_data["message_count"]

        inbox_latest["action"]["items"].append(item)

    # Add ungrouped emails (no thread_id) as individual action items
    for email in true_ungrouped_emails:
        body = email.get("body", "")
        inbox_latest["action"]["items"].append({
            "message_id": email.get("message_id", ""),
            "sender": email.get("sender", "Unknown"),
            "subject": email.get("subject", "No subject"),
            "body": body,
            "date": email.get("date", ""),
            "urgency": email.get("urgency", ""),
            "action_needed": "FILL"
        })

    # Write to inbox_latest.json (Claude will fill the FILL fields)
    with open(latest_file, "w") as f:
        json.dump(inbox_latest, f, indent=2)

    financial_count = len(inbox_latest["updates"]["financial"])
    revisit_count = len(inbox_latest["revisit"]["items"])

    print(f"\n=== inbox_latest.json Ready ===")
    print(f"Signal items (updates): {len(all_update_emails)}")
    print(f"Financial transactions: {financial_count}")
    print(f"Revisit items: {revisit_count} (including {len(replied_threads)} auto-detected replied threads)")
    print(f"Action items (threads needing reply): {total_action_count}")
    print(f"\nClaude fills: what_happened.summary, updates.worth_knowing, updates.pointless_shit, action.items[].action_needed")
    print(f"Pre-populated: updates.financial (array of {financial_count} transactions), revisit.items (array of {revisit_count} threads)")

    return {
        "status": "success",
        "message": f"inbox_latest.json ready with {total_action_count} action items",
        "signal_count": len(all_update_emails),
        "action_count": total_action_count,
        "financial_count": financial_count,
        "revisit_count": revisit_count,
        "replied_threads_detected": len(replied_threads),
        "demoted_count": len(demoted_to_updates),
        "path": latest_file
    }


def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'fetch_inbox':
        result = fetch_inbox(params)
    elif args.action == 'read_message':
        result = read_message(params)
    elif args.action == 'read_thread':
        result = read_thread(params)
    elif args.action == 'send':
        result = send(params)
    elif args.action == 'build_summary':
        result = build_summary(params)
    elif args.action == 'read_inbox_summary':
        result = read_inbox_summary(params)
    elif args.action == 'generate_inbox_latest_template':
        result = generate_inbox_latest_template(params)
    elif args.action == 'prepare_inbox_dashboard':
        result = prepare_inbox_dashboard(params)
    elif args.action == 'build_updates_summary':
        result = build_updates_summary(params)
    elif args.action == 'list_by_tag':
        result = list_by_tag(params)
    elif args.action == 'search':
        result = search(params)
    elif args.action == 'reply':
        result = reply(params)
    elif args.action == 'tag_message':
        result = tag_message(params)
    elif args.action == 'batch_tag_messages':
        result = batch_tag_messages(params)
    elif args.action == 'sync_archived_emails':
        result = sync_archived_emails(params)
    elif args.action == 'delete':
        result = delete(params)
    elif args.action == 'list_scheduled':
        result = list_scheduled(params)
    elif args.action == 'cancel_scheduled':
        result = cancel_scheduled(params)
    elif args.action == 'archive':
        result = archive(params)
    elif args.action == 'unarchive':
        result = unarchive(params)
    elif args.action == 'batch_unarchive':
        result = batch_unarchive(params)
    elif args.action == 'batch_delete_emails':
        result = batch_delete_emails(params)
    elif args.action == 'search_sent_messages':
        result = search_sent_messages(params)
    elif args.action == 'send_from_template':
        result = send_from_template(params)
    elif args.action == 'sync_tracking':
        result = sync_tracking(params)
    elif args.action == 'check_and_send_followups':
        result = check_and_send_followups(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()