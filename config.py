import json
import os
import sys

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

BOT_CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")
AI_CONFIG_FILE = os.path.join(BASE_DIR, "ai_config.json")


class BotConfig:
    DEFAULTS = {
        "NICK": "", "TOKEN": "", "CHANNEL": "", "CLIENT_ID": "",
        "CONNECT_MSG_ENABLED": True, "CONNECT_MSG": "/me is now connected...",
        "DISCONNECT_MSG_ENABLED": True, "DISCONNECT_MSG": "/me disconnected!",
        "TRIGGER_TAG": True, "TRIGGER_CMD": True, "TRIGGER_REP": True,
        "TRIGGER_OTHER_REP": True, "COMMANDS": "!ai, !aichat"
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
        "enabled": True,
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
