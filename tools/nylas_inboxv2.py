import json
import os
import requests
import time
from collections import defaultdict
from system_settings import load_credential


def clean_email_content(raw_content):
    """Clean email content by stripping HTML and formatting"""
    if not raw_content:
        return "(No content)"
    
    import re
    
    content = raw_content
    
    # Remove script and style tags completely
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # Remove all HTML tags
    content = re.sub(r'<[^>]+>', '', content)
    
    # Decode HTML entities
    content = content.replace('&nbsp;', ' ')
    content = content.replace('&amp;', '&')
    content = content.replace('&lt;', '<')
    content = content.replace('&gt;', '>')
    content = content.replace('&quot;', '"')
    content = content.replace('&#39;', "'")
    content = content.replace('&apos;', "'")
    
    # Clean up whitespace
    content = re.sub(r'\s+', ' ', content)
    content = content.strip()
    
    # Remove email signatures and common footer text
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


def auto_tag_email(subject, sender, body):
    """Automatically tag emails - returns list of tags (can be multi-tagged)"""
    subject_lower = subject.lower()
    body_lower = body.lower()
    tags = []
    
    # Reply indicators - needs action/response (HIGHEST PRIORITY)
    reply_keywords = [
        'please reply', 'respond by', 'rsvp', 'confirm', 'schedule', 'meeting',
        'call me', 'let me know', 'can you', 'would you', 'could you',
        'urgent', 'asap', 'deadline', 'action required', 'please confirm',
        'interview', 'onboarding', 'booking', 'appointment', 'response needed',
        'waiting for', 'need your', 'requires your'
    ]
    
    # Update indicators - informational changes/announcements
    update_keywords = [
        'update', 'new version', 'release', 'patch', 'upgrade',
        'maintenance', 'changelog', "what's new", 'announcement',
        'launched', 'now available', 'introducing', 'rollout',
        'deprecat', 'sunset', 'end of life'
    ]
    
    # Read indicators - informational but important
    read_keywords = [
        'news', 'report', 'summary', 'status',
        'policy', 'security', 'outage', 'incident',
        'invoice', 'receipt', 'billing', 'payment', 'account',
        'statement', 'notification', 'alert'
    ]
    
    # Relax indicators - low priority/marketing
    relax_keywords = [
        'newsletter', 'unsubscribe', 'marketing', 'promotion', 'sale',
        'discount', 'offer', 'deal', 'webinar', 'event', 'podcast',
        'blog', 'article', 'tips', 'guide', 'free', 'limited time',
        'save', 'special offer'
    ]
    
    # Check for Reply first (highest priority - single tag)
    if any(keyword in subject_lower or keyword in body_lower for keyword in reply_keywords):
        return ["Reply"]
    
    # Check for Updates (can double-tag with Read)
    is_update = any(keyword in subject_lower or keyword in body_lower for keyword in update_keywords)
    
    # Check for Relax indicators
    is_relax = any(keyword in subject_lower or keyword in body_lower for keyword in relax_keywords)
    
    # Check sender patterns for relax
    relax_senders = ['noreply', 'no-reply', 'donotreply', 'marketing', 'newsletter', 'notifications']
    if any(pattern in sender.lower() for pattern in relax_senders):
        is_relax = True
    
    # Tag logic
    if is_relax:
        tags.append("Relax")
    elif is_update:
        tags.extend(["Update", "Read"])  # Double tag
    elif any(keyword in subject_lower or keyword in body_lower for keyword in read_keywords):
        tags.append("Read")
    else:
        tags.append("Read")  # Default
    
    return tags


def check_email(params):
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
        # Get body content directly from the message data
        raw_body = msg.get('body', '') or msg.get('snippet', '')
        clean_body = clean_email_content(raw_body)
        
        subject = msg.get('subject', '')
        sender = msg.get('from', [{}])[0].get('email', '')
        
        # Auto-tag the email
        auto_tags = auto_tag_email(subject, sender, clean_body)
        
        results.append({
            'subject': subject,
            'sender': sender,
            'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0))),
            'message_id': msg.get('id'),
            'body': clean_body,
            'tags': auto_tags
        })
    
    return {'status': 'success', 'data': results, 'next_cursor': response.json().get('next_cursor')}


def generate_inbox_summary(params):
    """Generate clean inbox summary JSON file"""
    check_result = check_email({})
    if check_result.get("status") != "success":
        return {"status": "error", "message": "Failed to fetch email list"}

    messages = check_result.get("data", [])
    
    # Use the correct data directory path (go up one level from tools)
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    inbox_file = os.path.join(data_dir, "inbox_summary.json")
    with open(inbox_file, "w") as f:
        json.dump(messages, f, indent=2)

    return {"status": "success", "summary_count": len(messages)}


def read_inbox_summary(params):
    """Read the inbox summary JSON file"""
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")
        
        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}
        
        with open(inbox_file, "r") as f:
            data = json.load(f)
        
        return {"status": "success", "data": data, "count": len(data)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get_inbox_data():
    """Internal utility: Load inbox summary data"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    inbox_file = os.path.join(data_dir, "inbox_summary.json")

    if not os.path.exists(inbox_file):
        return None

    with open(inbox_file, "r") as f:
        return json.load(f)


def _chunk_emails(data, chunk_size, chunk_index):
    """Internal utility: Chunk email data"""
    total_emails = len(data)
    start_idx = chunk_index * chunk_size
    end_idx = min(start_idx + chunk_size, total_emails)

    chunk_data = data[start_idx:end_idx]

    return {
        "data": chunk_data,
        "chunk_info": {
            "chunk_index": chunk_index,
            "chunk_size": chunk_size,
            "total_emails": total_emails,
            "emails_in_chunk": len(chunk_data),
            "total_chunks": (total_emails + chunk_size - 1) // chunk_size,
            "has_more_chunks": end_idx < total_emails
        }
    }


def read_inbox_summary_chunked(params):
    """Read inbox summary in chunks to prevent response size errors"""
    chunk_size = params.get("chunk_size", 10)
    chunk_index = params.get("chunk_index", 0)

    try:
        data = _get_inbox_data()
        if data is None:
            return {"status": "error", "message": "inbox_summary.json not found"}

        result = _chunk_emails(data, chunk_size, chunk_index)
        result["status"] = "success"
        return result

    except Exception as e:
        return {"status": "error", "message": str(e)}

def _render_reply_section(reply_emails):
    """Internal utility: Render Reply section of briefing"""
    if not reply_emails:
        return ""

    section = "## 🔴 REPLY REQUIRED\n\n"
    section += "**IMPORTANT: GPT must provide a one-sentence summary of what each sender wants below each email in the table.**\n\n"
    section += "| # | Sender | Subject | Message ID |\n"
    section += "|---|--------|---------|------------|\n"

    for idx, email in enumerate(reply_emails, 1):
        sender = email['sender'].split('@')[0][:20]
        subject = email['subject'][:60] if email['subject'] else "(No subject)"
        msg_id = email['message_id'][:12] + "..."
        section += f"| {idx} | {sender} | {subject} | {msg_id} |\n"

    section += f"\n*Use `reply_to_email(message_id, body)` to respond*\n\n---\n\n"
    return section


def _render_read_section(read_emails):
    """Internal utility: Render Read section of briefing"""
    if not read_emails:
        return ""

    section = "## 📘 READ - Notable Items\n\n"
    section += "**IMPORTANT: GPT must summarize what each of these emails is about in 1 sentence.**\n\n"
    max_shown = 5
    for email in read_emails[:max_shown]:
        sender = email['sender'].split('@')[0][:20]
        subject = email['subject'][:50] if email['subject'] else "(No subject)"
        section += f"- **{sender}**: {subject}\n"

    if len(read_emails) > max_shown:
        section += f"\n*...and {len(read_emails) - max_shown} more Read emails*\n"

    section += "\n---\n\n"
    return section


def _render_update_section(summary_stats):
    """Internal utility: Render Update section of briefing"""
    if summary_stats['Update'] <= 0:
        return ""

    section = f"## 🔄 UPDATES\n\n"
    section += f"**{summary_stats['Update']} product/service updates received.**\n\n"
    section += f"*Use `generate_updates_summary()` to see grouped summary of all updates*\n\n"
    section += "---\n\n"
    return section


def _render_relax_section(relax_emails):
    """Internal utility: Render Relax section of briefing"""
    if not relax_emails:
        return ""

    section = f"## 😌 RELAX - Low Priority Overview\n\n"
    section += f"**IMPORTANT: GPT must write a 2-3 sentence paragraph summarizing the themes in these {len(relax_emails)} promotional/newsletter emails.**\n\n"
    section += f"Example themes: podcast guest pitches, marketing offers, newsletters, promotional content, etc.\n\n"
    return section


def generate_briefing_chunk(params):
    """
    Generate pre-rendered briefing for a chunk of emails
    Returns formatted markdown + processing instructions for GPT
    
    RENDERING RULES:
    - Reply emails: Full table format WITH body summaries
    - Read emails: Bullet list summary (max 5 shown)
    - Update emails: Count + link to generate_updates_summary()
    - Relax emails: Brief overview paragraph
    """
    chunk_index = params.get("chunk_index", 0)
    chunk_size = 10  # Fixed at 10 - perfect for readability
    
    # Get the chunk
    chunk_result = read_inbox_summary_chunked({
        "chunk_index": chunk_index,
        "chunk_size": chunk_size
    })
    
    if chunk_result.get("status") != "success":
        return chunk_result
    
    emails = chunk_result["data"]
    chunk_info = chunk_result["chunk_info"]
    
    # Calculate summary stats across ALL emails
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    inbox_file = os.path.join(data_dir, "inbox_summary.json")
    
    with open(inbox_file, "r") as f:
        all_data = json.load(f)
    
    summary_stats = {"Reply": 0, "Read": 0, "Update": 0, "Relax": 0}
    for email in all_data:
        for tag in email.get("tags", []):
            if tag in summary_stats:
                summary_stats[tag] += 1
    
    # GROUP BY TAGS
    reply_emails = [e for e in emails if "Reply" in e.get("tags", [])]
    read_emails = [e for e in emails if "Read" in e.get("tags", []) and "Update" not in e.get("tags", [])]
    update_emails = [e for e in emails if "Update" in e.get("tags", [])]
    relax_emails = [e for e in emails if "Relax" in e.get("tags", [])]
    
    # BUILD MARKDOWN BRIEFING
    briefing = f"""# 📧 Email Intelligence Brief - Chunk {chunk_info['chunk_index'] + 1} of {chunk_info['total_chunks']}

**Inbox Status:** {chunk_info['total_emails']} total emails  
**Breakdown:** {summary_stats['Reply']} require replies | {summary_stats['Read']} need review | {summary_stats['Update']} updates | {summary_stats['Relax']} low-priority

---

"""
    
    # EXECUTIVE SUMMARY SECTION
    briefing += "## Executive Summary\n\n"
    briefing += "**IMPORTANT: GPT must generate a 2-3 paragraph executive summary here that covers:**\n"
    briefing += "- Key themes across reply-required emails (who wants what?)\n"
    briefing += "- Notable items in Read emails\n"
    briefing += "- Brief mention of Relax email themes\n\n"
    briefing += "---\n\n"
    
    # Use renderer functions for each section
    briefing += _render_reply_section(reply_emails)
    briefing += _render_read_section(read_emails)
    briefing += _render_update_section(summary_stats)
    briefing += _render_relax_section(relax_emails)
    
    # PROCESSING INSTRUCTIONS FOR GPT
    start_num = chunk_info['chunk_index'] * chunk_size + 1
    end_num = min((chunk_info['chunk_index'] + 1) * chunk_size, chunk_info['total_emails'])
    
    processing_instructions = {
        "context": f"Showing emails {start_num}-{end_num} of {chunk_info['total_emails']} total",
        "reply_count": len(reply_emails),
        "instructions_for_gpt": {
            "generate_executive_summary": True,
            "summarize_reply_emails_inline": True,
            "summarize_read_emails_inline": True,
            "summarize_relax_themes": True,
            "use_email_body_data": True,
            "format": "Replace the 'IMPORTANT: GPT must...' instructions with actual summaries based on email body content"
        },
        "priority_actions": [
            f"Reply to {e['sender'].split('@')[0]}: {e['subject'][:40]}" 
            for e in reply_emails[:3]
        ] if reply_emails else ["No urgent replies needed in this chunk"],
        "available_commands": {
            "next_chunk": f"generate_briefing_chunk(chunk_index={chunk_info['chunk_index'] + 1})" if chunk_info['has_more_chunks'] else None,
            "previous_chunk": f"generate_briefing_chunk(chunk_index={chunk_info['chunk_index'] - 1})" if chunk_info['chunk_index'] > 0 else None,
            "reply": "reply_to_email(message_id='...', body='...')",
            "batch_archive": "batch_tag_emails(message_ids=[...], tags=['Archive'])",
            "search": "search_messages(sender='...' or subject='...')",
            "view_updates": "generate_updates_summary()",
            "open_full_email": "open_message(message_id='...')"
        },
        "rendering_note": "GPT MUST generate summaries inline. All email bodies are available in reply_emails, read_emails, and relax_emails arrays.",
        "has_more_chunks": chunk_info['has_more_chunks']
    }
    
    return {
        "status": "success",
        "briefing": briefing,
        "processing_instructions": processing_instructions,
        "reply_emails": reply_emails,  # Full email data with bodies
        "read_emails": read_emails,    # Full email data with bodies
        "relax_emails": relax_emails,  # Full email data with bodies
        "chunk_info": chunk_info
    }


def generate_updates_summary(params):
    """
    Generate grouped summary of all Update emails
    Groups by sender domain/service for easier scanning
    """
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")
        
        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}
        
        with open(inbox_file, "r") as f:
            data = json.load(f)
        
        # Get all Update emails
        update_emails = [e for e in data if "Update" in e.get("tags", [])]
        
        if not update_emails:
            return {
                "status": "success",
                "summary": "No updates found.",
                "count": 0
            }
        
        # Group by sender domain
        grouped = defaultdict(list)
        for email in update_emails:
            sender = email.get('sender', '')
            domain = sender.split('@')[1] if '@' in sender else sender
            # Clean up domain (e.g., "github.com" -> "GitHub")
            service_name = domain.split('.')[0].title()
            grouped[service_name].append(email)
        
        # Build summary
        summary = f"# 🔄 Updates Summary\n\n**Total Updates:** {len(update_emails)}\n\n"
        
        for service, emails in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
            summary += f"## {service} ({len(emails)} updates)\n\n"
            for email in emails[:3]:  # Max 3 per service
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


def get_emails_by_tag(params):
    """Get emails filtered by specific tag (useful for Reply emails table)"""
    tag_filter = params.get("tag_filter")
    
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")
        
        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}
        
        with open(inbox_file, "r") as f:
            data = json.load(f)
        
        if tag_filter:
            filtered_emails = [email for email in data if tag_filter in email.get("tags", [])]
            return {"status": "success", "data": filtered_emails, "count": len(filtered_emails)}
        else:
            return {"status": "success", "data": data, "count": len(data)}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_emails_by_tag_chunked(params):
    """Get emails filtered by tag in chunks"""
    tag_filter = params.get("tag_filter")
    chunk_size = params.get("chunk_size", 10)
    chunk_index = params.get("chunk_index", 0)

    try:
        data = _get_inbox_data()
        if data is None:
            return {"status": "error", "message": "inbox_summary.json not found"}

        # Filter by tag if specified
        if tag_filter:
            filtered_data = [email for email in data if tag_filter in email.get("tags", [])]
        else:
            filtered_data = data

        result = _chunk_emails(filtered_data, chunk_size, chunk_index)
        result["status"] = "success"
        result["chunk_info"]["tag_filter"] = tag_filter
        return result

    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_messages(params):
    """Search inbox by sender, subject, or tag"""
    sender = params.get("sender")
    subject = params.get("subject")
    tag = params.get("tag")
    
    if not any([sender, subject, tag]):
        return {"status": "error", "message": "Must provide at least one search parameter: sender, subject, or tag"}
    
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")
        
        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}
        
        with open(inbox_file, "r") as f:
            data = json.load(f)
        
        results = data
        
        # Apply filters
        if sender:
            results = [e for e in results if sender.lower() in e.get("sender", "").lower()]
        
        if subject:
            results = [e for e in results if subject.lower() in e.get("subject", "").lower()]
        
        if tag:
            results = [e for e in results if tag in e.get("tags", [])]
        
        return {
            "status": "success",
            "data": results,
            "count": len(results),
            "filters": {"sender": sender, "subject": subject, "tag": tag}
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def open_message(params):
    """Get single message with cleaned content"""
    message_id = params.get("message_id")
    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    # Get the raw message
    url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {"status": "error", "message": response.text}

    msg_data = response.json()
    
    # Get raw content and clean it ourselves
    raw_body = (
        msg_data.get("body_plain") or
        msg_data.get("body") or
        msg_data.get("snippet") or
        ""
    )
    
    body = clean_email_content(raw_body)

    return {
        "status": "success",
        "subject": msg_data.get('subject', ''),
        "sender": msg_data.get('from', [{}])[0].get('email', ''),
        "date": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg_data.get('date', 0))),
        "message_id": message_id,
        "body": body
    }

def send_email(params):
    """Send beautifully formatted email with automatic styling"""
    to = params.get("to")
    subject = params.get("subject")
    body = params.get("body")
    
    if not all([to, subject, body]):
        return {"status": "error", "message": "Missing required parameters: to, subject, body"}
    
    import re
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/send'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}

    # Convert markdown-style formatting to HTML
    formatted_body = body
    
    # Convert **bold** to <strong>
    formatted_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', formatted_body)
    
    # Convert bullet points (- item or * item) to proper list items
    lines = formatted_body.split('\n')
    processed_lines = []
    in_list = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check if line is a bullet point
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                processed_lines.append('<ul style="margin: 10px 0; padding-left: 20px;">')
                in_list = True
            # Remove the bullet marker and wrap in <li>
            item_text = stripped[2:]
            processed_lines.append(f'<li style="margin: 5px 0;">{item_text}</li>')
        else:
            # If we were in a list, close it
            if in_list:
                processed_lines.append('</ul>')
                in_list = False
            
            # Regular line - wrap in paragraph if not empty
            if stripped:
                processed_lines.append(f'<p style="margin: 10px 0;">{line}</p>')
            else:
                processed_lines.append('<br>')
    
    # Close list if still open
    if in_list:
        processed_lines.append('</ul>')
    
    formatted_body = '\n'.join(processed_lines)
    
    # Convert URLs to clickable links
    formatted_body = re.sub(
        r'(https?://[^\s<>"]+)',
        r'<a href="\1" style="color: #1a73e8; text-decoration: none;">\1</a>',
        formatted_body
    )

    # Build clean, professional HTML email
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

    response = requests.post(url, headers=headers, json=payload)
    
    return {
        'status': 'success' if response.status_code == 200 else 'error',
        'data': response.json() if response.status_code == 200 else response.text,
        'message': 'Email sent successfully' if response.status_code == 200 else 'Failed to send email'
    }


def reply_to_email(params):
    """Reply to an email with proper threading"""
    message_id = params.get("message_id")
    body = params.get("body")
    
    if not message_id or not body:
        return {"status": "error", "message": "Missing message_id or body parameters"}
    
    # First, get the original message to get sender and subject
    msg_result = open_message({"message_id": message_id})
    if msg_result.get("status") != "success":
        return {"status": "error", "message": "Failed to fetch original message"}
    
    original_sender = msg_result.get("sender")
    original_subject = msg_result.get("subject")
    
    # Add "Re:" if not already there
    if not original_subject.startswith("Re:"):
        reply_subject = f"Re: {original_subject}"
    else:
        reply_subject = original_subject
    
    import markdown2
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/send'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}

    # Convert markdown to HTML
    html_body = markdown2.markdown(body.strip())

    payload = {
        'to': [{'email': original_sender}],
        'subject': reply_subject,
        'body': html_body,
        'reply_to_message_id': message_id,  # This creates threading
        'content_type': 'text/html'
    }

    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        # After successful reply, auto-tag as "Replied" and "Archive"
        tag_result = tag_inbox_entry({
            "message_id": message_id,
            "tags": ["Replied", "Archive"]
        })
        
        return {
            'status': 'success',
            'message': 'Reply sent and email archived',
            'data': response.json(),
            'tag_result': tag_result
        }
    else:
        return {
            'status': 'error',
            'message': response.text
        }


def delete_email(params):
    """Delete an email permanently"""
    message_id = params.get("message_id")
    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    response = requests.delete(url, headers=headers)
    
    return {
        "status": "success" if response.status_code == 200 else "error",
        "message": "Email deleted" if response.status_code == 200 else response.text
    }

def archive_email(params):
    """Archive an email to the Unmistakable Archive folder and remove from INBOX"""
    message_id = params.get("message_id")
    folder_id = params.get("folder_id", "Label_4287")
    
    if not message_id:
        return {"status": "error", "message": "Missing message_id parameter"}
    
    creds = load_credential("nylas_inbox")
    GRANT_ID = creds['grant_id']
    ACCESS_TOKEN = creds['access_token']

    url = f"https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # For Gmail: Add to archive folder AND remove from INBOX
    payload = {
        "folders": [folder_id],
        "remove_folders": ["INBOX"]
    }

    response = requests.put(url, headers=headers, json=payload)
    
    return {
        "status": "success" if response.status_code == 200 else "error",
        "message": "Email archived and removed from inbox" if response.status_code == 200 else response.text,
        "folder_used": folder_id
    }


def batch_delete_emails(params):
    """Delete multiple emails"""
    message_ids = params.get("message_ids", [])
    if not message_ids:
        return {"status": "error", "message": "Missing message_ids parameter"}
    
    results = []
    for msg_id in message_ids:
        result = delete_email({"message_id": msg_id})
        results.append({"id": msg_id, "status": result["status"]})
    
    return {"status": "complete", "results": results}


def sync_archived_emails(params):
    """Automatically archive emails tagged with 'Archive' and remove from inbox summary"""
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")
        
        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}
        
        with open(inbox_file, "r") as f:
            data = json.load(f)
        
        archived_count = 0
        remaining_emails = []
        
        for entry in data:
            tags = entry.get("tags", [])
            if "Archive" in tags:
                # Archive this email via API
                message_id = entry.get("message_id")
                if message_id:
                    result = archive_email({"message_id": message_id})
                    if result.get("status") == "success":
                        archived_count += 1
                        # Don't add to remaining_emails - it gets removed from view
                    else:
                        # If archive failed, keep in list but note the error
                        entry["archive_error"] = result.get("message", "Archive failed")
                        remaining_emails.append(entry)
                else:
                    remaining_emails.append(entry)
            else:
                # Keep emails without Archive tag
                remaining_emails.append(entry)
        
        # Update the inbox summary with only non-archived emails
        with open(inbox_file, "w") as f:
            json.dump(remaining_emails, f, indent=2)
        
        return {
            "status": "success", 
            "archived_count": archived_count,
            "remaining_count": len(remaining_emails),
            "message": f"Archived {archived_count} emails, {len(remaining_emails)} remaining in inbox"
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def tag_inbox_entry(params):
    """Add tags to a specific inbox entry and auto-sync if Archive tag is added"""
    message_id = params.get("message_id")
    tags = params.get("tags")
    
    if not message_id or not tags:
        return {"status": "error", "message": "Missing message_id or tags parameters"}
    
    try:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        inbox_file = os.path.join(data_dir, "inbox_summary.json")
        
        if not os.path.exists(inbox_file):
            return {"status": "error", "message": "inbox_summary.json not found"}
        
        with open(inbox_file, "r") as f:
            data = json.load(f)
        
        # Find the message and add tags
        found = False
        archive_triggered = False
        
        for entry in data:
            if entry.get("message_id") == message_id:
                if "tags" not in entry:
                    entry["tags"] = []
                
                # Add new tags (avoid duplicates)
                if isinstance(tags, str):
                    tags = [tags]
                
                for tag in tags:
                    if tag not in entry["tags"]:
                        entry["tags"].append(tag)
                        if tag == "Archive":
                            archive_triggered = True
                
                found = True
                break
        
        if not found:
            return {"status": "error", "message": f"Message ID {message_id} not found"}
        
        # Save back to file
        with open(inbox_file, "w") as f:
            json.dump(data, f, indent=2)
        
        # Auto-trigger sync if Archive tag was added
        if archive_triggered:
            sync_result = sync_archived_emails({})
            return {
                "status": "success", 
                "message": "Tags added and auto-sync triggered",
                "sync_result": sync_result
            }
        else:
            return {"status": "success", "message": "Tags added successfully"}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}


def batch_tag_inbox_entries(params):
    """Batch tag multiple emails with the same tags"""
    message_ids = params.get("message_ids")
    tags = params.get("tags", ["Archive"])

    if not message_ids:
        return {"status": "error", "message": "Missing 'message_ids' parameter"}

    # Convert single ID to list
    if isinstance(message_ids, str):
        message_ids = [message_ids]

    results = []
    for msg_id in message_ids:
        result = tag_inbox_entry({"message_id": msg_id, "tags": tags})
        results.append({"id": msg_id, "status": result.get("status")})

    return {"status": "complete", "results": results}


def generate_daily_brief(params):
    """
    Generate consolidated inbox briefing using existing tag logic.
    No external API calls - uses local processing with auto-tagging.
    """
    from datetime import datetime

    # Get inbox data
    data = _get_inbox_data()
    if data is None:
        return {
            "status": "error",
            "message": "❌ inbox_summary.json not found. Run generate_inbox_summary first."
        }

    if not data:
        return {
            "status": "success",
            "message": "✅ Inbox is empty - no briefing needed",
            "total_emails": 0
        }

    # Calculate summary stats
    summary_stats = {"Reply": 0, "Read": 0, "Update": 0, "Relax": 0}
    for email in data:
        for tag in email.get("tags", []):
            if tag in summary_stats:
                summary_stats[tag] += 1

    # Group emails by tags
    reply_emails = [e for e in data if "Reply" in e.get("tags", [])]
    read_emails = [e for e in data if "Read" in e.get("tags", []) and "Update" not in e.get("tags", [])]
    update_emails = [e for e in data if "Update" in e.get("tags", [])]
    relax_emails = [e for e in data if "Relax" in e.get("tags", [])]

    # Build briefing using renderer functions
    today = datetime.now().strftime("%Y-%m-%d")
    briefing = f"""# 📧 Daily Inbox Brief - {today}

**Total Emails:** {len(data)}
**Breakdown:** {summary_stats['Reply']} require replies | {summary_stats['Read']} need review | {summary_stats['Update']} updates | {summary_stats['Relax']} low-priority

---

"""

    briefing += _render_reply_section(reply_emails)
    briefing += _render_read_section(read_emails)
    briefing += _render_update_section(summary_stats)
    briefing += _render_relax_section(relax_emails)

    # Save briefing to file
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    brief_data = {
        "date": today,
        "total_emails": len(data),
        "briefing": briefing,
        "emails_by_tag": summary_stats,
        "generated_at": datetime.now().isoformat()
    }

    brief_file = os.path.join(data_dir, "daily_inbox_brief.json")

    try:
        with open(brief_file, 'w', encoding='utf-8') as f:
            json.dump(brief_data, f, indent=2)
    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to save briefing: {str(e)}"
        }

    return {
        "status": "success",
        "message": f"✅ Inbox briefing generated for {len(data)} emails",
        "briefing_file": "data/daily_inbox_brief.json",
        "total_emails": len(data),
        "breakdown": summary_stats
    }


def trigger_claude_inbox_briefing(params):
    """
    Assign Claude task to generate full inbox briefing
    Can be called manually or via automation
    """
    from datetime import datetime
    import subprocess

    # Import claude_assistant actions locally to avoid circular imports
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    today = datetime.now().strftime("%Y-%m-%d")
    task_id = f"inbox_briefing_{today}"

    # Create output directory if it doesn't exist
    briefings_dir = os.path.join(data_dir, "inbox_briefs")
    os.makedirs(briefings_dir, exist_ok=True)

    output_file = os.path.join(briefings_dir, f"{today}.md")

    # Assign task to Claude via execution_hub
    assign_params = {
        "tool_name": "claude_assistant",
        "action": "assign_task",
        "params": {
            "task_id": task_id,
            "description": (
                "Generate comprehensive inbox briefing. "
                "Read inbox_summary.json, process all chunks, "
                "create executive summary with priority replies, "
                "notable items, and theme analysis. "
                f"Save output to {output_file}"
            ),
            "priority": "high",
            "context": {
                "date": today,
                "output_file": output_file
            }
        }
    }

    try:
        # Call execution_hub to assign the task
        result = subprocess.run(
            ["python3", "execution_hub.py", "execute_task", "--params", json.dumps(assign_params)],
            cwd=os.path.dirname(data_dir),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to assign task: {result.stderr}"
            }

        return {
            "status": "started",
            "task_id": task_id,
            "message": "Claude briefing task assigned. Task will be processed when Claude checks queue.",
            "output_file": output_file
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to trigger briefing: {str(e)}"
        }


def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'check_email':
        result = check_email(params)
    elif args.action == 'open_message':
        result = open_message(params)
    elif args.action == 'send_email':
        result = send_email(params)
    elif args.action == 'generate_inbox_summary':
        result = generate_inbox_summary(params)
    elif args.action == 'read_inbox_summary':
        result = read_inbox_summary(params)
    elif args.action == 'read_inbox_summary_chunked':
        result = read_inbox_summary_chunked(params)
    elif args.action == 'generate_briefing_chunk':
        result = generate_briefing_chunk(params)
    elif args.action == 'generate_updates_summary':
        result = generate_updates_summary(params)
    elif args.action == 'get_emails_by_tag':
        result = get_emails_by_tag(params)
    elif args.action == 'get_emails_by_tag_chunked':
        result = get_emails_by_tag_chunked(params)
    elif args.action == 'search_messages':
        result = search_messages(params)
    elif args.action == 'reply_to_email':
        result = reply_to_email(params)
    elif args.action == 'tag_inbox_entry':
        result = tag_inbox_entry(params)
    elif args.action == 'batch_tag_inbox_entries':
        result = batch_tag_inbox_entries(params)
    elif args.action == 'sync_archived_emails':
        result = sync_archived_emails(params)
    elif args.action == 'delete_email':
        result = delete_email(params)
    elif args.action == 'archive_email':
        result = archive_email(params)
    elif args.action == 'batch_delete_emails':
        result = batch_delete_emails(params)
    elif args.action == 'generate_daily_brief':
        result = generate_daily_brief(params)
    elif args.action == 'trigger_claude_inbox_briefing':
        result = trigger_claude_inbox_briefing(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()