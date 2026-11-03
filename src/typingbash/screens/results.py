"""Pantalla de resultados, con animación de entrada y celebración de récords."""

from __future__ import annotations

import time

from ..history import Records
from ..keys import Key
from ..render import Screen
from ..stats import TestResult
from ..ui import (
    BOX_DOUBLE,
    clear_box,
    draw_box,
    format_duration,
    format_number,
    panel_width,
    sparkline,
)
from .base import View

REVEAL_SECONDS = 0.5
CELEBRATION_SECONDS = 2.2
BOX_WIDTH = 58
MIN_BOX_WIDTH = 34

_MESSAGES = (
    (0, "cada test cuenta: la constancia es la que sube el número"),
    (30, "buen ritmo, sigue soltando los dedos"),
    (50, "muy sólido, ya se nota el automatismo"),
    (70, "excelente, estás en territorio rápido"),
    (90, "impresionante, esto ya es nivel de concurso"),
)


class ResultsView(View):
    hints = (
        ("enter", "repetir"),
        ("tab", "otro test"),
        ("esc", "menú"),
        ("h", "historial"),
        ("/", "comandos"),
    )

    def __init__(self, app, result: TestResult, records: Records) -> None:
        super().__init__(app)
        self.result = result
        self.records = records
        self._entered_at = 0.0

    def on_enter(self) -> None:
        self._entered_at = time.monotonic()

    def frame_interval(self) -> float | None:
        if not self.app.config.animations:
            return None
        limit = CELEBRATION_SECONDS if self.records.any else REVEAL_SECONDS
        if time.monotonic() - self._entered_at < limit:
            return 1 / 30
        return None

    def _reveal(self) -> float:
        """0 → 1 con desaceleración, para que los números "aterricen"."""
        if not self.app.config.animations:
            return 1.0
        progress = min(1.0, (time.monotonic() - self._entered_at) / REVEAL_SECONDS)
        return 1.0 - (1.0 - progress) ** 3

    # ------------------------------------------------------------------ teclas

    def on_key(self, key: Key) -> None:
        if key.name in ("enter", "tab"):
            self.app.start_test()
        elif key.name == "escape":
            self.app.show_menu()
        elif key.name == "char":
            char = key.char.lower()
            if char == "r":
                self.app.start_test()
            elif char == "h":
                self.app.show_history()
            elif char == "q":
                self.app.quit()
            elif char == "e":
                self.app.show_stats()

    # ------------------------------------------------------------------ dibujo

    def draw(self, screen: Screen) -> None:
        width = panel_width(screen, self.size, BOX_WIDTH, MIN_BOX_WIDTH)
        celebrating = self.records.any

        # Presupuesto de altura: las dos últimas filas son de la aplicación
        # (avisos y barra de atajos), así que no se pueden invadir. Lo que no
        # quepa se cede por orden de importancia: primero el gráfico, luego
        # las filas secundarias y por último el marco de la celebración.
        budget = screen.height - 2
        celebration_rows = 4 if celebrating else 0
        rows = self._rows(compact=False)
        show_graph = bool(self.result.wpm_series)

        def block(row_count: int, graph: bool, celebration: int) -> int:
            # celebración + [borde, hueco, titular (2), hueco, separador,
            # filas, (hueco + gráfico), borde] + mensaje motivacional
            return celebration + row_count + 7 + (2 if graph else 0) + 1

        if block(len(rows), show_graph, celebration_rows) > budget:
            show_graph = False
        if block(len(rows), show_graph, celebration_rows) > budget:
            rows = self._rows(compact=True)
        if celebrating and block(len(rows), show_graph, celebration_rows) > budget:
            celebration_rows = 2  # banner de una línea, sin marco

        height = block(len(rows), show_graph, 0) - 1  # solo la caja
        top = max(0, (budget - block(len(rows), show_graph, celebration_rows)) // 2)

        if celebrating:
            self._draw_celebration(screen, top, width, compact=celebration_rows < 4)
            top += celebration_rows

        left = (screen.width - width) // 2
        clear_box(screen, left, top, width, height)
        draw_box(
            screen, left, top, width, height, self.palette.style("border"),
            title="resultados", title_style=self.palette.style("accent", bold=True),
        )

        reveal = self._reveal()
        self._draw_headline(screen, left, top + 2, width, reveal)
        screen.put(
            left + 3, top + 5, "─" * (width - 6), self.palette.style("border")
        )
        self._draw_rows(screen, left, top + 6, width, rows)
        if show_graph:
            self._draw_graph(screen, left, top + height - 2, width, reveal)

        message = _message_for(self.result.wpm)
        screen.put_center(top + height, message, self.palette.style("border"))

    def _draw_headline(self, screen: Screen, left: int, y: int, width: int, reveal: float) -> None:
        palette = self.palette
        wpm_value = format_number(self.result.wpm * reveal)
        accuracy_value = f"{self.result.accuracy * reveal:.1f}%"

        half = width // 2
        for offset, (value, label) in enumerate(
            ((wpm_value, "wpm"), (accuracy_value, "acc"))
        ):
            column = left + offset * half
            center = column + half // 2
            screen.put(
                center - len(value) // 2, y, value, palette.style("accent", bold=True)
            )
            screen.put(center - len(label) // 2, y + 1, label, palette.style("muted"))

    def _rows(self, compact: bool = False) -> list[tuple[str, str]]:
        result = self.result
        chars = result.chars
        words = result.words
        essential = [
            ("raw", f"{format_number(result.raw_wpm)} wpm"),
            ("caracteres", f"{chars.correct} / {chars.incorrect} / {chars.total}"),
            ("palabras", f"{words.correct} / {words.incorrect} / {words.total}"),
            ("tiempo", format_duration(result.duration)),
            ("score", str(result.score)),
        ]
        if compact:
            return essential
        return essential[:2] + [
            ("extra · omitidos", f"{chars.extra} / {chars.missed}"),
            essential[2],
            ("consistencia", f"{result.consistency:.0f}%"),
            essential[3],
            ("modo", f"{result.describe_mode()} · {result.difficulty} · {result.language}"),
            essential[4],
        ]

    def _draw_rows(self, screen: Screen, left: int, y: int, width: int, rows) -> None:
        palette = self.palette
        label_style = palette.style("muted")
        value_style = palette.style("text")
        for offset, (label, value) in enumerate(rows):
            screen.put(left + 4, y + offset, label, label_style)
            screen.put_right(y + offset, left + width - 4, value, value_style)

    def _draw_graph(self, screen: Screen, left: int, y: int, width: int, reveal: float) -> None:
        series = self.result.wpm_series
        palette = self.palette
        available = width - 12
        if not series or available < 8:
            return
        graph = sparkline(series, available)
        visible = graph[: max(1, int(len(graph) * reveal))]
        screen.put(left + 4, y, "ritmo", palette.style("muted"))
        screen.put(left + 10, y, visible, palette.style("accent"))

    # ------------------------------------------------------------ celebración

    def _draw_celebration(self, screen: Screen, top: int, width: int, compact: bool) -> None:
        palette = self.palette
        left = (screen.width - width) // 2
        elapsed = time.monotonic() - self._entered_at
        animating = self.app.config.animations and elapsed < CELEBRATION_SECONDS

        if not compact:
            clear_box(screen, left, top, width, 3)
            draw_box(
                screen, left, top, width, 3, palette.style("accent", bold=True),
                chars=BOX_DOUBLE,
            )

        if self.records.wpm:
            headline = f"¡NUEVO RÉCORD!   {format_number(self.result.wpm)} wpm"
            if self.records.previous_wpm:
                headline += f"   (antes {format_number(self.records.previous_wpm)})"
        elif self.records.accuracy:
            headline = f"¡RÉCORD DE PRECISIÓN!   {self.result.accuracy:.1f}%"
        else:
            headline = f"¡RÉCORD DE PUNTUACIÓN!   {self.result.score}"

        screen.put_center(top if compact else top + 1, headline, palette.style("accent", bold=True))

        if animating and not compact:
            # Destellos que recorren el marco de izquierda a derecha.
            phase = elapsed * 14
            for index in range(4):
                position = int(phase + index * 7) % (width - 4)
                char = "✦" if (index + int(phase)) % 2 == 0 else "✧"
                screen.put(left + 2 + position, top, char, palette.style("warning", bold=True))


def _message_for(wpm_value: float) -> str:
    message = _MESSAGES[0][1]
    for threshold, text in _MESSAGES:
        if wpm_value >= threshold:
            message = text
    return message
