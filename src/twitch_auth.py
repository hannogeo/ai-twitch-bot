import os
import time

import requests


TWITCH_CLIENT_ID = "e6nlb7cil9n0e51c0gccu7tvd1fxcy"

SCOPES = "chat:read chat:edit"

DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
USERS_URL = "https://api.twitch.tv/helix/users"


class AuthError(Exception):
    pass


def _client_id():
    if not TWITCH_CLIENT_ID:
        raise AuthError("Twitch sign-in is not configured yet (no Client ID set).")
    return TWITCH_CLIENT_ID


def start_device_flow():
    """Start the Twitch device flow. Returns the device-code response dict."""
    resp = requests.post(DEVICE_URL,
                         data={"client_id": _client_id(), "scopes": SCOPES},
                         timeout=15)
    if resp.status_code != 200:
        raise AuthError(f"Could not start sign-in (HTTP {resp.status_code}).")
    return resp.json()


def poll_for_token(device_code, interval, cancel_event):
    """Poll until the user authorizes. Returns the token dict or raises AuthError."""
    while not cancel_event.is_set():
        time.sleep(interval)
        try:
            resp = requests.post(TOKEN_URL, data={
                "client_id": _client_id(),
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            }, timeout=15)
        except requests.RequestException as e:
            raise AuthError(f"Network error: {e}")

        data = resp.json()
        if resp.status_code == 200 and data.get("access_token"):
            return data

        msg = str(data.get("message", "")).lower()
        if msg == "authorization_pending":
            continue
        if msg == "slow_down":
            interval += 5
            continue
        if msg == "access_denied":
            raise AuthError("Sign-in was denied or cancelled on Twitch.")
        if "expired" in msg or "invalid" in msg:
            raise AuthError("The sign-in code expired. Please try again.")
        raise AuthError(f"Sign-in failed: {data.get('message', resp.status_code)}")

    raise AuthError("Sign-in cancelled.")


def refresh_access_token(refresh_token):
    """Exchange a refresh token for a new token pair. Returns dict or None."""
    resp = requests.post(TOKEN_URL, data={
        "client_id": _client_id(),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, timeout=15)
    data = resp.json()
    if resp.status_code == 200 and data.get("access_token"):
        return data
    return None


def get_user_info(access_token):
    """Fetch the authenticated user. Returns {'login', 'display_name'} or None."""
    resp = requests.get(USERS_URL, headers={
        "Authorization": f"Bearer {access_token}",
        "Client-Id": _client_id(),
    }, timeout=15)
    if resp.status_code == 200:
        users = resp.json().get("data") or []
        if users:
            u = users[0]
            login = (u.get("login") or "").lower()
            return {"login": login,
                    "display_name": u.get("display_name") or login}
    return None


def _account_token(entry):
    token = (entry or {}).get("access_token", "")
    return ("oauth:" + token) if token else ""


def refresh_stored_tokens(bot_config):
    """Refresh any stored access tokens so sessions stay alive. Saves config if changed."""
    auth = bot_config.get("TWITCH_AUTH") or {}
    changed = False
    for key in ("streamer", "bot"):
        entry = auth.get(key) or {}
        if not entry.get("refresh_token"):
            continue
        try:
            refreshed = refresh_access_token(entry["refresh_token"])
        except Exception:
            refreshed = None
        if refreshed and refreshed.get("access_token"):
            entry["access_token"] = refreshed["access_token"]
            if refreshed.get("refresh_token"):
                entry["refresh_token"] = refreshed["refresh_token"]
            changed = True
    if changed:
        bot_config["TWITCH_AUTH"] = auth
        bot_config.save()
    return changed


def get_effective_settings(bot_config, refresh=True):
    """Resolve the actual bot credentials. Returns a dict with CHANNEL/NICK/TOKEN."""
    if refresh:
        try:
            refresh_stored_tokens(bot_config)
        except Exception:
            pass

    auth = bot_config.get("TWITCH_AUTH") or {}
    streamer = auth.get("streamer") or {}
    bot = auth.get("bot") or {}

    if bot.get("login"):
        nick = bot["login"]
        token = _account_token(bot)
    elif streamer.get("login"):
        nick = streamer["login"]
        token = _account_token(streamer)
    else:
        nick = ""
        token = ""

    channel = streamer.get("login", "").lower()

    return {"CHANNEL": channel,
            "NICK": nick.strip().lower(),
            "TOKEN": token.strip()}
