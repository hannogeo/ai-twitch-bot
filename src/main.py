import asyncio
import os
import shutil
import threading
from pathlib import Path

import flet as ft
import flet_desktop

from ai_module import AIModule
from bot import IRCBot
from config import BASE_DIR, AIConfig, BotConfig
from pages import build_ai_config_page, build_bot_config_page
from ui import LogManager, section_card, snack
from updater import (check_for_update, download_update, get_local_version)

VERSION = get_local_version()

_flet_cache_root = Path.home() / ".flet" / "client"
_flet_cache_name = f"flet-desktop-full-{flet_desktop.version.version}"
if _flet_cache_root.exists():
    for _item in _flet_cache_root.iterdir():
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
    page.window.icon = os.path.join(BASE_DIR, "assets", "app_icon.ico")

    bot_config = BotConfig()
    ai_config = AIConfig()
    ai_module = AIModule(ai_config)
    log_mgr = LogManager(page)

    bot_thread = None
    bot_instance = None
    running = False

    status_dot = ft.Container(width=10, height=10, border_radius=5, bgcolor=ft.Colors.RED_500)
    status_label = ft.Text("STOPPED", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_400)
    status_badge = ft.Container(
        content=ft.Row([status_dot, status_label], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding(12, 6, 16, 6),
        bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.RED),
        border_radius=20,
    )

    btn_start_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding(24, 12, 24, 12),
        bgcolor={"": ft.Colors.GREEN_500},
        color={"": ft.Colors.BLACK},
    )
    btn_stop_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding(24, 12, 24, 12),
        bgcolor={"": ft.Colors.RED_500},
        color={"": ft.Colors.WHITE},
    )
    btn_toggle = ft.FilledButton("▶ START BOT", style=btn_start_style)

    def toggle_bot(e):
        nonlocal running, bot_thread, bot_instance

        if running:
            if bot_instance:
                bot_instance.stop_event.set()
            running = False
            btn_toggle.content = "▶ START BOT"
            btn_toggle.style = btn_start_style
            status_dot.bgcolor = ft.Colors.RED_500
            status_label.value = "STOPPED"
            status_label.color = ft.Colors.GREY_400
            status_badge.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.RED)
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
            btn_toggle.style = btn_stop_style
            status_dot.bgcolor = ft.Colors.GREEN_500
            status_label.value = "RUNNING"
            status_label.color = ft.Colors.GREEN_400
            status_badge.bgcolor = ft.Colors.with_opacity(0.08, ft.Colors.GREEN)

            def run_irc():
                nonlocal bot_instance
                irc = IRCBot(bot_config, ai_module, log_mgr.write)
                bot_instance = irc
                irc.run()

            bot_thread = threading.Thread(target=run_irc, daemon=True)
            bot_thread.start()

        btn_toggle.update()
        page.update()

    btn_toggle.on_click = toggle_bot

    # ── Auto-Update ──────────────────────────────────────────────────────

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
                    ft.IconButton(ft.Icons.CLOSE, icon_size=16,
                                  on_click=lambda e: setattr(update_banner, 'visible', False) or page.update()),
                ]),
                ft.Row([
                    ft.FilledButton("Download & Install",
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding(14, 8, 14, 8)),
                                    on_click=lambda e: start_update(url)),
                ]),
            ], spacing=6),
            bgcolor="#1C1C1E", border_radius=10, padding=12, margin=ft.Margin(0, 0, 0, 10),
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
            bgcolor="#1C1C1E", border_radius=10, padding=12, margin=ft.Margin(0, 0, 0, 10),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.PURPLE)),
        )
        page.update()

        def on_progress(percent, kbps, remaining):
            async def u():
                dl_status.value = f"Downloading... {percent*100:.0f}%"
                dl_speed.value = f"{kbps:.0f} KB/s — {'{:.0f}s'.format(remaining) if remaining < 60 else '{:.1f}min'.format(remaining/60)} left"
                progress_bar.value = percent
                page.update()
            page.run_task(u)

        def on_downloaded(path, error):
            async def u():
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
            page.run_task(u)
            if error or not path:
                return

            from updater import apply_update
            apply_update(path)

            import time
            time.sleep(1)

            async def destroy():
                await page.window.destroy()
                page.update()
            page.run_task(destroy)

        download_update(url, progress_callback=on_progress, done_callback=on_downloaded)

    check_for_update(on_update_available)

    # ── Migration banner ────────────────────────────────────────────────

    async def _open_url(e):
        await ft.UrlLauncher().launch_url("https://ai-twitch-bot.vercel.app")

    migration_banner = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.BLUE_300),
            ft.Column([
                ft.Text("There is now a better version of the bot", size=12, color=ft.Colors.GREY_300),
                ft.Row([
                    ft.Text("Try it at:", size=12, color=ft.Colors.GREY_500),
                    ft.GestureDetector(
                        content=ft.Text("https://ai-twitch-bot.vercel.app", size=12, color=ft.Colors.BLUE_300, italic=True,
                                        style=ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE, decoration_color=ft.Colors.BLUE_300)),
                        mouse_cursor=ft.MouseCursor.CLICK,
                        on_tap=lambda e: page.run_task(_open_url, e),
                    ),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text("But feel free to keep using this one if you'd like.", size=12, color=ft.Colors.GREY_500),
            ], spacing=1, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            ft.IconButton(ft.Icons.CLOSE, icon_size=14,
                          on_click=lambda e: setattr(migration_banner, 'visible', False) or page.update()),
        ], vertical_alignment=ft.CrossAxisAlignment.START),
        bgcolor="#1A1A2E",
        border_radius=8,
        padding=ft.Padding(10, 8, 4, 8),
        margin=ft.Margin(0, 0, 0, 6),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.08, ft.Colors.BLUE)),
    )

    # ── Pages ────────────────────────────────────────────────────────────

    dashboard = ft.Column([
        ft.Row([status_badge, ft.Text(f"v{VERSION}", color=ft.Colors.BLUE_300, size=12)],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        update_banner,
        migration_banner,
        section_card("Bot Log", log_mgr.container, "Live IRC activity and status messages.", expand=True),
        ft.Row([btn_toggle], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([ft.Text("Made with ♥ by HannoGeo", size=11, color=ft.Colors.GREY_600, italic=True)],
               alignment=ft.MainAxisAlignment.CENTER),
    ], expand=True, spacing=8)

    bot_config_page = build_bot_config_page(page, bot_config)
    ai_config_page = build_ai_config_page(page, ai_config, ai_module)

    content_stack = ft.Stack([
        ft.Container(dashboard, padding=20, visible=True),
        ft.Container(bot_config_page, padding=20, visible=False),
        ft.Container(ai_config_page, padding=20, visible=False),
    ], expand=True)
    page_views = content_stack.controls

    def nav_changed(e):
        idx = e.control.selected_index
        for i, c in enumerate(page_views):
            c.visible = (i == idx)
        page.update()

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=90, min_extended_width=120,
        group_alignment=-0.9,
        bgcolor="#121214",
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label="Dashboard"),
            ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="Bot Config"),
            ft.NavigationRailDestination(icon=ft.Icons.PSYCHOLOGY_OUTLINED, selected_icon=ft.Icons.PSYCHOLOGY, label="AI Config"),
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

    if bot_config["TOKEN"] and bot_config["NICK"] and bot_config["CHANNEL"]:
        async def _auto_start():
            await asyncio.sleep(1)
            toggle_bot(None)
        page.run_task(_auto_start)


if __name__ == "__main__":
    ft.run(main)
