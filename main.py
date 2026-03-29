"""
AI Chatbot
================================
A modern, all-in-one Twitch chatbot powered by Groq LLM.
Designed for high stability and visual excellence using pure Tkinter.
"""

import socket
import sys
import threading
import time
import json
import os
import datetime
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from groq import Groq
import requests
import subprocess

# Attempt to import DuckDuckGo Search
try:
    from ddgs import DDGS
except ImportError:
    DDGS = None

# ──────────────────────────────────────────────────────────────────────────────
# Global Configuration & Paths
# ──────────────────────────────────────────────────────────────────────────────

VERSION = "1.0.5"
GITHUB_REPO = "hannogeo/ai-twitch-bot"  # EDIT THIS to enable Auto-Updates

if getattr(sys, 'frozen', False) or "__compiled__" in globals():
    # This ensures bot_config and ai_config save securely NEXT to the .exe 
    # and survive all updates, completely avoiding compiler temp destruction
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_CONFIG_FILE = os.path.join(BASE_DIR, "bot_config.json")
AI_CONFIG_FILE = os.path.join(BASE_DIR, "ai_config.json")

# ──────────────────────────────────────────────────────────────────────────────
# Logic: Search Tool
# ──────────────────────────────────────────────────────────────────────────────

def perform_search(query: str, max_results: int = 4) -> str:
    if DDGS is None:
        return "DuckDuckGo search not available. Please install 'duckduckgo-search'."
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            if not results: return "No search results found."
            summary = []
            for r in results:
                summary.append(f"Result: {r.get('title', 'No Title')}\nContent: {r.get('body', 'No Content')}")
            return "\n\n".join(summary)
    except Exception as e:
        return f"Search Error: {str(e)}"

# ──────────────────────────────────────────────────────────────────────────────
# Logic: AI Chat Module
# ──────────────────────────────────────────────────────────────────────────────

class AIModule:
    def __init__(self):
        self.config = {}
        self.groq_client = None
        self.history = []
        self.config_lock = threading.RLock()
        self.history_lock = threading.RLock()
        self.load_config()

    def load_config(self):
        with self.config_lock:
            if os.path.exists(AI_CONFIG_FILE):
                try:
                    with open(AI_CONFIG_FILE, "r", encoding="utf-8") as f:
                        self.config = json.load(f)
                except:
                    self.config = {}
            else:
                self.config = {
                    "api_key": "",
                    "enabled": True,
                    "system_instruction": "You are a helpful AI Twitch bot.",
                    "chatter_context": {}
                }
                self.save_config()

            api_key = self.config.get("api_key", "").strip()
            if api_key:
                try:
                    self.groq_client = Groq(api_key=api_key)
                except:
                    self.groq_client = None
            else:
                self.groq_client = None

    def save_config(self):
        with self.config_lock:
            try:
                with open(AI_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4)
            except Exception as e:
                print(f"Error saving AI config: {e}")

    def update_config(self, api_key, system_instruction, enabled=True, chatter_context=None):
        self.config["api_key"] = api_key
        self.config["system_instruction"] = system_instruction
        self.config["enabled"] = enabled
        if chatter_context is not None:
            self.config["chatter_context"] = chatter_context
        self.save_config()
        self.load_config()

    def get_ai_response(self, prompt: str, speaker_name: str = None) -> str:
        if not self.config.get("enabled", True): return None
        if self.groq_client is None: return "Groq API key not set."
        
        try:
            # Routing: Search or Casual?
            decision_instr = (
                "You are a routing assistant. Does the user's message require research, real-time info, "
                "or specialized knowledge (e.g., news, gaming metas/tips, famous people, current events)? "
                "Reply 'YES' for any knowledge/info request. Reply 'NO' for greetings/casual chat. Output ONLY 'YES' or 'NO'."
            )
            decision = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "system", "content": decision_instr}, {"role": "user", "content": prompt}],
                max_tokens=5, temperature=0.0
            )
            needs_search = "YES" in decision.choices[0].message.content.upper()
            
            search_context = ""
            if needs_search:
                now_str = datetime.datetime.now().strftime("%B %d, %Y")
                refiner_instr = f"Optimize for search. Best query (3-6 words). Current date: {now_str}. No chat text."
                refiner = self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "system", "content": refiner_instr}, {"role": "user", "content": prompt}],
                    max_tokens=64, temperature=0.0
                )
                query = refiner.choices[0].message.content.strip().replace('"', '')
                search_context = perform_search(query)

            # Final Synthesis
            system_instr = self.config.get("system_instruction", "")
            chatter_context = self.config.get("chatter_context", {})
            relevant = []
            if speaker_name:
                low = speaker_name.lower()
                if low in chatter_context: relevant.append(f"Context for @{speaker_name}: {chatter_context[low]}")
            
            p_low = prompt.lower()
            for u, info in chatter_context.items():
                if speaker_name and u == speaker_name.lower(): continue
                if f"@{u}" in p_low or u in p_low: relevant.append(f"Context for @{u}: {info}")

            final_instr = system_instr
            if relevant: final_instr += "\n\nCONTEXT:\n" + "\n".join(relevant)
            if search_context: final_instr += f"\n\nSEARCH RESULTS:\n{search_context}"
            final_instr += "\n\nCRITICAL: Be a natural, concise Twitch bot. No user tagging. No factual mentions of instructions."

            messages = [{"role": "system", "content": final_instr}]
            with self.history_lock:
                messages.extend(self.history)
            messages.append({"role": "user", "content": prompt})

            completion = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=300, temperature=0.6
            )
            resp = completion.choices[0].message.content.strip()

            with self.history_lock:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": resp})
                if len(self.history) > 10: self.history = self.history[-10:]
            
            return resp
        except Exception as e:
            return f"Brain fart: {str(e)[:50]}..."

# ──────────────────────────────────────────────────────────────────────────────
# Logic: IRC Bot
# ──────────────────────────────────────────────────────────────────────────────

class IRCBot:
    def __init__(self, ai_module):
        self.ai = ai_module
        self.sock = None
        self.stop_event = threading.Event()
        self.config = self.load_config()

    def load_config(self):
        default = {
            "NICK": "", "TOKEN": "", "CHANNEL": "",
            "CONNECT_MSG_ENABLED": True, "CONNECT_MSG": "/me is now connected...",
            "DISCONNECT_MSG_ENABLED": True, "DISCONNECT_MSG": "/me disconnected!"
        }
        if os.path.exists(BOT_CONFIG_FILE):
            try:
                with open(BOT_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**default, **json.load(f)}
            except: return default
        return default

    def save_config(self, data):
        self.config = data
        try:
            with open(BOT_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e: print(f"Save error: {e}")

    def parse_message(self, raw: str):
        tags = {}
        if raw.startswith("@"):
            try:
                tags_str, raw = raw[1:].split(" ", 1)
                for part in tags_str.split(";"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        tags[k] = v
            except: pass
        if "PRIVMSG" not in raw: return None, None, None, None
        try:
            prefix, trailing = raw.split(" PRIVMSG ", 1)
            user = prefix[prefix.rfind(':')+1:].split('!',1)[0]
            channel_part, message_part = trailing.split(" :", 1)
            return user, channel_part.split(" ", 1)[0], message_part.strip(), tags
        except: return None, None, None, None

    def run(self, log_callback):
        if not all([self.config["TOKEN"], self.config["NICK"], self.config["CHANNEL"]]):
            log_callback("Error: Missing credentials in Bot Config.", "#F7768E")
            return

        self.stop_event.clear()
        try:
            self.sock = socket.socket()
            self.sock.connect(("irc.chat.twitch.tv", 6667))
            self.sock.send(f"PASS {self.config['TOKEN']}\r\n".encode("utf-8"))
            self.sock.send(f"NICK {self.config['NICK']}\r\n".encode("utf-8"))
            self.sock.send("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n".encode("utf-8"))
            self.sock.send(f"JOIN #{self.config['CHANNEL']}\r\n".encode("utf-8"))

            log_callback(f"Connected to #{self.config['CHANNEL']}", "#9ECE6A")
            if self.config.get("CONNECT_MSG_ENABLED"):
                self.sock.send(f"PRIVMSG #{self.config['CHANNEL']} :{self.config['CONNECT_MSG']}\r\n".encode("utf-8"))

            self.sock.settimeout(2.0)
            while not self.stop_event.is_set():
                try:
                    resp = self.sock.recv(2048).decode("utf-8", errors="ignore")
                except socket.timeout: continue
                except: break
                
                if not resp: break
                for line in resp.split("\r\n"):
                    if not line: continue
                    if line.startswith("PING"):
                        self.sock.send("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
                        continue

                    user, chan, msg, tags = self.parse_message(line)
                    if not user or not msg: continue
                    log_callback(f"{user}: {msg}")

                    msg_l = msg.lower()
                    nick_l = self.config['NICK'].lower()
                    is_ai = f"@{nick_l}" in msg_l or msg_l.startswith("!ai ") or msg_l in ("!ai", "!aichat")
                    parent_user = tags.get("reply-parent-user-login")
                    is_reply = parent_user and parent_user.lower() == nick_l

                    if is_ai or is_reply:
                        prompt = msg.strip()
                        if msg_l.startswith("!ai"): prompt = msg[3:].strip()
                        elif msg_l.startswith("!aichat"): prompt = msg[7:].strip()
                        elif f"@{nick_l}" in msg_l: prompt = msg_l.replace(f"@{nick_l}", "").strip()
                        
                        if not prompt: prompt = "Say hi!"
                        
                        final_prompt = prompt
                        if parent_user:
                            parent_msg = tags.get("reply-parent-msg-body", "").replace("\\s", " ")
                            final_prompt = f"[Replying to @{parent_user}: \"{parent_msg}\"]\n\n{prompt}"

                        response = self.ai.get_ai_response(final_prompt, user)
                        if response:
                            msg_id = tags.get("id")
                            if msg_id:
                                self.sock.send(f"@reply-parent-msg-id={msg_id} PRIVMSG #{self.config['CHANNEL']} :{response}\r\n".encode("utf-8"))
                            else:
                                self.sock.send(f"PRIVMSG #{self.config['CHANNEL']} :@{user} {response}\r\n".encode("utf-8"))
                            log_callback(f"BOT -> {user}: {response}", "#7AA2F7")

        except Exception as e:
            log_callback(f"Connection Error: {e}", "#F7768E")
        finally:
            if self.config.get("DISCONNECT_MSG_ENABLED") and self.sock:
                try: self.sock.send(f"PRIVMSG #{self.config['CHANNEL']} :{self.config['DISCONNECT_MSG']}\r\n".encode("utf-8"))
                except: pass
            if self.sock: self.sock.close()
            self.sock = None
            log_callback("Disconnected.", "#F7768E")

# ──────────────────────────────────────────────────────────────────────────────
# GUI: Modern Dashboard (CustomTkinter)
# ──────────────────────────────────────────────────────────────────────────────

class ModernApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Chatbot - Dashboard")
        self.root.geometry("950x650")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.ai = AIModule()
        self.bot = IRCBot(self.ai)
        self.is_running = False

        self.setup_ui()
        self.show_page("dashboard")

        # Auto-start bot on launch
        self.root.after(500, self.start_bot)

        # Check for updates in background
        threading.Thread(target=self.check_for_updates, daemon=True).start()

        # Graceful shutdown hook
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self.root, width=220, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="AI Chatbot", font=ctk.CTkFont(size=22, weight="bold"), text_color="#3B8ED0").pack(pady=30)
        
        self.nav_btns = []
        for name, page in [("Dashboard", "dashboard"), ("Bot Config", "config"), ("AI Brain", "ai")]:
            btn = ctk.CTkButton(self.sidebar, text=name, command=lambda p=page: self.show_page(p), 
                                fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"), 
                                anchor="w", font=ctk.CTkFont(size=14))
            btn.pack(fill="x", padx=15, pady=5)
            self.nav_btns.append(btn)

        # Main Area
        self.container = ctk.CTkFrame(self.root, fg_color="transparent")
        self.container.pack(side="right", fill="both", expand=True)

        # Dashboard Page
        self.p_dashboard = ctk.CTkFrame(self.container, fg_color="transparent")
        self.build_dashboard()

        # Config Page
        self.p_config = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self._set_fast_scroll(self.p_config)
        self.build_config()

        # AI Page
        self.p_ai = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self._set_fast_scroll(self.p_ai)
        self.build_ai()

    def _set_fast_scroll(self, scroll_frame):
        try:
            # By modifying the internal Tkinter Canvas yscrollincrement, 
            # we multiply the physical pixel distance of every "unit" that CustomTkinter asks to scroll.
            scroll_frame._parent_canvas.configure(yscrollincrement="15")
        except Exception as e:
            print("Scroll speed fix error:", e)

    def _isolate_scroll(self, child_widget, parent_scroll_frame):
        def on_enter(e):
            try: parent_scroll_frame._parent_canvas.unbind_all("<MouseWheel>")
            except: pass
        def on_leave(e):
            try: parent_scroll_frame._parent_canvas.bind_all("<MouseWheel>", parent_scroll_frame._mouse_wheel_all)
            except: pass
        
        child_widget.bind("<Enter>", on_enter)
        child_widget.bind("<Leave>", on_leave)

    def _auto_resize_textbox(self, t_widget):
        def do_resize(event=None):
            try:
                text = t_widget.get("1.0", "end-1c")
                total_lines = sum(max(1, len(line) // 60 + 1) for line in text.split('\n'))
                h = max(60, min(total_lines * 22 + 10, 200))
                t_widget.configure(height=h)
            except: pass
        t_widget.bind("<KeyRelease>", do_resize)
        do_resize()

    def build_dashboard(self):
        header = ctk.CTkFrame(self.p_dashboard, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=(40, 10))

        self.status_indicator = ctk.CTkLabel(header, text="● STOPPED", text_color="#F7768E", font=ctk.CTkFont(size=16, weight="bold"))
        self.status_indicator.pack(side="left")

        # Log Area
        self.log_area = ctk.CTkTextbox(self.p_dashboard, font=ctk.CTkFont(family="Consolas", size=13), wrap="word", corner_radius=10, fg_color="#18181A")
        self.log_area.pack(fill="both", expand=True, padx=40, pady=10)
        self.log_area.configure(state="disabled")

        # Controls
        ctrl = ctk.CTkFrame(self.p_dashboard, fg_color="transparent")
        ctrl.pack(fill="x", padx=40, pady=20)

        self.btn_toggle = ctk.CTkButton(ctrl, text="▶ START BOT", fg_color="#9ECE6A", text_color="black", hover_color="#7BB04A", font=ctk.CTkFont(weight="bold"), command=self.toggle_bot)
        self.btn_toggle.pack(side="left")

    def build_config(self):
        ctk.CTkLabel(self.p_config, text="BOT CREDENTIALS", font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w", padx=40, pady=(40, 5))
        ctk.CTkLabel(self.p_config, text="Connection settings for Twitch IRC.", text_color="gray").pack(anchor="w", padx=40)

        f = ctk.CTkFrame(self.p_config, fg_color="transparent")
        f.pack(fill="x", padx=40, pady=20)

        def create_entry(parent, label, default, show=""):
            ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(10, 2))
            e = ctk.CTkEntry(parent, font=ctk.CTkFont(size=14), show=show, height=40, corner_radius=8)
            e.pack(fill="x", pady=(0, 10))
            e.insert(0, default)
            return e

        self.e_nick = create_entry(f, "Bot Username", self.bot.config.get("NICK", ""))
        self.e_token = create_entry(f, "OAuth Token (oauth:xxx)", self.bot.config.get("TOKEN", ""), show="*")
        self.e_chan = create_entry(f, "Channel", self.bot.config.get("CHANNEL", ""))
        
        ctk.CTkButton(f, text="Save Credentials", font=ctk.CTkFont(weight="bold", size=14), height=45, corner_radius=8, command=self.save_bot_config).pack(fill="x", pady=30)

    def build_ai(self):
        ctk.CTkLabel(self.p_ai, text="AI BRAIN SETTINGS", font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w", padx=40, pady=(40, 5))
        ctk.CTkLabel(self.p_ai, text="Configure Groq interaction and personality.", text_color="gray").pack(anchor="w", padx=40)

        f = ctk.CTkFrame(self.p_ai, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=40, pady=20)

        ctk.CTkLabel(f, text="Groq API Key", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(10, 2))
        self.e_ai_key = ctk.CTkEntry(f, font=ctk.CTkFont(size=14), show="*", height=40, corner_radius=8)
        self.e_ai_key.pack(fill="x", pady=(0, 10))
        self.e_ai_key.insert(0, self.ai.config.get("api_key", ""))

        ctk.CTkLabel(f, text="System Instruction (Persona)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(10, 2))
        self.t_ai_instr = ctk.CTkTextbox(f, font=ctk.CTkFont(size=13), height=140, wrap="word", corner_radius=8)
        self.t_ai_instr.pack(fill="both", expand=True)
        self.t_ai_instr.insert("1.0", self.ai.config.get("system_instruction", ""))

        self._isolate_scroll(self.t_ai_instr, self.p_ai)
        self._auto_resize_textbox(self.t_ai_instr)

        ctk.CTkButton(f, text="Save AI Settings", font=ctk.CTkFont(weight="bold", size=14), height=45, corner_radius=8, command=self.save_ai_config).pack(fill="x", pady=20)

        # Chatter Contexts
        ctk.CTkLabel(self.p_ai, text="CHATTER CONTEXTS", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=40, pady=(30, 10))
        
        self.ctx_container = ctk.CTkFrame(self.p_ai, fg_color="transparent")
        self.ctx_container.pack(fill="both", expand=True, padx=40)

        self.refresh_context_ui()

    def refresh_context_ui(self):
        # Clear container
        for widget in self.ctx_container.winfo_children():
            widget.destroy()

        # Add New row
        add_f = ctk.CTkFrame(self.ctx_container, fg_color="#18181A", corner_radius=8)
        add_f.pack(fill="x", pady=(0, 20), ipadx=10, ipady=10)

        ctk.CTkLabel(add_f, text="Add New Context", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5, 5))

        entry_f = ctk.CTkFrame(add_f, fg_color="transparent")
        entry_f.pack(fill="x", padx=10, pady=(0, 5))

        e_user = ctk.CTkEntry(entry_f, placeholder_text="Username", width=150)
        e_user.pack(side="left", padx=(0, 10), anchor="n")

        e_info = ctk.CTkTextbox(entry_f, height=60, wrap="word", fg_color="#1E1E1E", border_width=1, border_color="#333333")
        e_info.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self._isolate_scroll(e_info, self.p_ai)
        self._auto_resize_textbox(e_info)

        def on_add():
            u = e_user.get().strip().lower()
            i = e_info.get("1.0", "end-1c").strip()
            if u and i:
                ctx = self.ai.config.get("chatter_context", {})
                ctx[u] = i
                self.ai.config["chatter_context"] = ctx
                self.ai.save_config()
                self.refresh_context_ui()

        ctk.CTkButton(entry_f, text="Add", width=80, fg_color="#2FA572", hover_color="#1F754E", command=on_add).pack(side="right", anchor="n")

        # Existing contexts
        ctx_dict = self.ai.config.get("chatter_context", {})
        for user in sorted(ctx_dict.keys()):
            info = ctx_dict[user]
            
            card = ctk.CTkFrame(self.ctx_container, fg_color="#1E1E1E", corner_radius=8)
            card.pack(fill="x", pady=5, ipadx=10, ipady=10)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(0, 5))

            ctk.CTkLabel(top, text=f"@{user}", font=ctk.CTkFont(weight="bold", size=14), text_color="#7AA2F7").pack(side="left")

            def make_delete(u=user):
                def do_delete():
                    c = self.ai.config.get("chatter_context", {})
                    if u in c:
                        del c[u]
                        self.ai.config["chatter_context"] = c
                        self.ai.save_config()
                        self.refresh_context_ui()
                return do_delete

            ctk.CTkButton(top, text="Remove", width=60, height=24, fg_color="#D14E53", hover_color="#A1363A", font=ctk.CTkFont(size=12), command=make_delete(user)).pack(side="right")

            txt = ctk.CTkTextbox(card, height=60, wrap="word", fg_color="#16161E", border_width=1, border_color="#333333")
            txt.pack(fill="x", padx=10)
            txt.insert("1.0", info)

            self._isolate_scroll(txt, self.p_ai)
            self._auto_resize_textbox(txt)

            def make_save(u=user, t_widget=txt):
                def do_save():
                    i = t_widget.get("1.0", "end-1c").strip()
                    c = self.ai.config.get("chatter_context", {})
                    c[u] = i
                    self.ai.config["chatter_context"] = c
                    self.ai.save_config()
                return do_save

            btn_save = ctk.CTkButton(card, text="Save Changes", width=100, height=24, fg_color="#565F89", hover_color="#343A59", font=ctk.CTkFont(size=12), command=make_save(user, txt))
            btn_save.pack(anchor="e", padx=10, pady=(5, 0))
    def show_page(self, page_name):
        self.p_dashboard.pack_forget()
        self.p_config.pack_forget()
        self.p_ai.pack_forget()
        
        if page_name == "dashboard": self.p_dashboard.pack(fill="both", expand=True)
        elif page_name == "config": self.p_config.pack(fill="both", expand=True)
        elif page_name == "ai": self.p_ai.pack(fill="both", expand=True)

    def log(self, text, color=None):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"[{ts}] {text}\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def toggle_bot(self):
        if self.is_running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        if self.is_running: return
        self.is_running = True
        self.btn_toggle.configure(text="■ STOP BOT", fg_color="#F7768E", hover_color="#C95F71")
        self.status_indicator.configure(text="● RUNNING", text_color="#9ECE6A")
        threading.Thread(target=self.bot.run, args=(self.log,), daemon=True).start()

    def stop_bot(self):
        if not self.is_running: return
        self.bot.stop_event.set()
        self.is_running = False
        self.btn_toggle.configure(text="▶ START BOT", fg_color="#9ECE6A", hover_color="#7BB04A")
        self.status_indicator.configure(text="● STOPPED", text_color="#F7768E")

    def save_bot_config(self):
        data = self.bot.config
        data["NICK"] = self.e_nick.get().strip()
        data["TOKEN"] = self.e_token.get().strip()
        data["CHANNEL"] = self.e_chan.get().strip().replace("#", "").lower()
        self.bot.save_config(data)
        messagebox.showinfo("Success", "Bot configuration saved!")

    def save_ai_config(self):
        key = self.e_ai_key.get().strip()
        instr = self.t_ai_instr.get("1.0", "end").strip()
        self.ai.update_config(key, instr)
        messagebox.showinfo("Success", "AI settings saved!")

    def check_for_updates(self):
        try:
            if "YourUsername" in GITHUB_REPO: return
            resp = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("tag_name", "").lstrip("v")
                current = VERSION.lstrip("v")
                if latest > current:
                    assets = data.get("assets", [])
                    if assets:
                        dl_url = assets[0]["browser_download_url"]
                        self.root.after(0, lambda: self.show_update_button(latest, dl_url))
        except: pass

    def show_update_button(self, version, url):
        self.btn_update = ctk.CTkButton(self.p_dashboard, text=f"🎉 Update available: v{version}", fg_color="#E0AF68", text_color="black", hover_color="#C09048", font=ctk.CTkFont(weight="bold"), command=lambda: self.do_update(url))
        self.btn_update.pack(pady=20)

    def do_update(self, url):
        self.btn_update.configure(state="disabled", text="Downloading... (Please wait)")
        def _dl():
            try:
                r = requests.get(url, stream=True)
                new_exe = os.path.join(BASE_DIR, "AIChatbot_new.exe")
                with open(new_exe, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                bat_path = os.path.join(BASE_DIR, "update.bat")
                current_exe = sys.executable if (getattr(sys, 'frozen', False) or "__compiled__" in globals()) else os.path.abspath(__file__)
                if not (getattr(sys, 'frozen', False) or "__compiled__" in globals()):
                    self.root.after(0, lambda: self.btn_update.configure(text="Update downloaded (Run script manually)"))
                    return
                
                with open(bat_path, "w") as f:
                    f.write("@echo off\n"
                            "timeout /t 2 /nobreak >nul\n"
                            f"del \"{current_exe}\"\n"
                            f"ren \"{new_exe}\" \"{os.path.basename(current_exe)}\"\n"
                            f"start \"\" \"{current_exe}\"\n"
                            f"del \"%~f0\"\n")
                
                # Clear PyInstaller's hidden environment flags to prevent the new EXE from crashing 
                # as it tries to read the dying parent's transient extraction folder.
                clean_env = os.environ.copy()
                clean_env.pop("_MEIPASS2", None)
                clean_env.pop("_MEIPASS", None)
                clean_env.pop("TCL_LIBRARY", None)
                clean_env.pop("TK_LIBRARY", None)
                
                subprocess.Popen(bat_path, shell=True, env=clean_env, creationflags=0x00000008)  # DETACHED_PROCESS
                # Gracefully drop connection before swapping executables
                self.root.after(0, self.on_closing)
            except Exception as e:
                self.root.after(0, lambda: self.btn_update.configure(text=f"Update Failed: {e}"))
        threading.Thread(target=_dl, daemon=True).start()

    def on_closing(self):
        if self.is_running:
            self.btn_toggle.configure(state="disabled")
            self.status_indicator.configure(text="● DISCONNECTING...", text_color="#E0AF68")
            self.root.update()
            
            self.bot.stop_event.set()
            start_wait = time.time()
            # Wait up to 2.5 seconds for the bot thread to send its message and close sock
            while self.bot.sock is not None and (time.time() - start_wait) < 2.5:
                self.root.update()
                time.sleep(0.05)
                
        self.root.destroy()
        os._exit(0)

if __name__ == "__main__":
    root = ctk.CTk()
    app = ModernApp(root)
    root.mainloop()
