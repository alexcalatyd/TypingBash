"""Pantalla de ayuda: comandos y atajos, generados desde el registro."""

from __future__ import annotations

from ..commands import registry
from ..keys import Key
from ..render import Screen, truncate
from ..ui import draw_box, panel_height, panel_width
from .base import View

BASE_WIDTH, MIN_WIDTH = 74, 40
BASE_HEIGHT, MIN_HEIGHT = 22, 8

KEYBOARD = (
    ("enter", "empezar o repetir el test"),
    ("tab", "reiniciar con palabras nuevas"),
    ("esc", "volver al menú"),
    ("/", "abrir la línea de comandos"),
    ("retroceso", "borrar un carácter"),
    ("ctrl/alt + retroceso", "borrar la palabra entera"),
    ("↑ ↓", "moverse por listas e historial de comandos"),
    ("ctrl+c", "salir restaurando la terminal"),
)

GROUP_TITLES = {
    "modo": "modo de juego",
    "apariencia": "ajustes",
    "pantalla": "navegación",
    "general": "general",
}


class HelpView(View):
    hints = (("esc", "volver"), ("↑↓", "desplazar"), ("/", "comandos"))

    def __init__(self, app) -> None:
        super().__init__(app)
        self.offset = 0

    def on_enter(self) -> None:
        self.offset = 0

    def on_key(self, key: Key) -> None:
        if key.name in ("escape", "enter"):
            self.app.go_back()
        elif key.name == "char" and key.char.lower() == "q":
            self.app.go_back()
        elif key.name in ("down", "up"):
            lines = self._lines()
            self.offset = max(0, min(len(lines) - 1, self.offset + (1 if key.name == "down" else -1)))
        elif key.name in ("page-down", "page-up"):
            step = 8 if key.name == "page-down" else -8
            self.offset = max(0, self.offset + step)

    def _lines(self) -> list[tuple[str, str, str]]:
        """(tipo, izquierda, derecha) — tipo: 'title', 'row' o 'blank'."""
        lines: list[tuple[str, str, str]] = []
        grouped: dict[str, list] = {}
        for command in registry.all():
            grouped.setdefault(command.group, []).append(command)

        lines.append(("title", "comandos", ""))
        for group in ("modo", "apariencia", "pantalla", "general"):
            commands = grouped.get(group)
            if not commands:
                continue
            lines.append(("blank", "", ""))
            lines.append(("subtitle", GROUP_TITLES.get(group, group), ""))
            for command in sorted(commands, key=lambda c: c.name):
                alias = f"  ({', '.join('/' + a for a in command.aliases)})" if command.aliases else ""
                lines.append(("row", command.usage, command.summary + alias))

        lines.append(("blank", "", ""))
        lines.append(("title", "teclado", ""))
        lines.append(("blank", "", ""))
        for key, description in KEYBOARD:
            lines.append(("row", key, description))
        return lines

    def draw(self, screen: Screen) -> None:
        palette = self.palette
        lines = self._lines()
        width = panel_width(screen, self.size, BASE_WIDTH, MIN_WIDTH)
        # Nunca más alto que el contenido: un marco medio vacío se ve peor.
        height = min(
            len(lines) + 2,
            panel_height(screen, self.size, BASE_HEIGHT, MIN_HEIGHT),
            screen.height - 3,
        )
        height = max(MIN_HEIGHT, height)
        left = (screen.width - width) // 2
        top = max(0, (screen.height - height) // 2 - 1)

        draw_box(
            screen, left, top, width, height, palette.style("border"),
            title="ayuda", title_style=palette.style("accent", bold=True),
        )

        inner_height = height - 2
        self.offset = max(0, min(self.offset, max(0, len(lines) - inner_height)))
        window = lines[self.offset : self.offset + inner_height]

        label_width = 26
        for offset, (kind, left_text, right_text) in enumerate(window):
            y = top + 1 + offset
            if kind == "blank":
                continue
            if kind == "title":
                screen.put(left + 3, y, left_text.upper(), palette.style("accent", bold=True))
                continue
            if kind == "subtitle":
                screen.put(left + 3, y, left_text, palette.style("muted"))
                continue
            screen.put(left + 3, y, truncate(left_text, label_width), palette.style("text"))
            screen.put(
                left + 3 + label_width, y,
                truncate(right_text, width - label_width - 6), palette.style("muted"),
            )

        if len(lines) > inner_height:
            screen.put_right(
                top + height - 1, left + width - 3,
                f" {self.offset + 1}/{len(lines) - inner_height + 1} ",
                palette.style("border"),
            )
