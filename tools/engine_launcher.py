import os
import json
import subprocess
import logging

def launch_all_engines():
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    REGISTRY_PATH = os.path.join(BASE_DIR, "../data/engine_registry.json")

    try:
        with open(REGISTRY_PATH, "r") as f:
            registry = json.load(f)
    except Exception as e:
        logging.error(f"⚠️ Failed to load engine registry: {e}")
        return

    engines = registry.get("engines", [])

    for engine_file in engines:
        engine_path = os.path.join(BASE_DIR, engine_file)
        logging.info(f"🛠 Attempting to launch: {engine_path}")
        if os.path.exists(engine_path):
            try:
                subprocess.Popen(["python3", engine_path, "run_engine"])
                logging.info(f"🚀 Launched engine: {engine_file}")
            except Exception as e:
                logging.error(f"❌ Failed to launch {engine_file}: {e}")
        else:
            logging.warning(f"⚠️ Engine script not found: {engine_path}")

if __name__ == "__main__":
    launch_all_engines()