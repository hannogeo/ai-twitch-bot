import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile

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


def get_app_dir() -> str:
    return os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))


def check_for_update(callback):
    """Check GitHub for latest release. Calls callback(version, zip_url) or callback(None, None)."""
    def _check():
        try:
            resp = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                latest_tag = data.get("tag_name", "")
                local_ver = get_local_version()
                if parse_semver(latest_tag) > parse_semver(local_ver):
                    assets = data.get("assets", [])
                    zip_asset = next((a for a in assets if a["name"].endswith(".zip") and "setup" not in a["name"].lower()), None)
                    if zip_asset:
                        callback(latest_tag, zip_asset["browser_download_url"])
                        return
            callback(None, None)
        except Exception:
            callback(None, None)

    threading.Thread(target=_check, daemon=True).start()


def download_update(url, progress_callback=None, done_callback=None):
    """Download update zip. progress_callback(percent, speed_kbps, eta_seconds). done_callback(path, error)."""
    def _do():
        try:
            base = get_app_dir()
            zip_path = os.path.join(base, "update.zip")

            r = requests.get(url, stream=True, timeout=30)
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.monotonic()
            last_update = 0

            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if progress_callback and total and now - last_update > 0.1:
                            elapsed = now - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            kbps = speed / 1024
                            remaining = (total - downloaded) / speed if speed > 0 else 0
                            progress_callback(downloaded / total, kbps, remaining)
                            last_update = now

            if done_callback:
                done_callback(zip_path, None)
        except Exception as e:
            if done_callback:
                done_callback(None, str(e))

    threading.Thread(target=_do, daemon=True).start()


def apply_update(zip_path, done_callback=None):
    """Extract zip, create restart script, and launch it. Calls done_callback(error) before exiting."""
    def _apply():
        try:
            base = get_app_dir()
            temp_dir = os.path.join(base, "update_temp")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(temp_dir)

            # The zip contains a folder named AITwitchBot/
            source = os.path.join(temp_dir, "AITwitchBot")
            if not os.path.exists(source):
                # Files might be at root of zip
                source = temp_dir

            exe_name = os.path.basename(sys.executable) if getattr(sys, 'frozen', False) else "AITwitchBot.exe"
            bat_path = os.path.join(base, "update.bat")

            bat_content = f"""@echo off
chcp 65001 >nul
echo Waiting for app to close...
:waitloop
tasklist /FI "IMAGENAME eq {exe_name}" 2>nul | find /I "{exe_name}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)
echo Updating files...
xcopy "{source}\\*" "{base}\\" /E /Y /Q
echo Cleaning up...
rmdir /S /Q "{temp_dir}" 2>nul
del "{zip_path}" 2>nul
start "" "{base}\\{exe_name}"
del "%~f0"
"""
            with open(bat_path, "w") as f:
                f.write(bat_content)

            subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if done_callback:
                done_callback(None)
        except Exception as e:
            if done_callback:
                done_callback(str(e))

    threading.Thread(target=_apply, daemon=True).start()
