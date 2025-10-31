import json
import os

# Customize these patterns as needed
JUNK_PATTERNS = [
    "no-reply", "noreply", "support@", "info@", "mailer@", "calendar@",
    "donotreply", "auto@", "admin@", "@stripe", "@zendesk", "@intercom",
    "@slack", "@amazon", "@google"
]

INPUT_FILE = "data/contacts_raw.json"
OUTPUT_FILE = "data/contacts_cleaned.json"


def is_junk_email(email):
    if not email or not isinstance(email, str):
        return True
    email = email.lower()
    return any(pattern in email for pattern in JUNK_PATTERNS)


def clean_contacts():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Input file not found: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r") as f:
        raw_data = json.load(f)

    cleaned = {}
    dropped = 0

    for key, entry in raw_data.get("entries", {}).items():
        name = entry.get("name", "").strip()
        email = entry.get("email", "").strip()

        if not name or not email or is_junk_email(email):
            dropped += 1
            continue

        cleaned[key] = {
            "name": name,
            "email": email
        }

    with open(OUTPUT_FILE, "w") as f:
        json.dump({"entries": cleaned}, f, indent=2)

    print(f"✅ Cleaned {len(cleaned)} entries. Dropped {dropped} junk contacts.")


if __name__ == "__main__":
    clean_contacts()