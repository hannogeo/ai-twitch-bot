import datetime
import os
import platform
import subprocess
import sys
import threading
import webbrowser

import flet as ft
import requests

from ai_module import AIModule
from bot import IRCBot
from config import BASE_DIR, AIConfig, BotConfig
from updater import (GITHUB_REPO, check_for_update, download_update,
                     get_local_version, parse_semver)

VERSION = get_local_version()


def main(page: ft.Page):
    page.title = "AI Twitch Bot"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 820
    page.window.height = 640
    page.window.min_width = 600
    page.window.min_height = 450

    bot_config = BotConfig()
    ai_config = AIConfig()
    ai_module = AIModule(ai_config)

    bot_thread = None
    bot_instance = None
    running = False

    log_lines = []

    def log(text, color=ft.Colors.WHITE_70):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log_lines.append(f"[{ts}] {text}")
        if len(log_lines) > 500:
            log_lines[:] = log_lines[-500:]
        log_area.value = "\n".join(log_lines)
        page.update()

    def toggle_bot(e):
        nonlocal running, bot_thread, bot_instance
        if running:
            if bot_instance:
                bot_instance.stop_event.set()
            running = False
            btn_toggle.text = "▶ START BOT"
            btn_toggle.style = btn_start_style
            status_text.value = "● STOPPED"
            status_text.color = ft.Colors.RED
            page.update()
        else:
            if not bot_config["TOKEN"] or not bot_config["NICK"] or not bot_config["CHANNEL"]:
                page.show_dialog(ft.AlertDialog(title=ft.Text("Missing credentials. Set up Bot Config first.")))
                return
            running = True
            btn_toggle.text = "■ STOP BOT"
            btn_toggle.style = btn_stop_style
            status_text.value = "● RUNNING"
            status_text.color = ft.Colors.GREEN
            page.update()

            def run_irc():
                nonlocal bot_instance
                irc = IRCBot(bot_config, ai_module, log)
                bot_instance = irc
                irc.run()

            bot_thread = threading.Thread(target=run_irc, daemon=True)
            bot_thread.start()

    # ── Twitch Login ──────────────────────────────────────────────────────

    def start_twitch_login(e):
        client_id = e_client_id.value.strip()
        if not client_id:
            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Enter your Twitch App Client ID first."),
            ))
            return

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Twitch Login"),
            content=ft.Column([ft.Text("Starting login...")], width=420, height=250),
        )
        page.show_dialog(dlg)
        page.update()

        def do_login():
            try:
                resp = requests.post("https://id.twitch.tv/oauth2/device", data={
                    "client_id": client_id, "scopes": "chat:read chat:write"
                })
                data = resp.json()
                if resp.status_code != 200:
                    page.show_dialog(ft.AlertDialog(title=ft.Text(data.get("message", str(data)))))
                    dlg.open = False
                    page.update()
                    return

                device_code = data["device_code"]
                user_code = data["user_code"]
                interval = data.get("interval", 5)

                code_text = ft.Text(user_code, size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE)
                status_label = ft.Text("Waiting for authorization...", color=ft.Colors.GREY)
                btn_open = ft.FilledButton("Open twitch.tv/activate", on_click=lambda e: webbrowser.open("https://www.twitch.tv/activate"))

                dlg.content = ft.Column([
                    ft.Text("Enter this code on the Twitch activation page:", size=14),
                    ft.Container(code_text, alignment=ft.alignment.center, margin=20),
                    btn_open,
                    status_label,
                ], width=420, height=250, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                page.update()

                def poll():
                    nonlocal interval
                    import time as _t
                    while True:
                        _t.sleep(interval)
                        try:
                            pr = requests.post("https://id.twitch.tv/oauth2/token", data={
                                "client_id": client_id, "scopes": "chat:read chat:write",
                                "device_code": device_code,
                                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                            })
                            if pr.status_code == 200:
                                j = pr.json()
                                tok = j["access_token"]
                                dlg.open = False
                                page.update()
                                on_login_success(tok)
                                return
                            err = pr.json().get("error", "")
                            if err == "authorization_pending":
                                continue
                            if err == "slow_down":
                                interval += 1
                                continue
                            if err == "expired_token":
                                status_label.value = "Code expired. Try again."
                                status_label.color = ft.Colors.RED
                                page.update()
                                return
                            status_label.value = f"Error: {err}"
                            status_label.color = ft.Colors.RED
                            page.update()
                            return
                        except Exception as ex:
                            status_label.value = f"Error: {str(ex)[:30]}"
                            status_label.color = ft.Colors.RED
                            page.update()
                            return

                threading.Thread(target=poll, daemon=True).start()

            except Exception as ex:
                dlg.open = False
                page.update()
                page.show_dialog(ft.AlertDialog(title=ft.Text(f"Login failed: {str(ex)[:60]}")))

        threading.Thread(target=do_login, daemon=True).start()

    def on_login_success(token):
        bot_config["TOKEN"] = token
        bot_config.save()
        log("Twitch token obtained and saved.", ft.Colors.GREEN)
        try:
            vr = requests.get("https://id.twitch.tv/oauth2/validate",
                              headers={"Authorization": f"Bearer {token}"}, timeout=5)
            if vr.status_code == 200:
                login_name = vr.json().get("login", "")
                if login_name:
                    bot_config["NICK"] = login_name
                    bot_config.save()
                    e_nick.value = login_name
                    page.update()
                    log(f"Bot username auto-filled: {login_name}", ft.Colors.GREEN)
        except Exception:
            pass

    # ── Save Handlers ─────────────────────────────────────────────────────

    def save_bot_config(e):
        bot_config["NICK"] = e_nick.value.strip()
        bot_config["CHANNEL"] = e_chan.value.strip().replace("#", "").lower()
        bot_config["CLIENT_ID"] = e_client_id.value.strip()
        bot_config["CONNECT_MSG_ENABLED"] = sw_conn.value
        bot_config["DISCONNECT_MSG_ENABLED"] = sw_disc.value
        bot_config["TRIGGER_TAG"] = sw_tag.value
        bot_config["TRIGGER_CMD"] = sw_cmd.value
        bot_config["TRIGGER_REP"] = sw_rep.value
        bot_config["TRIGGER_OTHER_REP"] = sw_other_rep.value
        bot_config["COMMANDS"] = e_cmds.value.strip()
        bot_config.save()
        sw_tag.label = f"Activate on @{e_nick.value.strip() or 'Bot'} Tag"
        page.show_dialog(ft.AlertDialog(title=ft.Text("Bot settings saved!")))
        page.update()

    def save_ai_config(e):
        ai_config["api_key"] = e_ai_key.value.strip()
        ai_config["enabled"] = sw_ai_enabled.value
        ai_config["system_instruction"] = t_ai_instr.value.strip()
        ai_config.save()
        ai_module._init_client()
        page.show_dialog(ft.AlertDialog(title=ft.Text("AI settings saved!")))
        page.update()

    # ── Chatter Context ───────────────────────────────────────────────────

    ctx_container = ft.Column(spacing=5)

    def refresh_contexts():
        ctx_container.controls.clear()

        e_user = ft.TextField(label="Username", width=150, text_size=13)
        e_info = ft.TextField(label="Context", multiline=True, min_lines=2, max_lines=4, expand=True, text_size=13)

        def on_add(e):
            u = e_user.value.strip().lower()
            i = e_info.value.strip()
            if u and i:
                ctx = ai_config.get("chatter_context", {})
                ctx[u] = i
                ai_config["chatter_context"] = ctx
                ai_config.save()
                refresh_contexts()

        add_card = ft.Container(
            content=ft.Column([
                ft.Text("Add New Context", weight=ft.FontWeight.BOLD, size=14),
                ft.Row([
                    e_user,
                    e_info,
                    ft.FilledButton("Add", on_click=on_add, bgcolor=ft.Colors.GREEN, color=ft.Colors.BLACK),
                ]),
            ]),
            bgcolor="#18181A",
            border_radius=8,
            padding=10,
        )
        ctx_container.controls.append(add_card)

        ctx_dict = ai_config.get("chatter_context", {})
        for username in sorted(ctx_dict.keys()):
            info = ctx_dict[username]
            t_info = ft.TextField(value=info, multiline=True, min_lines=2, max_lines=4, expand=True, text_size=13)

            def make_save(u, field):
                def fn(e):
                    ctx = ai_config.get("chatter_context", {})
                    ctx[u] = field.value.strip()
                    ai_config["chatter_context"] = ctx
                    ai_config.save()
                return fn

            def make_remove(u):
                def fn(e):
                    ctx = ai_config.get("chatter_context", {})
                    ctx.pop(u, None)
                    ai_config["chatter_context"] = ctx
                    ai_config.save()
                    refresh_contexts()
                return fn

            card = ft.Container(
                content=ft.Column([
                    ft.Text(f"@{username}", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_400, size=14),
                    ft.Row([
                        t_info,
                        ft.Column([
                            ft.IconButton(ft.Icons.SAVE_OUTLINED, on_click=make_save(username, t_info), tooltip="Save"),
                            ft.IconButton(ft.Icons.DELETE_OUTLINED, on_click=make_remove(username), tooltip="Remove"),
                        ]),
                    ]),
                ]),
                bgcolor="#1E1E1E",
                border_radius=8,
                padding=10,
                margin=ft.Margin(0, 5, 0, 5),
            )
            ctx_container.controls.append(card)

        page.update()

    refresh_contexts()

    # ── Auto-Update ───────────────────────────────────────────────────────

    update_banner = ft.Container(visible=False)

    def on_update_available(version, url):
        if version is None:
            return
        update_banner.visible = True
        update_banner.content = ft.Container(
            content=ft.Row([
                ft.Text(f"Update v{version} available!", weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER),
                ft.ProgressBar(width=200, visible=False),
                ft.FilledButton("Download & Install", on_click=lambda e: start_update(url)),
                ft.IconButton(ft.Icons.CLOSE, on_click=lambda e: setattr(update_banner, 'visible', False) or page.update()),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor="#2A2A2A",
            border_radius=8,
            padding=10,
            margin=ft.Margin(0, 0, 0, 10),
        )
        page.update()

    def start_update(url):
        progress = ft.ProgressBar(width=200)
        update_banner.content.content.controls[2] = progress
        update_banner.content.content.controls[2].visible = True
        page.update()

        def on_done(path, error):
            if error:
                page.show_dialog(ft.AlertDialog(title=ft.Text(f"Update failed: {error}")))
                return
            if path:
                page.show_dialog(ft.AlertDialog(
                    title=ft.Text("Update downloaded"),
                    content=ft.Text("The installer will launch. Please close the app after installation."),
                ))
                subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES"])

        download_update(url, done_callback=on_done)

    check_for_update(on_update_available)

    # ── UI Controls ───────────────────────────────────────────────────────

    log_area = ft.TextField(
        multiline=True, read_only=True,
        expand=True,
        text_size=13,
        bgcolor="#18181A", border_color=ft.Colors.TRANSPARENT,
    )

    status_text = ft.Text("● STOPPED", color=ft.Colors.RED, size=16, weight=ft.FontWeight.BOLD)

    btn_start_style = ft.ButtonStyle(bgcolor={"": ft.Colors.GREEN_500}, color={"": ft.Colors.BLACK})
    btn_stop_style = ft.ButtonStyle(bgcolor={"": ft.Colors.RED_500}, color={"": ft.Colors.WHITE})
    btn_toggle = ft.FilledButton("▶ START BOT", style=btn_start_style, on_click=toggle_bot)

    v_text = ft.Text(f"v{VERSION}", color=ft.Colors.BLUE_300, size=12)

    dashboard = ft.Column([
        ft.Row([status_text, v_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        update_banner,
        log_area,
        ft.Row([btn_toggle], alignment=ft.MainAxisAlignment.CENTER),
    ], expand=True)

    # ── Bot Config Page ───────────────────────────────────────────────────

    e_client_id = ft.TextField(label="Twitch App Client ID", value=bot_config["CLIENT_ID"], expand=True, text_size=14, height=45)
    e_nick = ft.TextField(label="Bot Username", value=bot_config["NICK"], expand=True, text_size=14, height=45)
    e_chan = ft.TextField(label="Target Channel", value=bot_config["CHANNEL"], expand=True, text_size=14, height=45)

    btn_login = ft.FilledButton("Login with Twitch", on_click=start_twitch_login,
                                   bgcolor=ft.Colors.PURPLE_600, color=ft.Colors.WHITE)

    sw_conn = ft.Switch(label="Send Connect Message", value=bot_config["CONNECT_MSG_ENABLED"])
    sw_disc = ft.Switch(label="Send Disconnect Message", value=bot_config["DISCONNECT_MSG_ENABLED"])
    sw_tag = ft.Switch(label=f"Activate on @{bot_config['NICK'] or 'Bot'} Tag", value=bot_config["TRIGGER_TAG"])
    sw_cmd = ft.Switch(label="Activate on Commands", value=bot_config["TRIGGER_CMD"])
    sw_rep = ft.Switch(label="Activate on Direct Replies", value=bot_config["TRIGGER_REP"])
    sw_other_rep = ft.Switch(label="Allow Triggers in Other Replies", value=bot_config["TRIGGER_OTHER_REP"])
    e_cmds = ft.TextField(label="Custom Commands", value=bot_config["COMMANDS"], expand=True, text_size=14,
                          hint_text="!ai, !aichat")
    btn_save_bot = ft.FilledButton("Save Bot Settings", on_click=save_bot_config,
                                      bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE)

    bot_config_page = ft.Column([
        ft.Text("BOT CREDENTIALS", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("Connection settings for Twitch IRC.", color=ft.Colors.GREY, size=13),
        ft.Container(height=20),
        e_client_id,
        ft.Row([btn_login, ft.Text("Register an app at dev.twitch.tv, then paste your Client ID.",
                                    color=ft.Colors.GREY, size=12)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Container(height=10),
        e_nick,
        ft.Text("Auto-filled after Twitch login. Can also be set manually.", color=ft.Colors.GREY, size=12),
        ft.Container(height=10),
        e_chan,
        ft.Container(height=20),
        ft.Text("MESSAGES", size=18, weight=ft.FontWeight.BOLD),
        sw_conn,
        sw_disc,
        ft.Container(height=20),
        ft.Text("AI ACTIVATION", size=18, weight=ft.FontWeight.BOLD),
        sw_tag,
        sw_cmd,
        sw_rep,
        sw_other_rep,
        ft.Container(height=10),
        e_cmds,
        ft.Container(height=20),
        btn_save_bot,
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ── AI Config Page ────────────────────────────────────────────────────

    sw_ai_enabled = ft.Switch(label="AI Brain Enabled (Global)", value=ai_config["enabled"])
    e_ai_key = ft.TextField(label="Groq API Key", value=ai_config["api_key"], password=True, expand=True,
                            text_size=14, hint_text="gsk_...")
    t_ai_instr = ft.TextField(label="System Instruction", value=ai_config["system_instruction"],
                              multiline=True, min_lines=6, max_lines=12, expand=True, text_size=14)
    btn_save_ai = ft.FilledButton("Save AI Settings", on_click=save_ai_config,
                                     bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE)

    ai_config_page = ft.Column([
        ft.Text("AI BRAIN SETTINGS", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("Configure Groq interaction and personality.", color=ft.Colors.GREY, size=13),
        ft.Container(height=20),
        sw_ai_enabled,
        ft.Container(height=10),
        e_ai_key,
        ft.Text("Get your free key at console.groq.com/keys", color=ft.Colors.GREY, size=12),
        ft.Container(height=15),
        t_ai_instr,
        ft.Container(height=20),
        btn_save_ai,
        ft.Container(height=30),
        ft.Text("CHATTER CONTEXTS", size=22, weight=ft.FontWeight.BOLD),
        ft.Text("Add context about specific chatters so the bot can personalise responses.",
                color=ft.Colors.GREY, size=12),
        ft.Container(height=10),
        ctx_container,
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ── Navigation ────────────────────────────────────────────────────────

    content_stack = ft.Stack([
        ft.Container(dashboard, padding=20, visible=True),
        ft.Container(bot_config_page, padding=20, visible=False),
        ft.Container(ai_config_page, padding=20, visible=False),
    ], expand=True)

    pages = [dashboard, bot_config_page, ai_config_page]
    page_views = content_stack.controls

    def nav_changed(e):
        idx = e.control.selected_index
        for i, c in enumerate(page_views):
            c.visible = (i == idx)
        page.update()

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=80,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.SETTINGS, label="Bot Config"),
            ft.NavigationRailDestination(icon=ft.Icons.PSYCHOLOGY, label="AI Config"),
        ],
        on_change=nav_changed,
    )

    page.add(
        ft.Row([
            rail,
            ft.VerticalDivider(width=1),
            content_stack,
        ], expand=True)
    )

    # Auto-start bot after a moment if credentials are configured
    if bot_config["TOKEN"] and bot_config["NICK"] and bot_config["CHANNEL"]:
        threading.Timer(1.0, lambda: toggle_bot(None)).start()


if __name__ == "__main__":
    ft.run(main)
