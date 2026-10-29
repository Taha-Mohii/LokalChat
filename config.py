import json
import os
import uuid
import tempfile
from utils.crypto import create_identity

CHUNK_SIZE = 4096
TCP_PORT = 5000
DISCOVERY_PORT = 5001

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)

    return None

def save_config(device_id, name, identity_private_key=None):
    if not identity_private_key:
        previous = load_config() or {}
        if previous.get("device_id") == device_id:
            identity_private_key = previous.get("identity_private_key")
        if not identity_private_key:
            identity_private_key, _ = create_identity()
    config = {
        "device_id" : device_id,
        "name" : name,
        "identity_private_key": identity_private_key,
    }
    os.makedirs(BASE_DIR, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="config-", dir=BASE_DIR, text=True)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(config, f, indent=4)
        os.replace(temp_path, CONFIG_FILE)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
    return config

def get_or_create_config(name=None):
    config = load_config()
    if config:
        if name and config.get("name") != name:
            return save_config(config.get("device_id") or str(uuid.uuid4()), name)
        if not config.get("device_id"):
            return save_config(str(uuid.uuid4()), config.get("name") or name or "User")
        if not config.get("identity_private_key"):
            return save_config(config["device_id"], config.get("name") or name or "User")
        return config
    device_id = str(uuid.uuid4())
    return save_config(device_id, name)

def update_name(new_name):
    config = load_config()
    if config:
        config["name"] = new_name
        return save_config(config["device_id"], new_name,
                           config.get("identity_private_key"))
    return save_config(str(uuid.uuid4()), new_name)
