import os
import sys
import json
import requests
from datetime import datetime

# ✅ Make `tools` importable when run as a script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from tools.podcast_manager import resolve_index

# === CONFIG ===
API_KEY = "3Ldi8Kwk66Dx65Q0lFL"
SHOW_ID = "6202ac9f5668e761825372c3"
AUDIO_DIR = "audio"
API_ENDPOINT = f"https://open.acast.com/rest/shows/{SHOW_ID}/episodes"
HEADERS = {"x-api-key": API_KEY}

# === INDEX I/O ===
def load_index():
    path = resolve_index()
    with open(path, "r") as f:
        return json.load(f)

def save_index(index):
    path = resolve_index()
    with open(path, "w") as f:
        json.dump(index, f, indent=2)

# === STATUS CHECKS ===
def should_upload(entry):
    """Check if entry should be uploaded (as draft)"""
    return entry.get("status") == "scheduled" and "scheduled_publish_date" in entry

def should_publish(entry):
    """Check if entry should be published (draft -> published)"""
    if entry.get("status") != "uploaded" or "scheduled_publish_date" not in entry:
        return False
    
    # Check if the scheduled date has arrived
    scheduled_date = entry["scheduled_publish_date"]  # "2025-09-10"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    return scheduled_date <= today

# === MARKER FORMATTING ===
def extract_markers_for_acast(markers):
    """Format markers as string per Acast support response"""
    if not markers:
        return None
    
    # Extract timestamp from our format
    for marker in markers:
        if isinstance(marker, str) and "," in marker:
            marker_type, timestamp = marker.split(",", 1)
            timestamp = timestamp.strip()
            
            if marker_type.strip().lower() == "midroll":
                # Use Acast's expected string format: "preroll,timestamp,postroll"
                return f"preroll,{timestamp},postroll"
    
    return None

# === UPDATE EPISODE ON ACAST ===
def update_episode_on_acast(entry_key, episode_id, changed_fields):
    """
    Updates an existing episode on Acast via PATCH.

    Args:
        entry_key: Episode key from podcast_index.json
        episode_id: Acast episode ID (_id)
        changed_fields: Dict of fields that changed

    Returns:
        True if successful, False otherwise
    """
    from datetime import timedelta

    if not episode_id:
        print(f"❌ No Acast episode ID for {entry_key}")
        return False

    update_url = f"{API_ENDPOINT}/{episode_id}"
    payload = {}

    # Convert changed fields to Acast format
    if "title" in changed_fields:
        payload["title"] = changed_fields["title"]

    if "summary" in changed_fields:
        payload["summary"] = changed_fields["summary"]

    if "alias" in changed_fields:
        payload["alias"] = changed_fields["alias"]

    if "episodeNumber" in changed_fields:
        payload["episodeNumber"] = str(changed_fields["episodeNumber"])

    if "markers" in changed_fields:
        markers = changed_fields["markers"]
        marker_string = extract_markers_for_acast(markers)
        if marker_string:
            payload["markers"] = marker_string

    if "scheduled_publish_date" in changed_fields:
        scheduled_date = changed_fields["scheduled_publish_date"]
        if scheduled_date and scheduled_date != "TBD":
            try:
                scheduled_dt = datetime.strptime(scheduled_date, "%Y-%m-%d")
                today_dt = datetime.utcnow()

                if scheduled_dt.date() > today_dt.date():
                    payload["status"] = "scheduled"
                    scheduled_dt = scheduled_dt.replace(hour=6, minute=0)
                    scheduled_utc = scheduled_dt + timedelta(hours=7)
                    payload["publishDate"] = scheduled_utc.isoformat() + "Z"
                else:
                    payload["status"] = "published"
            except ValueError:
                pass

    if "status" in changed_fields:
        payload["status"] = changed_fields["status"]

    if not payload:
        print(f"⚠️ No fields to update for {entry_key}")
        return True

    try:
        response = requests.patch(
            update_url,
            headers=HEADERS,
            json=payload
        )

        if response.status_code in [200, 201]:
            print(f"✅ Synced {entry_key} to Acast ({len(payload)} fields)")
            return True
        else:
            print(f"❌ Update failed for {entry_key}: {response.status_code}")
            print(f"❌ Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Update error for {entry_key}: {e}")
        return False


# === BULK SYNC ALL EPISODES ===
def sync_all_uploaded_episodes():
    """
    Syncs all previously uploaded episodes to Acast with latest metadata.
    Used for bulk pushing corrected midrolls, titles, etc.
    """
    index = load_index()
    entries = index.get("entries", {})

    synced = []
    skipped = []
    failed = []

    for key, entry in entries.items():
        episode_id = entry.get("acast_episode_id")

        if not episode_id:
            skipped.append(key)
            continue

        # Build full update payload (all syncable fields)
        changed_fields = {}

        if entry.get("title"):
            changed_fields["title"] = entry["title"]
        if entry.get("summary"):
            changed_fields["summary"] = entry["summary"]
        if entry.get("alias"):
            changed_fields["alias"] = entry["alias"]
        if entry.get("markers"):
            changed_fields["markers"] = entry["markers"]
        if entry.get("scheduled_publish_date"):
            changed_fields["scheduled_publish_date"] = entry["scheduled_publish_date"]
        if entry.get("status"):
            changed_fields["status"] = entry["status"]

        print(f"\n🔄 Syncing {key}...")
        if update_episode_on_acast(key, episode_id, changed_fields):
            synced.append(key)
            entry["last_synced_at"] = datetime.utcnow().isoformat() + "Z"
        else:
            failed.append(key)

    # Save updated index with sync timestamps
    save_index(index)

    print(f"\n{'='*60}")
    print(f"✅ Synced: {len(synced)} episodes")
    print(f"⚠️ Skipped: {len(skipped)} episodes (no acast_episode_id)")
    print(f"❌ Failed: {len(failed)} episodes")
    print(f"{'='*60}")

    return {
        "synced": synced,
        "skipped": skipped,
        "failed": failed
    }


# === UPLOAD TO ACAST ===
def upload_episode(entry, entry_key=None):
    from datetime import timedelta

    audio_file = os.path.join(AUDIO_DIR, entry["audio"])
    if not os.path.exists(audio_file):
        print(f"❌ Missing audio file: {audio_file}")
        return False

    print(f"📤 Uploading: {entry['title']} using {audio_file}")

    # Build the form data with proper scheduling
    scheduled_date = entry.get("scheduled_publish_date")

    form_data = {
        "title": entry["title"],
        "summary": entry["summary"],
    }

    # Set status based on whether we have a future scheduled date
    if scheduled_date:
        try:
            scheduled_dt = datetime.strptime(scheduled_date, "%Y-%m-%d")
            today_dt = datetime.utcnow()

            if scheduled_dt.date() > today_dt.date():
                form_data["status"] = "scheduled"
                # Set publish time to 6:00 AM PT → convert to UTC = 13:00
                scheduled_dt = scheduled_dt.replace(hour=6, minute=0)
                scheduled_utc = scheduled_dt + timedelta(hours=7)
                scheduled_iso = scheduled_utc.isoformat() + "Z"
                form_data["publishDate"] = scheduled_iso
                print(f"📅 Scheduling for: {scheduled_date} (ISO: {scheduled_iso})")
            else:
                form_data["status"] = "published"
                print(f"📤 Publishing immediately (scheduled date has passed)")
        except ValueError:
            form_data["status"] = "draft"
            print(f"⚠️ Invalid date format: {scheduled_date}, defaulting to draft")
    else:
        form_data["status"] = "draft"
        print(f"📝 No scheduled date, uploading as draft")

    if entry.get("alias"):
        form_data["alias"] = entry["alias"]

    if entry.get("episodeNumber"):
        form_data["episodeNumber"] = str(entry["episodeNumber"])

    markers = entry.get("markers", [])
    if markers:
        marker_array = extract_markers_for_acast(markers)
        if marker_array:
            print(f"🎯 Setting markers as array: {marker_array}")
            form_data["markers"] = marker_array
    else:
        print("📝 No markers to set")

    try:
        with open(audio_file, "rb") as audio_handle:
            files = {"audio": audio_handle}

            response = requests.post(
                API_ENDPOINT,
                headers=HEADERS,
                data=form_data,
                files=files
            )

            print(f"🔍 Response: {response.status_code}")

            if response.status_code in [200, 201]:
                episode_data = response.json()
                episode_id = episode_data.get('_id')
                print(f"✅ Successfully uploaded: {entry['title']}")
                print(f"🆔 Episode ID: {episode_id}")

                # Store episode ID in index for future updates
                if entry_key:
                    index = load_index()
                    if entry_key in index.get("entries", {}):
                        index["entries"][entry_key]["acast_episode_id"] = episode_id
                        index["entries"][entry_key]["last_synced_at"] = datetime.utcnow().isoformat() + "Z"
                        save_index(index)
                        print(f"💾 Stored episode ID for {entry_key}")

                return True

            elif response.status_code == 400 and "alias already exists" in response.text:
                print(f"⚠️ Episode '{entry['title']}' already exists")
                return True

            else:
                print(f"❌ Upload failed: {response.status_code}")
                print(f"❌ Response: {response.text}")
                return False

    except Exception as e:
        print(f"❌ Upload error: {e}")
        return False

# === MAIN LOGIC ===
def run():
    index = load_index()
    entries = index.get("entries", {})

    if not entries:
        print("⚠️ No entries found.")
        return

    updated = False

    for key, entry in entries.items():
        status = entry.get("status")
        print(f"\n🔍 Checking: {entry.get('title', key)} [{status}]")

        if should_upload(entry):
            print("📤 Ready to upload as draft.")
            if upload_episode(entry, entry_key=key):
                entry["status"] = "uploaded"
                entry["uploaded_at"] = datetime.utcnow().isoformat()
                updated = True
                print(f"✅ Successfully uploaded: {entry['title']}")
            else:
                print(f"💥 Failed to upload: {entry['title']}")
                
        elif should_publish(entry):
            print("🚀 Ready to publish!")
            print("⚠️ Publishing not implemented yet")
            
        else:
            if status == "uploaded":
                print("⏳ Uploaded, waiting for scheduled date to publish.")
            else:
                print("⏸️ Skipping — not ready.")

    if updated:
        save_index(index)
        print("\n💾 Index updated.")



# === ENTRYPOINT ===
if __name__ == "__main__":
    import time
    print("🚀 STARTING FINAL PODCAST PUBLISHER")
    print("🎯 Using correct Acast marker format and scheduling")
    while True:
        run()
        time.sleep(60)  # Check every 60 seconds