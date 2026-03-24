import requests
import json
from system_settings import load_credential

API_BASE = "https://api.nylas.com/v3"
HEADERS = {
    "Authorization": f"Bearer {load_credential('access_token')}",
    "Content-Type": "application/json"
}
GRANT_ID = load_credential("grant_id")


def extract_event_minimal(event):
    """Extract only essential fields from event object including event ID."""
    when = event.get("when", {})
    participants = event.get("participants", [])

    return {
        "event_id": event.get("id"),
        "title": event.get("title"),
        "start_time": when.get("start_time"),
        "end_time": when.get("end_time"),
        "participants": [p.get("email") for p in participants if p.get("email")]
    }


def list_events(params):
    calendar_id = "srini@unmistakablemedia.com"
    url = f"{API_BASE}/grants/{GRANT_ID}/events"
    res = requests.get(url, headers=HEADERS, params={"limit": 50, "calendar_id": calendar_id})
    res.raise_for_status()
    data = res.json()
    events = data.get("data", [])
    return {"data": [extract_event_minimal(e) for e in events]}


def book_event(params):
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    email = params.get("email")
    calendar_id = params.get("calendar_id", "srini@unmistakablemedia.com")

    meet_link = "https://meet.google.com/vhh-otiz-gxp"

    event = {
        "title": params.get("title", "OrchestrateOS Meeting"),
        "description": f"Join via Google Meet: {meet_link}",
        "location": meet_link,
        "when": {
            "start_time": start_time,
            "end_time": end_time
        },
        "participants": [
            {"email": email, "name": email}
        ]
    }

    url = f"{API_BASE}/grants/{GRANT_ID}/events?calendar_id={calendar_id}"
    res = requests.post(url, headers=HEADERS, json=event)
    res.raise_for_status()
    data = res.json()
    created_event = data.get("data", data)
    
    try:
        sync_to_dashboard({})
    except Exception as e:
        print(f"Warning: Failed to sync to dashboard: {e}")
    
    return {"data": extract_event_minimal(created_event)}


def delete_event(params):
    event_id = params.get("event_id")
    calendar_id = params.get("calendar_id", "srini@unmistakablemedia.com")
    url = f"{API_BASE}/grants/{GRANT_ID}/events/{event_id}?calendar_id={calendar_id}"
    res = requests.delete(url, headers=HEADERS)
    res.raise_for_status()
    
    try:
        sync_to_dashboard({})
    except Exception as e:
        print(f"Warning: Failed to sync to dashboard: {e}")
    
    return {"status": "deleted", "event_id": event_id}


def read_availability(params):
    url = f"{API_BASE}/calendars/availability"
    res = requests.post(url, headers=HEADERS, json=params)
    res.raise_for_status()
    return res.json()


def create_calendar(params):
    url = f"{API_BASE}/grants/{GRANT_ID}/calendars"
    res = requests.post(url, headers=HEADERS, json=params)
    res.raise_for_status()
    return res.json()


def set_time_slots(params):
    return {"status": "stored", "config": params}


def list_calendars(params):
    url = f"{API_BASE}/grants/{GRANT_ID}/calendars"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()


def list_scheduler_configs(params):
    url = f"{API_BASE}/grants/{GRANT_ID}/scheduling/configurations"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()


def read_scheduler_config(params):
    config_id = params.get("config_id")
    url = f"{API_BASE}/grants/{GRANT_ID}/scheduling/configurations/{config_id}"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()


def update_scheduler_config(params):
    config_id = params.get("config_id")
    updates = params.get("updates", {})

    url = f"{API_BASE}/grants/{GRANT_ID}/scheduling/configurations/{config_id}"
    res = requests.patch(url, headers=HEADERS, json=updates)
    res.raise_for_status()
    return res.json()


def create_scheduler_config(params):
    """
    Create a new Nylas Scheduling Page.

    Required params: slug, title, duration_minutes
    Optional: days (list of ints, default [1,2,3]), start (default '10:00'), end (default '12:00'),
              timezone (default 'America/Los_Angeles'), description, available_days_in_future (default 30),
              buffer_before (default 0), buffer_after (default 0), interval_minutes (default same as duration)

    Returns: {"status": "success", "config_id": "...", "slug": "...", "booking_url": "..."}

    Note: CLIENT_ID for booking URL not yet in credentials.json. URL pattern is:
    https://book.nylas.com/us/{CLIENT_ID}/{SLUG}
    """
    from system_settings import load_credential

    # Required params
    slug = params.get("slug")
    title = params.get("title")
    duration_minutes = params.get("duration_minutes")

    if not all([slug, title, duration_minutes]):
        return {"status": "error", "message": "Missing required params: slug, title, duration_minutes"}

    # Optional params with defaults
    days = params.get("days", [1, 2, 3])
    start = params.get("start", "10:00")
    end = params.get("end", "12:00")
    timezone = params.get("timezone", "America/Los_Angeles")
    description = params.get("description", "")
    available_days_in_future = params.get("available_days_in_future", 30)
    buffer_before = params.get("buffer_before", 0)
    buffer_after = params.get("buffer_after", 0)
    interval_minutes = params.get("interval_minutes", duration_minutes)

    # Build request body per Nylas v3 Scheduler API
    body = {
        "slug": slug,
        "participants": [{
            "name": "Srini Rao",
            "email": "srini@unmistakablemedia.com",
            "is_organizer": True,
            "availability": {
                "calendar_ids": ["primary"],
                "open_hours": [{
                    "days": days,
                    "timezone": timezone,
                    "start": start,
                    "end": end
                }]
            },
            "booking": {
                "calendar_id": "primary"
            },
            "timezone": timezone
        }],
        "requires_session_auth": False,
        "availability": {
            "duration_minutes": duration_minutes,
            "interval_minutes": interval_minutes,
            "availability_rules": {
                "availability_method": "collective",
                "buffer": {"before": buffer_before, "after": buffer_after},
                "default_open_hours": [{
                    "days": [1, 2, 3, 4, 5],
                    "timezone": timezone,
                    "start": "09:00",
                    "end": "17:00"
                }]
            }
        },
        "event_booking": {
            "title": title,
            "timezone": timezone,
            "description": description,
            "booking_type": "booking",
            "disable_emails": False
        },
        "scheduler": {
            "available_days_in_future": available_days_in_future,
            "min_cancellation_notice": 0,
            "min_booking_notice": 60,
            "rescheduling_url": "https://book.nylas.com/us/reschedule/:booking_ref",
            "cancellation_url": "https://book.nylas.com/us/cancel/:booking_ref",
            "hide_rescheduling_options": False,
            "hide_cancellation_options": False,
            "hide_additional_guests": False
        }
    }

    url = f"{API_BASE}/grants/{GRANT_ID}/scheduling/configurations"
    res = requests.post(url, headers=HEADERS, json=body)
    res.raise_for_status()
    data = res.json()

    config_data = data.get("data", data)
    config_id = config_data.get("id")

    # Try to get client_id from credentials for booking URL
    try:
        creds = load_credential("nylas_calendar")
        client_id = creds.get("client_id", "YOUR_CLIENT_ID")
    except:
        client_id = "YOUR_CLIENT_ID"

    booking_url = f"https://book.nylas.com/us/{client_id}/{slug}"

    return {
        "status": "success",
        "config_id": config_id,
        "slug": slug,
        "booking_url": booking_url,
        "note": "Add 'client_id' to nylas_calendar credentials for accurate booking URL" if client_id == "YOUR_CLIENT_ID" else None
    }


def add_meet_link_to_scheduler(params):
    config_id = params.get("config_id")
    meet_link = "https://meet.google.com/vhh-otiz-gxp"
    
    url = f"{API_BASE}/grants/{GRANT_ID}/scheduling/configurations/{config_id}"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    current_config = res.json()
    
    updates = {
        "event_booking": {
            "title": current_config.get("data", {}).get("event_booking", {}).get("title", "OrchestrateOS Meeting"),
            "description": f"Join via Google Meet: {meet_link}"
        }
    }
    
    res = requests.patch(url, headers=HEADERS, json=updates)
    res.raise_for_status()
    
    return {"status": "success", "config_id": config_id, "meet_link": meet_link}


def sync_to_dashboard(params):
    import os
    from datetime import datetime
    import time

    calendar_id = "srini@unmistakablemedia.com"
    url = f"{API_BASE}/grants/{GRANT_ID}/events"
    # Query events for next 90 days to catch all upcoming events
    query_params = {
        "limit": 100,
        "calendar_id": calendar_id,
        "start": int(time.time()),
        "end": int(time.time()) + (90 * 86400)
    }
    res = requests.get(url, headers=HEADERS, params=query_params)
    res.raise_for_status()
    data = res.json()
    events = data.get("data", [])

    dashboard_events = []
    for e in events:
        # Skip "Open Product Call" events
        if e.get("title") == "Open Product Call":
            continue
            
        when = e.get("when", {})
        participants = e.get("participants", [])
        conferencing = e.get("conferencing", {})

        meeting_with = "No participants"
        for p in participants:
            email = p.get("email", "")
            if email and "srinirao" not in email.lower() and "unmistakablemedia" not in email.lower():
                meeting_with = p.get("name", email)
                break

        contact_email = ""
        for p in participants:
            email = p.get("email", "")
            if email and "srinirao" not in email.lower() and "unmistakablemedia" not in email.lower():
                contact_email = email
                break

        # Extract Google Meet link
        meet_url = conferencing.get("details", {}).get("url", "")

        dashboard_events.append({
            "title": e.get("title", "Untitled"),
            "meeting_with": meeting_with,
            "contact_email": contact_email,
            "start_time": when.get("start_time"),
            "end_time": when.get("end_time"),
            "event_id": e.get("id"),
            "meet_url": meet_url
        })

    dashboard_events.sort(key=lambda x: x.get("start_time") or 0)

    output = {
        "last_synced": datetime.now().isoformat(),
        "events": dashboard_events
    }

    output_path = os.path.join(os.path.dirname(__file__), "..", "semantic_memory", "calendar_events.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    return {"status": "success", "events_synced": len(dashboard_events), "path": output_path}

def main():
    import argparse
    import json
    from system_settings import load_credential

    creds = load_credential("nylas_calendar")
    global HEADERS, GRANT_ID, API_BASE
    API_BASE = "https://api.us.nylas.com/v3"
    HEADERS = {
        "Authorization": f"Bearer {creds['access_token']}",
        "Content-Type": "application/json"
    }
    GRANT_ID = creds["grant_id"]

    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params")
    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}

    if args.action == "list_events":
        result = list_events(params)
    elif args.action == "book_event":
        result = book_event(params)
    elif args.action == "delete_event":
        result = delete_event(params)
    elif args.action == "read_availability":
        result = read_availability(params)
    elif args.action == "create_calendar":
        result = create_calendar(params)
    elif args.action == "set_time_slots":
        result = set_time_slots(params)
    elif args.action == "list_calendars":
        result = list_calendars(params)
    elif args.action == "sync_to_dashboard":
        result = sync_to_dashboard(params)
    elif args.action == "list_scheduler_configs":
        result = list_scheduler_configs(params)
    elif args.action == "read_scheduler_config":
        result = read_scheduler_config(params)
    elif args.action == "update_scheduler_config":
        result = update_scheduler_config(params)
    elif args.action == "create_scheduler_config":
        result = create_scheduler_config(params)
    elif args.action == "add_meet_link_to_scheduler":
        result = add_meet_link_to_scheduler(params)
    else:
        result = {"status": "error", "message": f"Unknown action {args.action}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
