import json
import os
import sys
import threading

import requests

GITHUB_REPO = "hannogeo/ai-twitch-bot"


def parse_semver(version: str):
    parts = version.strip().lstrip("v").split(".")
    major = int(parts[0]) if parts and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return (major, minor, patch)


def get_local_version() -> str:
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    vpath = os.path.join(base, "version.json")
    try:
        with open(vpath, "r") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def check_for_update(callback):
    """Check GitHub for latest release. Calls callback(latest_version, download_url) or callback(None, None)."""
    def _check():
        try:
            resp = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                latest_tag = data.get("tag_name", "")
                local_ver = get_local_version()
                if parse_semver(latest_tag) > parse_semver(local_ver):
                    assets = data.get("assets", [])
                    setup_asset = next((a for a in assets if a["name"].endswith("-Setup.exe")), None)
                    if setup_asset:
                        callback(latest_tag, setup_asset["browser_download_url"])
                        return
            callback(None, None)
        except Exception:
            callback(None, None)

    threading.Thread(target=_check, daemon=True).start()


def download_update(url, progress_callback=None, done_callback=None):
    """Download update setup exe. Calls done_callback(path, error)."""
    def _do():
        try:
            base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            setup_path = os.path.join(base, "update_setup.exe")

            r = requests.get(url, stream=True, timeout=30)
            total = int(r.headers.get('content-length', 0))
            downloaded = 0

            with open(setup_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total:
                            progress_callback(downloaded / total)

            if done_callback:
                done_callback(setup_path, None)
        except Exception as e:
            if done_callback:
                done_callback(None, str(e))

    threading.Thread(target=_do, daemon=True).start()
