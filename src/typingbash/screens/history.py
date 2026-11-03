"""Historial de resultados en forma de tabla."""

from __future__ import annotations

import time

from ..keys import Key
from ..render import Screen
from ..stats import TestResult
from ..ui import blend, draw_box, format_number, panel_width, sparkline
from .base import View

ROWS_VISIBLE = 12
BASE_WIDTH, MIN_WIDTH = 70, 44


class HistoryView(View):
    hints = (("esc", "volver"), ("↑↓", "desplazar"), ("/", "comandos"))

    def __init__(self, app) -> None:
        super().__init__(app)
        self.offset = 0

    def on_enter(self) -> None:
        self.offset = 0

    def on_key(self, key: Key) -> None:
        entries = self._entries()
        if key.name in ("escape", "enter"):
            self.app.go_back()
        elif key.name == "char" and key.char.lower() in ("q", "h"):
            self.app.go_back()
        elif key.name == "down":
            self.offset = min(max(0, len(entries) - ROWS_VISIBLE), self.offset + 1)
        elif key.name == "up":
            self.offset = max(0, self.offset - 1)
        elif key.name == "page-down":
            self.offset = min(max(0, len(entries) - ROWS_VISIBLE), self.offset + ROWS_VISIBLE)
        elif key.name == "page-up":
            self.offset = max(0, self.offset - ROWS_VISIBLE)

    def _entries(self) -> list[TestResult]:
        return list(reversed(self.app.history.entries))

    def draw(self, screen: Screen) -> None:
        palette = self.palette
        entries = self._entries()
        width = panel_width(screen, self.size, BASE_WIDTH, MIN_WIDTH)
        # En grande caben todas las filas que dé la ventana, pero sin dejar
        # medio marco vacío si hay pocos resultados guardados.
        room = max(3, screen.height - 9)
        visible = max(3, min(blend(ROWS_VISIBLE, room, self.size), room, max(3, len(entries))))
        height = visible + 6
        left = (screen.width - width) // 2
        top = max(0, (screen.height - height) // 2 - 1)

        draw_box(
            screen, left, top, width, height, palette.style("border"),
            title="historial", title_style=palette.style("accent", bold=True),
        )

        if not entries:
            screen.put_center(top + height // 2, "aún no hay tests guardados", palette.style("muted"))
            screen.put_center(
                top + height // 2 + 1, "haz uno y aparecerá aquí", palette.style("border")
            )
            return

        columns = _columns(left + 3, width - 6)
        header = palette.style("muted")
        screen.put(columns["index"], top + 1, "#", header)
        screen.put(columns["wpm"] - 3, top + 1, "wpm", header)
        screen.put(columns["raw"] - 3, top + 1, "raw", header)
        screen.put(columns["acc"] - 4, top + 1, " acc", header)
        screen.put(columns["mode"], top + 1, "modo", header)
        screen.put(columns["when"], top + 1, "cuándo", header)
        screen.put(left + 3, top + 2, "─" * (width - 6), palette.style("border"))

        self.offset = max(0, min(self.offset, max(0, len(entries) - visible)))
        best = max(entry.wpm for entry in entries)

        for row, entry in enumerate(entries[self.offset : self.offset + visible]):
            y = top + 3 + row
            number = self.offset + row + 1
            is_best = entry.wpm >= best
            value_style = (
                palette.style("accent", bold=True) if is_best else palette.style("text")
            )
            screen.put(columns["index"], y, str(number), palette.style("border"))
            _put_right(screen, columns["wpm"], y, format_number(entry.wpm), value_style)
            _put_right(screen, columns["raw"], y, format_number(entry.raw_wpm), palette.style("muted"))
            _put_right(screen, columns["acc"], y, f"{entry.accuracy:.0f}%", palette.style("muted"))
            screen.put(columns["mode"], y, entry.describe_mode(), palette.style("muted"))
            screen.put(columns["when"], y, _relative_time(entry.timestamp), palette.style("border"))

        # Pie: tendencia de los últimos resultados.
        series = [entry.wpm for entry in reversed(entries[:30])]
        graph = sparkline(series, min(len(series), width - 22))
        if graph:
            y = top + height - 2
            screen.put(left + 3, y, "tendencia", palette.style("muted"))
            screen.put(left + 13, y, graph, palette.style("accent"))
            screen.put_right(
                y, left + width - 3, f"{len(entries)} tests", palette.style("border")
            )


def _columns(left: int, width: int) -> dict[str, int]:
    """Columnas repartidas en proporción al ancho útil de la tabla."""
    when = left + width - 14
    accuracy = left + round(width * 0.41)
    return {
        "index": left,
        "wpm": left + round(width * 0.17),
        "raw": left + round(width * 0.28),
        "acc": accuracy,
        "mode": max(accuracy + 5, min(left + round(width * 0.47), when - 14)),
        "when": when,
    }


def _put_right(screen: Screen, right: int, y: int, text: str, style: str) -> None:
    screen.put(right - len(text), y, text, style)


def _relative_time(timestamp: float) -> str:
    delta = max(0, time.time() - timestamp)
    if delta < 60:
        return "ahora"
    if delta < 3600:
        return f"hace {int(delta // 60)} min"
    if delta < 86400:
        return f"hace {int(delta // 3600)} h"
    if delta < 86400 * 7:
        return f"hace {int(delta // 86400)} d"
    return time.strftime("%d/%m/%y", time.localtime(timestamp))
