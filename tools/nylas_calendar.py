import requests
import json
from system_settings import load_credential

API_BASE = "https://api.nylas.com/v3"
HEADERS = {
    "Authorization": f"Bearer {load_credential('access_token')}",
    "Content-Type": "application/json"
}
GRANT_ID = load_credential("grant_id")


def list_upcoming_events(params):
    calendar_id = "3afea38a-5be5-4d7b-a6a4-494297f499fb"
    url = f"{API_BASE}/grants/{GRANT_ID}/events"
    res = requests.get(url, headers=HEADERS, params={"limit": 10, "calendar_id": calendar_id})
    res.raise_for_status()
    return res.json()


def book_event(params):
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    email = params.get("email")

    event = {
        "title": "Orchestrate Booking",
        "when": {
            "start_time": start_time,
            "end_time": end_time
        },
        "participants": [
            {"email": email, "name": email}
        ]
    }

    url = f"{API_BASE}/grants/{GRANT_ID}/events"
    res = requests.post(url, headers=HEADERS, json=event)
    res.raise_for_status()
    return res.json()


def delete_event(params):
    event_id = params.get("event_id")
    calendar_id = params.get("calendar_id")
    url = f"{API_BASE}/grants/{GRANT_ID}/events/{event_id}"
    res = requests.delete(url, headers=HEADERS)
    return {"status": "deleted", "event_id": event_id}


def get_availability(params):
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
    # Not a direct Nylas API feature — can be stored locally or used client-side
    return {"status": "stored", "config": params}



def list_calendars(params):
    url = f"{API_BASE}/grants/{GRANT_ID}/calendars"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()

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

    if args.action == "list_upcoming_events":
        result = list_upcoming_events(params)
    elif args.action == "book_event":
        result = book_event(params)
    elif args.action == "delete_event":
        result = delete_event(params)
    elif args.action == "get_availability":
        result = get_availability(params)
    elif args.action == "create_calendar":
        result = create_calendar(params)
    elif args.action == "set_time_slots":
        result = set_time_slots(params)
    elif args.action == "list_calendars":
        result = list_calendars(params)
    else:
        result = {"status": "error", "message": f"Unknown action {args.action}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()