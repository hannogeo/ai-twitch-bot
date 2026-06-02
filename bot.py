import socket
import ssl
import threading
import time
import re
import collections


class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.timestamps = collections.deque()

    def acquire(self) -> float:
        now = time.monotonic()
        while self.timestamps and now - self.timestamps[0] > self.period:
            self.timestamps.popleft()
        if len(self.timestamps) < self.max_calls:
            self.timestamps.append(now)
            return 0.0
        wait = self.period - (now - self.timestamps[0])
        self.timestamps.append(now + wait)
        return wait


class IRCBot:
    def __init__(self, config, ai_module, log_callback):
        self.config = config
        self.ai = ai_module
        self.log_callback = log_callback
        self.sock = None
        self.stop_event = threading.Event()
        self.rate_limiter = RateLimiter(19, 30)
        self.last_channel_send = 0.0

    def _normalize_token(self, token: str) -> str:
        token = token.strip()
        if not token.startswith("oauth:"):
            return "oauth:" + token
        return token

    def _send(self, data: str) -> bool:
        if not self.sock:
            return False
        try:
            self.sock.send(data.encode("utf-8"))
            return True
        except Exception:
            return False

    def _rate_limited_send(self, msg: str) -> bool:
        wait = self.rate_limiter.acquire()
        if wait > 0:
            time.sleep(wait)
        now = time.monotonic()
        since_last = now - self.last_channel_send
        if since_last < 1.1:
            time.sleep(1.1 - since_last)
        self.last_channel_send = time.monotonic()
        return self._send(msg)

    def parse_message(self, raw: str):
        tags = {}
        if raw.startswith("@"):
            try:
                tags_str, raw = raw[1:].split(" ", 1)
                for part in tags_str.split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        tags[k] = v
            except Exception:
                pass
        if "PRIVMSG" not in raw:
            return None, None, None, None
        try:
            prefix, trailing = raw.split(" PRIVMSG ", 1)
            user = prefix[prefix.rfind(':') + 1:].split('!', 1)[0]
            channel_part, message_part = trailing.split(" :", 1)
            return user, channel_part.split(" ", 1)[0], message_part.strip(), tags
        except Exception:
            return None, None, None, None

    def run(self):
        cfg = self.config
        if not all([cfg["TOKEN"], cfg["NICK"], cfg["CHANNEL"]]):
            self.log_callback("Missing credentials in Bot Config.")
            return

        self.stop_event.clear()
        try:
            raw_sock = socket.socket()
            raw_sock.settimeout(15.0)
            raw_sock.connect(("irc.chat.twitch.tv", 6697))
            context = ssl.create_default_context()
            self.sock = context.wrap_socket(raw_sock, server_hostname="irc.chat.twitch.tv")
            self.sock.settimeout(2.0)

            token = self._normalize_token(cfg["TOKEN"])
            nick = cfg["NICK"].lower().strip()
            self._send(f"PASS {token}\r\n")
            self._send(f"NICK {nick}\r\n")
            self._send("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n")
            self._send(f"JOIN #{cfg['CHANNEL']}\r\n")

            self.log_callback(f"Connected to #{cfg['CHANNEL']}")
            if cfg.get("CONNECT_MSG_ENABLED"):
                self._rate_limited_send(f"PRIVMSG #{cfg['CHANNEL']} :{cfg['CONNECT_MSG']}\r\n")

            while not self.stop_event.is_set():
                try:
                    resp = self.sock.recv(2048).decode("utf-8", errors="ignore")
                except socket.timeout:
                    continue
                except Exception:
                    break

                if not resp:
                    break
                for line in resp.split("\r\n"):
                    if not line:
                        continue
                    if line.startswith("PING"):
                        self._send("PONG :tmi.twitch.tv\r\n")
                        continue

                    if "PRIVMSG" not in line:
                        continue

                    user, chan, msg, tags = self.parse_message(line)
                    if not user or not msg:
                        continue
                    self.log_callback(f"{user}: {msg}")

                    msg_l = msg.lower()
                    nick_l = cfg["NICK"].lower()
                    parent_user = tags.get("reply-parent-user-login")

                    t_tag = cfg.get("TRIGGER_TAG", True)
                    t_cmd = cfg.get("TRIGGER_CMD", True)
                    t_rep = cfg.get("TRIGGER_REP", True)
                    t_other_rep = cfg.get("TRIGGER_OTHER_REP", True)

                    raw_cmds = cfg.get("COMMANDS", "!ai, !aichat")
                    cmds = sorted([c.strip().lower() for c in raw_cmds.split(",") if c.strip()], key=len, reverse=True)

                    is_tag = t_tag and f"@{nick_l}" in msg_l
                    is_rep = t_rep and parent_user and parent_user.lower() == nick_l

                    is_cmd = False
                    matched_cmd = None
                    if t_cmd:
                        for c in cmds:
                            if msg_l.startswith(c + " ") or msg_l == c:
                                is_cmd = True
                                matched_cmd = c
                                break

                    if parent_user and parent_user.lower() != nick_l and not t_other_rep:
                        can_trigger = is_cmd
                    else:
                        can_trigger = is_tag or is_cmd or is_rep

                    if can_trigger:
                        prompt = msg.strip()
                        if matched_cmd:
                            if msg_l.startswith(matched_cmd + " "):
                                prompt = msg[len(matched_cmd):].strip()
                            else:
                                prompt = ""
                        elif is_tag:
                            prompt = re.sub(rf"@{re.escape(nick_l)}", "", msg, flags=re.IGNORECASE).strip()

                        if not prompt:
                            prompt = "Say hi!"

                        final_prompt = prompt
                        if parent_user:
                            parent_msg = tags.get("reply-parent-msg-body", "").replace("\\s", " ")
                            final_prompt = f'[Replying to @{parent_user}: "{parent_msg}"]\n\n{prompt}'

                        response = self.ai.get_ai_response(final_prompt, user)
                        if response:
                            msg_id = tags.get("id")
                            if msg_id:
                                self._rate_limited_send(
                                    f"@reply-parent-msg-id={msg_id} PRIVMSG #{cfg['CHANNEL']} :{response}\r\n"
                                )
                            else:
                                self._rate_limited_send(
                                    f"PRIVMSG #{cfg['CHANNEL']} :@{user} {response}\r\n"
                                )
                            self.log_callback(f"BOT -> {user}: {response}")

        except Exception as e:
            self.log_callback(f"Connection Error: {e}")
        finally:
            if cfg.get("DISCONNECT_MSG_ENABLED") and self.sock:
                self._send(f"PRIVMSG #{cfg['CHANNEL']} :{cfg['DISCONNECT_MSG']}\r\n")
            if self.sock:
                self.sock.close()
            self.sock = None
            self.log_callback("Disconnected.")
