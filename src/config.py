import json
import os
import sys

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
BOT_CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")
AI_CONFIG_FILE = os.path.join(DATA_DIR, "ai_config.json")


def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def _migrate_old_config():
    for old_name, new_path in [("bot_config.json", BOT_CONFIG_FILE), ("ai_config.json", AI_CONFIG_FILE)]:
        old_path = os.path.join(BASE_DIR, old_name)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                os.rename(old_path, new_path)
            except Exception:
                try:
                    import shutil
                    shutil.copy2(old_path, new_path)
                    os.remove(old_path)
                except Exception:
                    pass


_ensure_data_dir()
_migrate_old_config()


class BotConfig:
    DEFAULTS = {
        "CONNECT_MSG_ENABLED": True, "CONNECT_MSG": "/me is now connected...",
        "DISCONNECT_MSG_ENABLED": True, "DISCONNECT_MSG": "/me disconnected!",
        "TRIGGER_TAG": True, "TRIGGER_CMD": True, "TRIGGER_REP": True,
        "TRIGGER_OTHER_REP": True, "COMMANDS": "!ai, !aichat",
        "TWITCH_AUTH": {"streamer": {}, "bot": {}}
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(BOT_CONFIG_FILE):
            try:
                with open(BOT_CONFIG_FILE, "r") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        _ensure_data_dir()
        try:
            with open(BOT_CONFIG_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            print(f"Save error: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data.get(key, self.DEFAULTS.get(key, ""))

    def __setitem__(self, key, value):
        self.data[key] = value


class AIConfig:
    DEFAULTS = {
        "api_key": "",
        "system_instruction": "You are a helpful AI Twitch bot.",
        "chatter_context": {}
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(AI_CONFIG_FILE):
            try:
                with open(AI_CONFIG_FILE, "r") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        _ensure_data_dir()
        try:
            with open(AI_CONFIG_FILE, "w") as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            print(f"Save error: {e}")

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key):
        return self.data.get(key, self.DEFAULTS.get(key, ""))

    def __setitem__(self, key, value):
        self.data[key] = value
