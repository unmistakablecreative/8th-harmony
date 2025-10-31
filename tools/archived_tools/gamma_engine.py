#!/usr/bin/env python3
import os
import json
import argparse
import requests
import time
from datetime import datetime

# === CONFIG ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "tools", "credentials.json")
CONFIG_PATH = os.path.join(BASE_DIR, "data", "presentation_config.json")
INPUT_FILE = os.path.join(BASE_DIR, "data", "gamma_input.txt")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
GAMMA_ENDPOINT = "https://public-api.gamma.app/v0.2/generations"
GAMMA_POLL_ENDPOINT = "https://public-api.gamma.app/v0.2/generations/{}"

# === HELPERS ===
def load_api_key():
    try:
        with open(CREDENTIALS_PATH, "r") as f:
            creds = json.load(f)
            return creds.get("GAMMA_API_KEY", "")
    except Exception:
        return ""

def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to load config: {e}"}

def load_input_text():
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to read input text: {e}"}

def extract_title(text):
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return "untitled_" + datetime.now().strftime("%Y%m%d_%H%M%S")

def save_file_from_url(file_url, filename):
    try:
        os.makedirs(EXPORT_DIR, exist_ok=True)
        file_path = os.path.join(EXPORT_DIR, filename)
        response = requests.get(file_url)
        with open(file_path, "wb") as f:
            f.write(response.content)
        return file_path
    except Exception as e:
        return f"❌ Failed to download file: {e}"

def poll_until_ready(gamma_id, timeout=90, interval=5):
    poll_url = GAMMA_POLL_ENDPOINT.format(gamma_id)
    headers = {"X-API-KEY": load_api_key()}
    for _ in range(0, timeout, interval):
        try:
            response = requests.get(poll_url, headers=headers)
            data = response.json()
            if data.get("status") == "complete":
                return data
            time.sleep(interval)
        except Exception:
            time.sleep(interval)
    return None

# === MAIN FUNCTION ===
def create_gamma_deck():
    config = load_config()
    if isinstance(config, dict) and config.get("status") == "error":
        print(json.dumps(config, indent=2))
        return

    input_text = load_input_text()
    if isinstance(input_text, dict) and input_text.get("status") == "error":
        print(json.dumps(input_text, indent=2))
        return

    payload = config.copy()
    payload["inputText"] = input_text
    title = extract_title(input_text)

    try:
        response = requests.post(
            GAMMA_ENDPOINT,
            headers={
                "X-API-KEY": load_api_key(),
                "Content-Type": "application/json"
            },
            json=payload
        )
        raw = response.text
        print("📦 Raw Gamma Response:")
        print(raw)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"❌ API error {response.status_code}: {raw}")
        data = response.json()
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"❌ Failed to submit request: {e}"}))
        return

    gamma_id = data.get("generationId")
    if not gamma_id:
        print(json.dumps({"status": "error", "message": "❌ Gamma response missing generationId."}))
        return

    result = poll_until_ready(gamma_id)
    if not result:
        print(json.dumps({"status": "error", "message": "❌ Generation timed out."}))
        return

    final_output = {
        "status": "success",
        "deck_url": result.get("publicUrl"),
        "download_url": result.get("downloadUrl"),
        "title": title,
    }

    if result.get("downloadUrl"):
        ext = config.get("exportAs", "pdf")
        filename = f"{title}.{ext}"
        download_path = save_file_from_url(result["downloadUrl"], filename)
        final_output["saved_file"] = download_path

    print(json.dumps(final_output, indent=2))

# === CONFIG MODIFIER ===
def modify_config(filename="presentation_config.json", field=None, value=None):
    config_path = os.path.join(BASE_DIR, "data", filename)
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"❌ Failed to load config: {e}"}))
        return

    if field and value:
        keys = field.split(".")
        obj = config
        for k in keys[:-1]:
            obj = obj.setdefault(k, {})
        obj[keys[-1]] = value
        try:
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            print(json.dumps({"status": "success", "message": f"✅ Updated {field} to '{value}'"}))
        except Exception as e:
            print(json.dumps({"status": "error", "message": f"❌ Failed to write config: {e}"}))
        return

    print(json.dumps(config, indent=2))

# === ENTRYPOINT ===
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create_gamma_deck", "modify_config"])
    parser.add_argument("--field")
    parser.add_argument("--value")
    parser.add_argument("--config")
    parser.add_argument("--params", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.command == "create_gamma_deck":
        create_gamma_deck()
    elif args.command == "modify_config":
        fname = args.config or "presentation_config.json"
        modify_config(fname, args.field, args.value)

if __name__ == "__main__":
    main()
