import asyncio
import datetime
import os
import shutil
import threading
from pathlib import Path

import flet as ft
import flet_desktop

from ai_module import AIModule
from bot import IRCBot
from config import BASE_DIR, AIConfig, BotConfig
from updater import (GITHUB_REPO, check_for_update, download_update,
                     get_local_version, parse_semver)

VERSION = get_local_version()

# Clean stale Flet temp extraction dirs to avoid rename conflicts on Windows
_flet_cache_root = Path.home() / ".flet" / "client"
_flet_cache_name = f"flet-desktop-full-{flet_desktop.version.version}"
if _flet_cache_root.exists():
    for _item in _flet_cache_root.iterdir():
        # Match temp extraction dirs like "flet-desktop-full-0.85.2.xxxxx"
        if _item.name.startswith(_flet_cache_name + ".") and _item.is_dir():
            shutil.rmtree(_item, ignore_errors=True)


def main(page: ft.Page):
    page.title = "AI Twitch Bot"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.PURPLE)
    page.bgcolor = "#121214"
    page.window.width = 820
    page.window.height = 640
    page.window.min_width = 600
    page.window.min_height = 450
    page.window.icon = os.path.join(BASE_DIR, "app_icon.ico")

    bot_config = BotConfig()
    ai_config = AIConfig()
    ai_module = AIModule(ai_config)

    bot_thread = None
    bot_instance = None
    running = False

    log_lines = []

    def section_card(title, content, description=None):
        rows = [
            ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
        ]
        if description:
            rows.append(ft.Text(description, size=12, color=ft.Colors.GREY_400))
        rows.append(ft.Divider(height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
        rows.append(ft.Container(content, padding=ft.Padding(0, 4, 0, 0)))
        return ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor="#1C1C1E",
            border_radius=12,
            padding=16,
            margin=ft.Margin(0, 0, 0, 12),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
        )

    def snack(text):
        page.show_snack_bar(ft.SnackBar(ft.Text(text), duration=2000))

    def log(text, color=ft.Colors.WHITE_70):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log_lines.append(f"[{ts}] {text}")
        if len(log_lines) > 500:
            log_lines[:] = log_lines[-500:]
        log_area.value = "\n".join(log_lines)

        async def _update():
            log_area.update()

        page.run_task(_update)

    def toggle_bot(e):
        nonlocal running, bot_thread, bot_instance
        if running:
            if bot_instance:
                bot_instance.stop_event.set()
            running = False
            btn_toggle.content = "▶ START BOT"
            btn_toggle.style = btn_toggle_style
            btn_toggle.update()
            status_dot.bgcolor = ft.Colors.RED_500
            status_label.value = "STOPPED"
            status_label.color = ft.Colors.GREY_400
            status_badge.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.RED)
            page.update()
        else:
            if not bot_config["TOKEN"] or not bot_config["NICK"] or not bot_config["CHANNEL"]:
                page.show_dialog(ft.AlertDialog(
                    title=ft.Text("Missing credentials. Set up Bot Config first.", size=14),
                    title_padding=ft.Padding(20, 16, 20, 6),
                    content_padding=ft.Padding(0),
                ))
                return
            running = True
            btn_toggle.content = "■ STOP BOT"
            btn_toggle.style = btn_toggle_stop_style
            btn_toggle.update()
            status_dot.bgcolor = ft.Colors.GREEN_500
            status_label.value = "RUNNING"
            status_label.color = ft.Colors.GREEN_400
            status_badge.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.GREEN)
            page.update()

            def run_irc():
                nonlocal bot_instance
                irc = IRCBot(bot_config, ai_module, log)
                bot_instance = irc
                irc.run()

            bot_thread = threading.Thread(target=run_irc, daemon=True)
            bot_thread.start()

    # ── Save Handlers ─────────────────────────────────────────────────────

    def save_bot_config(e):
        bot_config["TOKEN"] = e_token.value.strip()
        bot_config["NICK"] = e_nick.value.strip()
        bot_config["CHANNEL"] = e_chan.value.strip().replace("#", "").lower()
        bot_config["CONNECT_MSG_ENABLED"] = sw_conn.value
        bot_config["DISCONNECT_MSG_ENABLED"] = sw_disc.value
        bot_config["TRIGGER_TAG"] = sw_tag.value
        bot_config["TRIGGER_CMD"] = sw_cmd.value
        bot_config["TRIGGER_REP"] = sw_rep.value
        bot_config["TRIGGER_OTHER_REP"] = sw_other_rep.value
        bot_config["COMMANDS"] = e_cmds.value.strip()
        bot_config.save()
        sw_tag.label = f"Activate on @{e_nick.value.strip() or 'Bot'} Tag"
        snack("Bot settings saved")
        page.update()

    def save_ai_config(e):
        ai_config["api_key"] = e_ai_key.value.strip()
        ai_config["enabled"] = sw_ai_enabled.value
        ai_config["system_instruction"] = t_ai_instr.value.strip()
        ai_config.save()
        ai_module._init_client()
        snack("AI settings saved")
        page.update()

    # ── Chatter Context ───────────────────────────────────────────────────

    ctx_container = ft.Column(spacing=5)

    def refresh_contexts():
        ctx_container.controls.clear()

        e_user = ft.TextField(label="Username", width=150, text_size=13, border_radius=8, bgcolor="#0D0D0F")
        e_info = ft.TextField(label="Context", multiline=True, min_lines=2, max_lines=4, expand=True, text_size=13,
                              border_radius=8, bgcolor="#0D0D0F")

        def on_add(e):
            u = e_user.value.strip().lower()
            i = e_info.value.strip()
            if u and i:
                ctx = ai_config.get("chatter_context", {})
                ctx[u] = i
                ai_config["chatter_context"] = ctx
                ai_config.save()
                refresh_contexts()

        add_btn_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding(14, 8, 14, 8))
        add_card = ft.Container(
            content=ft.Column([
                ft.Text("Add New Context", weight=ft.FontWeight.BOLD, size=14),
                ft.Row([
                    e_user,
                    e_info,
                    ft.FilledButton("Add", on_click=on_add, style=add_btn_style),
                ], spacing=8),
            ]),
            bgcolor="#0D0D0F",
            border_radius=10,
            padding=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
        )
        ctx_container.controls.append(add_card)

        ctx_dict = ai_config.get("chatter_context", {})
        for username in sorted(ctx_dict.keys()):
            info = ctx_dict[username]
            t_info = ft.TextField(value=info, multiline=True, min_lines=2, max_lines=4, expand=True, text_size=13,
                                  border_radius=8, bgcolor="#0D0D0F")

            def make_save(u, field):
                def fn(e):
                    ctx = ai_config.get("chatter_context", {})
                    ctx[u] = field.value.strip()
                    ai_config["chatter_context"] = ctx
                    ai_config.save()
                return fn

            def make_remove(u):
                def fn(e):
                    def do_delete(e2):
                        dlg.open = False
                        page.update()
                        ctx = ai_config.get("chatter_context", {})
                        ctx.pop(u, None)
                        ai_config["chatter_context"] = ctx
                        ai_config.save()
                        refresh_contexts()
                    dlg = ft.AlertDialog(
                        title=ft.Text("Delete context?", size=15),
                        title_padding=ft.Padding(20, 14, 20, 4),
                        content=ft.Text(f"Remove context for @{u}?", size=13),
                        content_padding=ft.Padding(20, 4, 20, 8),
                        actions_padding=ft.Padding(12, 4, 12, 10),
                        actions=[
                            ft.TextButton("Cancel", style=ft.ButtonStyle(padding=ft.Padding(14, 4, 14, 4)), on_click=lambda e2: setattr(dlg, 'open', False) or page.update()),
                            ft.TextButton("Delete", style=ft.ButtonStyle(padding=ft.Padding(14, 4, 14, 4)), on_click=do_delete),
                        ],
                    )
                    page.show_dialog(dlg)
                    page.update()
                return fn

            card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(f"@{username}", weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE_300, size=14, expand=True),
                        ft.Row([
                            ft.IconButton(ft.Icons.CHECK_CIRCLE_OUTLINE, on_click=make_save(username, t_info), tooltip="Save", icon_size=18),
                            ft.IconButton(ft.Icons.DELETE_OUTLINED, on_click=make_remove(username), tooltip="Remove", icon_size=18),
                        ], spacing=0),
                    ]),
                    ft.Container(height=4),
                    t_info,
                ]),
                bgcolor="#161618",
                border_radius=10,
                padding=14,
                margin=ft.Margin(0, 6, 0, 0),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
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
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=18, color=ft.Colors.AMBER),
                            ft.Text(f"Update {version} available", weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER, size=14),
                        ], spacing=8),
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=16, on_click=lambda e: setattr(update_banner, 'visible', False) or page.update()),
                ]),
                ft.Row([
                    ft.FilledButton("Download & Install", on_click=lambda e: start_update(url),
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding(14, 8, 14, 8))),
                ]),
            ], spacing=6),
            bgcolor="#1C1C1E",
            border_radius=10,
            padding=12,
            margin=ft.Margin(0, 0, 0, 10),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.AMBER)),
        )
        page.update()

    def start_update(url):
        progress_bar = ft.ProgressBar(width=200, color=ft.Colors.PURPLE_400, bgcolor="#2A2A2A")
        dl_status = ft.Text("Downloading... 0%", size=12)
        dl_speed = ft.Text("", size=11, color=ft.Colors.GREY_500)

        update_banner.content = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.DOWNLOAD, size=18, color=ft.Colors.PURPLE_400),
                    ft.Text("Downloading update...", weight=ft.FontWeight.BOLD, size=14),
                ], spacing=8),
                ft.Container(height=4),
                progress_bar,
                ft.Row([dl_status, dl_speed], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ], spacing=4),
            bgcolor="#1C1C1E",
            border_radius=10,
            padding=12,
            margin=ft.Margin(0, 0, 0, 10),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.PURPLE)),
        )
        page.update()

        def on_progress(percent, kbps, remaining):
            async def _update():
                dl_status.value = f"Downloading... {percent*100:.0f}%"
                if remaining < 60:
                    dl_speed.value = f"{kbps:.0f} KB/s — {remaining:.0f}s left"
                else:
                    dl_speed.value = f"{kbps:.0f} KB/s — {remaining/60:.1f}min left"
                progress_bar.value = percent
                page.update()
            page.run_task(_update)

        def on_downloaded(path, error):
            async def _update():
                if error:
                    dl_status.value = f"Download failed: {error}"
                    dl_status.color = ft.Colors.RED
                    page.update()
                    return
                if not path:
                    return
                dl_status.value = "Installing..."
                dl_speed.value = ""
                progress_bar.value = None
                page.update()
            page.run_task(_update)
            if error or not path:
                return

            from updater import apply_update
            apply_update(path)

            import time
            time.sleep(1)

            async def _destroy():
                await page.window.destroy()
                page.update()
            page.run_task(_destroy)

        from updater import download_update
        download_update(url, progress_callback=on_progress, done_callback=on_downloaded)

    check_for_update(on_update_available)

    # ── UI Controls ───────────────────────────────────────────────────────

    log_area = ft.TextField(
        multiline=True, read_only=True,
        expand=True,
        text_size=13,
        bgcolor="#0D0D0F", border_color=ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
        border_radius=8,
    )

    status_dot = ft.Container(width=10, height=10, border_radius=5, bgcolor=ft.Colors.RED_500)
    status_label = ft.Text("STOPPED", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_400)
    status_badge = ft.Container(
        content=ft.Row([status_dot, status_label], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding(12, 6, 16, 6),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.RED),
        border_radius=20,
    )

    btn_toggle_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding(24, 12, 24, 12),
        bgcolor={"": ft.Colors.GREEN_500},
        color={"": ft.Colors.BLACK},
    )
    btn_toggle_stop_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding(24, 12, 24, 12),
        bgcolor={"": ft.Colors.RED_500},
        color={"": ft.Colors.WHITE},
    )
    btn_toggle = ft.FilledButton("▶ START BOT", style=btn_toggle_style, on_click=toggle_bot)

    v_text = ft.Text(f"v{VERSION}", color=ft.Colors.BLUE_300, size=12)

    dashboard = ft.Column([
        ft.Row([status_badge, v_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        update_banner,
        section_card("Bot Log", log_area, "Live IRC activity and status messages."),
        ft.Row([btn_toggle], alignment=ft.MainAxisAlignment.CENTER),
    ], expand=True)

    # ── Bot Config Page ───────────────────────────────────────────────────

    e_token = ft.TextField(label="Access Token", value=bot_config["TOKEN"], password=True, can_reveal_password=True, expand=True, text_size=14, height=44,
                           border_radius=8, bgcolor="#0D0D0F")
    e_nick = ft.TextField(label="Bot Username", value=bot_config["NICK"], expand=True, text_size=14, height=44,
                          border_radius=8, bgcolor="#0D0D0F")
    e_chan = ft.TextField(label="Target Channel", value=bot_config["CHANNEL"], expand=True, text_size=14, height=44,
                          border_radius=8, bgcolor="#0D0D0F")

    sw_conn = ft.Switch(label="Send Connect Message", value=bot_config["CONNECT_MSG_ENABLED"])
    sw_disc = ft.Switch(label="Send Disconnect Message", value=bot_config["DISCONNECT_MSG_ENABLED"])
    sw_tag = ft.Switch(label=f"Activate on @{bot_config['NICK'] or 'Bot'} Tag", value=bot_config["TRIGGER_TAG"])
    sw_cmd = ft.Switch(label="Activate on Commands", value=bot_config["TRIGGER_CMD"])
    sw_rep = ft.Switch(label="Activate on Direct Replies", value=bot_config["TRIGGER_REP"])
    sw_other_rep = ft.Switch(label="Allow Triggers in Other Replies", value=bot_config["TRIGGER_OTHER_REP"])
    e_cmds = ft.TextField(label="Custom Commands", value=bot_config["COMMANDS"], expand=True, text_size=14,
                          hint_text="!ai, !aichat", border_radius=8, bgcolor="#0D0D0F")
    btn_save_bot_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding(20, 10, 20, 10))
    btn_save_bot = ft.FilledButton("Save Bot Settings", on_click=save_bot_config, style=btn_save_bot_style)

    bot_config_page = ft.Column([
        ft.Text("Bot Config", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("Connection settings for Twitch IRC.", color=ft.Colors.GREY_400, size=13),
        ft.Container(height=8),
        section_card("Credentials", ft.Column([
            e_token,
            ft.Text("Get an access token at twitchtokengenerator.com (scopes: chat:read, chat:edit).",
                    color=ft.Colors.GREY_500, size=12),
            ft.Container(height=4),
            e_nick,
            ft.Text("The name of the bot's Twitch account.", color=ft.Colors.GREY_500, size=12),
            ft.Container(height=4),
            e_chan,
        ], spacing=4)),
        section_card("Messages", ft.Column([sw_conn, sw_disc], spacing=4), "Auto-send messages when the bot connects or disconnects."),
        section_card("AI Activation", ft.Column([sw_tag, sw_cmd, sw_rep, sw_other_rep, ft.Container(height=4), e_cmds], spacing=4),
                     "Configure what triggers the AI to respond in chat."),
        ft.Row([btn_save_bot], alignment=ft.MainAxisAlignment.END),
        ft.Container(height=20),
    ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ── AI Config Page ────────────────────────────────────────────────────

    sw_ai_enabled = ft.Switch(label="AI Brain Enabled (Global)", value=ai_config["enabled"])
    e_ai_key = ft.TextField(label="Groq API Key", value=ai_config["api_key"], password=True, expand=True,
                            text_size=14, hint_text="gsk_...", border_radius=8, bgcolor="#0D0D0F")
    t_ai_instr = ft.TextField(label="System Instruction", value=ai_config["system_instruction"],
                              multiline=True, min_lines=6, max_lines=12, expand=True, text_size=14,
                              border_radius=8, bgcolor="#0D0D0F")
    btn_save_ai_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding(20, 10, 20, 10))
    btn_save_ai = ft.FilledButton("Save AI Settings", on_click=save_ai_config, style=btn_save_ai_style)

    ai_config_page = ft.Column([
        ft.Text("AI Config", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("Configure Groq interaction and personality.", color=ft.Colors.GREY_400, size=13),
        ft.Container(height=8),
        section_card("AI Brain", ft.Column([
            sw_ai_enabled,
            e_ai_key,
            ft.Text("Get your free key at console.groq.com/keys", color=ft.Colors.GREY_500, size=12),
            ft.Container(height=4),
            t_ai_instr,
        ], spacing=4)),
        section_card("Chatter Contexts", ctx_container, "Add context about specific chatters so the bot can personalise responses."),
        ft.Row([btn_save_ai], alignment=ft.MainAxisAlignment.END),
        ft.Container(height=20),
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
        min_width=90,
        min_extended_width=120,
        group_alignment=-0.9,
        bgcolor="#121214",
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="Bot Config",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.PSYCHOLOGY_OUTLINED, selected_icon=ft.Icons.PSYCHOLOGY, label="AI Config",
            ),
        ],
        on_change=nav_changed,
    )

    page.add(
        ft.Row([
            rail,
            ft.VerticalDivider(width=1, color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
            content_stack,
        ], expand=True, spacing=0)
    )

    # Auto-start bot after a moment if credentials are configured
    if bot_config["TOKEN"] and bot_config["NICK"] and bot_config["CHANNEL"]:
        async def _auto_start():
            await asyncio.sleep(1)
            toggle_bot(None)
        page.run_task(_auto_start)


if __name__ == "__main__":
    ft.run(main)
