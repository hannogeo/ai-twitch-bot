import datetime

import flet as ft


def section_card(title, content, description=None, expand=False):
    rows = [
        ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
    ]
    if description:
        rows.append(ft.Text(description, size=12, color=ft.Colors.GREY_400))
    rows.append(ft.Divider(height=1, color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
    rows.append(content)
    return ft.Container(
        content=ft.Column(rows, spacing=8, expand=expand, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        bgcolor="#1C1C1E",
        border_radius=12,
        padding=16,
        margin=ft.Margin(0, 0, 0, 12),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.06, ft.Colors.WHITE)),
        expand=expand,
    )


def snack(page, text):
    page.show_dialog(ft.SnackBar(ft.Text(text), duration=2000))


class LogManager:
    def __init__(self, page):
        self.page = page
        self.lines = []
        self.container = ft.Container(
            content=ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            bgcolor="#0D0D0F",
            border=ft.Border.all(1, ft.Colors.with_opacity(0.15, ft.Colors.WHITE)),
            border_radius=8,
            expand=True,
            padding=ft.Padding(12, 12, 12, 10),
            margin=ft.Margin(0, 4, 0, 0),
        )

    def write(self, text, color=None):
        if color is None:
            color = ft.Colors.WHITE_70
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.lines.append((f"[{ts}] {text}", color))
        if len(self.lines) > 500:
            self.lines[:] = self.lines[-500:]

        async def _update():
            col = self.container.content
            col.controls = [ft.Text(t, color=c, size=13) for t, c in self.lines]
            col.update()

        self.page.run_task(_update)
