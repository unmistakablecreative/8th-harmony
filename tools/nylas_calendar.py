import requests
import json
import argparse
import sys
import datetime
import pytz
GRANT_ID = '8602b3fc-cee8-45da-af8a-1c9544cfb9ac'
API_KEY = (
    'nyk_v0_obWM28jd2qixbOickYOnLxyp97b2gqPYmNrqdo98HeHZZCroo1lsEMSyruk9767X')
EMAIL = 'srinirao'
CONFIG_ID = '92c23103-ea9b-44ad-ab30-f1ae4d434272'
BASE_URL = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}'


def send_request(method, url, payload=None):
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type':
        'application/json', 'Accept': 'application/json'}
    try:
        response = requests.request(method, url, headers=headers, json=payload)
        return {'status_code': response.status_code, 'response': response.
            json() if response.content else {}}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def create_calendar(name, description, location, timezone):
    return send_request('POST', f'{BASE_URL}/calendars', {'name': name,
        'description': description, 'location': location, 'timezone': timezone}
        )


def get_availability():
    tz = pytz.timezone('America/Los_Angeles')
    now = datetime.datetime.now(tz).replace(hour=0, minute=0, second=0,
        microsecond=0)
    start_time = int(now.astimezone(pytz.utc).timestamp())
    end_time = int((now + datetime.timedelta(days=14)).astimezone(pytz.utc)
        .timestamp())
    res = send_request('POST',
        'https://api.us.nylas.com/v3/calendars/availability', {'start_time':
        start_time, 'end_time': end_time, 'interval_minutes': 30,
        'duration_minutes': 30, 'participants': [{'email': 'srinirao',
        'calendar_ids': ['primary'], 'open_hours': [{'days': [1, 2, 3, 4, 5
        ], 'timezone': 'America/Los_Angeles', 'start': '12:00', 'end':
        '16:00'}]}]})
    if res['status_code'] != 200:
        return res
    slots = res['response'].get('data', {}).get('time_slots', [])
    readable = []
    for slot in slots:
        start = datetime.datetime.fromtimestamp(slot['start_time'], tz
            ).strftime('%a %b %d — %I:%M %p')
        end = datetime.datetime.fromtimestamp(slot['end_time'], tz).strftime(
            '%I:%M %p')
        readable.append(f'🟢 {start} – {end} PST')
    return {'status_code': 200, 'slots': readable}
    return send_request('POST', f'{BASE_URL}/events', {'title': title,
        'location': location, 'description': description, 'start_time':
        start_time, 'end_time': end_time, 'participants': [{'email':
        participant_email}]})

def book_event(start_time, end_time, email):
    return send_request('POST', f'{BASE_URL}/events?calendar_id=primary', {
        'title': 'Meeting with Srini', 'location': 'Online', 'description':
        '', 'participants': [{'email': email}], 'when': {'start_time':
        start_time, 'end_time': end_time}})


def delete_event(event_id, calendar_id='primary'):
    url = f'{BASE_URL}/events/{event_id}?calendar_id={calendar_id}'
    return send_request('DELETE', url)



    res = send_request('GET', f'{BASE_URL}/events?calendar_id=primary')
    if res['status_code'] != 200:
        return res
    tz = pytz.timezone('America/Los_Angeles')
    events = res['response'].get('data', [])
    readable = []
    for e in events:
        start = datetime.datetime.fromtimestamp(e['when']['start_time'], tz
            ).strftime('%a %b %d — %I:%M %p')
        end = datetime.datetime.fromtimestamp(e['when']['end_time'], tz
            ).strftime('%I:%M %p')
        title = e.get('title', 'Untitled')
        emails = ', '.join(p['email'] for p in e.get('participants', []))
        readable.append(f'📆 {title} — {start} – {end} PST ({emails})')
    return {'status_code': 200, 'events': readable}

def list_upcoming_events():
    res = send_request("GET", f"{BASE_URL}/events?calendar_id=primary")
    if res["status_code"] != 200:
        return res

    tz = pytz.timezone("America/Los_Angeles")
    events = res["response"].get("data", [])
    
    readable = []
    structured = []

    for e in events:
        start_dt = datetime.datetime.fromtimestamp(e["when"]["start_time"], tz)
        end_dt = datetime.datetime.fromtimestamp(e["when"]["end_time"], tz)

        start = start_dt.strftime("%a %b %d — %I:%M %p")
        end = end_dt.strftime("%I:%M %p")

        title = e.get("title", "Untitled")
        emails = ", ".join(p["email"] for p in e.get("participants", []))

        readable.append(f"📆 {title} — {start} – {end} PST ({emails})")
        
        structured.append({
            "event_id": e.get("id"),
            "calendar_id": e.get("calendar_id", "primary"),
            "title": title,
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "emails": emails
        })

    return {
        "status_code": 200,
        "events": readable,
        "structured_events": structured
    }



def set_time_slots(duration_minutes, interval_minutes,
    available_days_in_future, min_booking_notice, available_times):
    url = f'{BASE_URL}/scheduling/configurations/{CONFIG_ID}'
    payload = {'participants': [{'email': EMAIL, 'is_organizer': True,
        'availability': {'calendar_ids': ['primary'], 'open_hours':
        available_times}, 'booking': {'calendar_id': 'primary'}}],
        'availability': {'duration_minutes': duration_minutes,
        'interval_minutes': interval_minutes}, 'scheduler': {
        'available_days_in_future': available_days_in_future,
        'min_booking_notice': min_booking_notice}}
    return send_request('PUT', url, payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', help=
        'create_calendar|get_availability|book_event|list_upcoming_events|set_time_slots|delete_event'
        )
    parser.add_argument('--params', help='JSON string of parameters',
        required=False)
    args = parser.parse_args()
    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError:
        print(json.dumps({'status': 'error', 'message':
            'Invalid JSON in --params'}))
        sys.exit(1)
    if args.action == 'create_calendar':
        result = create_calendar(**params)
    elif args.action == 'get_availability':
        result = get_availability()
    elif args.action == 'book_event':
        result = book_event(**params)
    elif args.action == 'list_upcoming_events':
        result = list_upcoming_events()
    elif args.action == 'set_time_slots':
        result = set_time_slots(**params)
    elif args.action == 'delete_event':
        result = delete_event(**params)
    else:
        result = {'status': 'error', 'message':
            f"Unknown action '{args.action}'"}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
