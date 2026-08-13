import threading
import webbrowser

import flet as ft

from twitch_auth import (get_effective_settings, get_user_info,
                         poll_for_token, start_device_flow)
from ui import section_card, snack


def build_bot_config_page(page, bot_config):
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

    # ── Twitch sign-in ─────────────────────────────────────────────────────

    def refresh_account_ui():
        auth = bot_config.get("TWITCH_AUTH") or {}
        for entry, status, btn, out in (
            (auth.get("streamer") or {}, st_status, st_btn, st_out),
            (auth.get("bot") or {}, bot_status, bot_btn, bot_out),
        ):
            name = entry.get("display_name") or entry.get("login") or ""
            if name:
                status.value = f"Signed in as @{name}"
                status.color = ft.Colors.GREEN_400
                btn.visible = False
                out.visible = True
            else:
                status.value = "Not signed in"
                status.color = ft.Colors.GREY_500
                btn.visible = True
                out.visible = False
        page.update()

    def sync_fields_from_auth():
        eff = get_effective_settings(bot_config, refresh=False)
        e_chan.value = eff["CHANNEL"]
        e_nick.value = eff["NICK"]
        e_token.value = eff["TOKEN"]

    def sign_out(account_key):
        auth = dict(bot_config.get("TWITCH_AUTH") or {})
        auth.pop(account_key, None)
        bot_config["TWITCH_AUTH"] = auth
        bot_config.save()
        sync_fields_from_auth()
        refresh_account_ui()
        snack(page, "Signed out")

    def sign_in(account_key):
        cancel_event = threading.Event()

        async def close_dlg():
            dlg.open = False
            page.update()

        def cancel(e):
            cancel_event.set()
            page.run_task(close_dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Sign in with Twitch", size=16),
            title_padding=ft.Padding(20, 16, 20, 6),
            content=ft.Column([
                ft.ProgressRing(width=28, height=28),
                ft.Text("Starting sign-in...", size=13),
            ], width=360, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            content_padding=ft.Padding(20, 8, 20, 12),
            actions=[ft.TextButton("Cancel", on_click=cancel)],
            actions_padding=ft.Padding(12, 4, 12, 10),
        )
        page.show_dialog(dlg)
        page.update()

        async def show_code(flow):
            code = flow["user_code"]
            uri = flow.get("verification_uri") or "https://www.twitch.tv/activate"
            dlg.content = ft.Column([
                ft.Text("1. Open the Twitch page:", size=13),
                ft.FilledButton("Open twitch.tv/activate", icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda e: webbrowser.open(uri)),
                ft.Container(height=6),
                ft.Text("2. Enter this code:", size=13),
                ft.Text(code, size=30, weight=ft.FontWeight.BOLD, font_family="Consolas",
                        color=ft.Colors.PURPLE_300, text_align=ft.TextAlign.CENTER),
                ft.Container(height=6),
                ft.Text("Waiting for you to authorize...", size=12,
                        color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
            ], width=360, spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            page.update()

        async def fail(err):
            dlg.content = ft.Column([
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED_400, size=28),
                ft.Text(err or "Sign-in failed.", size=13, text_align=ft.TextAlign.CENTER),
            ], width=360, spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            dlg.actions = [ft.TextButton("Close", on_click=lambda e: page.run_task(close_dlg))]
            page.update()

        async def done(tokens, info):
            auth = dict(bot_config.get("TWITCH_AUTH") or {})
            auth[account_key] = {
                "login": info["login"],
                "display_name": info["display_name"],
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
            }
            bot_config["TWITCH_AUTH"] = auth
            bot_config.save()
            sync_fields_from_auth()
            refresh_account_ui()
            dlg.open = False
            page.update()
            snack(page, f"Signed in as @{info['login']}")

        def worker():
            try:
                flow = start_device_flow()
            except Exception as e:
                page.run_task(fail, str(e))
                return
            page.run_task(show_code, flow)
            try:
                tokens = poll_for_token(flow["device_code"], flow.get("interval", 5), cancel_event)
            except Exception as e:
                if not cancel_event.is_set():
                    page.run_task(fail, str(e))
                return
            try:
                info = get_user_info(tokens["access_token"])
            except Exception:
                info = None
            if not info:
                page.run_task(fail, "Could not fetch account info.")
                return
            page.run_task(done, tokens, info)

        threading.Thread(target=worker, daemon=True).start()

    btn_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding(20, 10, 20, 10))
    st_btn = ft.FilledButton("Sign in with Twitch", icon=ft.Icons.LOGIN, style=btn_style,
                             on_click=lambda e: sign_in("streamer"))
    st_out = ft.OutlinedButton("Sign out", icon=ft.Icons.LOGOUT, style=btn_style,
                               on_click=lambda e: sign_out("streamer"))
    bot_btn = ft.FilledButton("Sign in with Twitch", icon=ft.Icons.LOGIN, style=btn_style,
                              on_click=lambda e: sign_in("bot"))
    bot_out = ft.OutlinedButton("Sign out", icon=ft.Icons.LOGOUT, style=btn_style,
                                on_click=lambda e: sign_out("bot"))

    st_status = ft.Text("Not signed in", size=13, color=ft.Colors.GREY_500)
    bot_status = ft.Text("Not signed in", size=13, color=ft.Colors.GREY_500)

    def account_card(title, subtitle, status, btn, out):
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Text(title, weight=ft.FontWeight.BOLD, size=14, expand=True), status],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text(subtitle, size=12, color=ft.Colors.GREY_500),
                ft.Container(height=2),
                ft.Row([btn, out], spacing=8),
            ], spacing=6),
            bgcolor="#0D0D0F",
            border_radius=10,
            padding=14,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
        )

    refresh_account_ui()

    def save(e):
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
        page.update()
        snack(page, "Bot settings saved")

    btn_save = ft.FilledButton("Save Bot Settings", on_click=save, style=btn_style)

    return ft.Column([
        ft.Text("Bot Config", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("Connection settings for Twitch IRC.", color=ft.Colors.GREY_400, size=13),
        ft.Container(height=8),
        section_card("Sign in with Twitch", ft.Column([
            account_card("Streamer Account",
                         "The account whose channel the bot chats in. If no bot account is set, the bot also sends messages as this account.",
                         st_status, st_btn, st_out),
            account_card("Bot Account (optional)",
                         "By default the bot sends messages as you. Sign in a different account here to send messages as it instead.",
                         bot_status, bot_btn, bot_out),
            ft.Text("Saves automatically when you sign in.",
                    color=ft.Colors.GREY_500, size=12),
        ], spacing=6)),
        section_card("Manual Setup (advanced)", ft.Column([
            e_token,
            ft.Text("Only needed if you're not using sign-in above. Get a token at twitchtokengenerator.com (scopes: chat:read, chat:edit).",
                    color=ft.Colors.GREY_500, size=12),
            ft.Container(height=4),
            e_nick,
            ft.Text("The name of the account sending messages. Auto-filled when you sign in.",
                    color=ft.Colors.GREY_500, size=12),
            ft.Container(height=4),
            e_chan,
            ft.Text("The channel to join. Auto-filled when you sign in as the streamer.",
                    color=ft.Colors.GREY_500, size=12),
        ], spacing=4)),
        section_card("Messages", ft.Column([sw_conn, sw_disc], spacing=4),
                     "Auto-send messages when the bot connects or disconnects."),
        section_card("AI Activation", ft.Column([sw_tag, sw_cmd, sw_rep, sw_other_rep, ft.Container(height=4), e_cmds], spacing=4),
                     "Configure what triggers the AI to respond in chat."),
        ft.Row([btn_save], alignment=ft.MainAxisAlignment.END),
        ft.Container(height=20),
    ], expand=True, scroll=ft.ScrollMode.AUTO)


def build_ai_config_page(page, ai_config, ai_module):
    e_key = ft.TextField(label="Groq API Key", value=ai_config["api_key"], password=True, expand=True,
                         text_size=14, hint_text="gsk_...", border_radius=8, bgcolor="#0D0D0F")
    t_instr = ft.TextField(label="System Instruction", value=ai_config["system_instruction"],
                           multiline=True, min_lines=6, max_lines=12, expand=True, text_size=14,
                           border_radius=8, bgcolor="#0D0D0F")

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

        add_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding(14, 8, 14, 8))
        add_card = ft.Container(
            content=ft.Column([
                ft.Text("Add New Context", weight=ft.FontWeight.BOLD, size=14),
                ft.Row([e_user, e_info, ft.FilledButton("Add", on_click=on_add, style=add_style)], spacing=8),
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
                            ft.TextButton("Cancel", style=ft.ButtonStyle(padding=ft.Padding(14, 4, 14, 4)),
                                          on_click=lambda e2: setattr(dlg, 'open', False) or page.update()),
                            ft.TextButton("Delete", style=ft.ButtonStyle(padding=ft.Padding(14, 4, 14, 4)),
                                          on_click=do_delete),
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

    def save(e):
        ai_config["api_key"] = e_key.value.strip()
        ai_config["system_instruction"] = t_instr.value.strip()
        ai_config.save()
        ai_module._init_client()
        page.update()
        snack(page, "AI settings saved")

    btn_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), padding=ft.Padding(20, 10, 20, 10))
    btn_save = ft.FilledButton("Save AI Settings", on_click=save, style=btn_style)

    return ft.Column([
        ft.Text("AI Config", size=28, weight=ft.FontWeight.BOLD),
        ft.Text("Configure Groq interaction and personality.", color=ft.Colors.GREY_400, size=13),
        ft.Container(height=8),
        section_card("AI Brain", ft.Column([
            e_key,
            ft.Text("Get your free key at console.groq.com/keys", color=ft.Colors.GREY_500, size=12),
            ft.Container(height=4),
            t_instr,
        ], spacing=4)),
        section_card("Chatter Contexts", ctx_container,
                     "Add context about specific chatters so the bot can personalise responses."),
        ft.Row([btn_save], alignment=ft.MainAxisAlignment.END),
        ft.Container(height=20),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
