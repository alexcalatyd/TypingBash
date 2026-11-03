"""Menú principal."""

from __future__ import annotations

import time

from ..keys import Key
from ..render import Screen
from ..ui import LOGO_HEIGHT, draw_logo, format_number
from ..words import language_name
from .base import View

TIME_PRESETS = (15, 30, 60, 120)
WORD_PRESETS = (10, 25, 50, 100)
REVEAL_SECONDS = 0.45

# Alto del menú clásico (logo incluido) y separación máxima entre bloques
# según el tamaño de interfaz: en grande el menú se estira para llenar más.
MENU_BLOCK = 11
MAX_SPREAD = {"small": 0, "medium": 1, "large": 2}
SPREAD_GAPS = 3  # huecos que crecen: bajo el logo, tras los preajustes y tras el resumen


class MenuView(View):
    hints = (
        ("enter", "empezar"),
        ("m", "modo"),
        ("1-4", "preajuste"),
        ("s", "ajustes"),
        ("h", "historial"),
        ("/", "comandos"),
    )

    def __init__(self, app) -> None:
        super().__init__(app)
        self._shown_at = 0.0

    def on_enter(self) -> None:
        self._shown_at = time.monotonic()

    def frame_interval(self) -> float | None:
        if self.app.config.animations and time.monotonic() - self._shown_at < REVEAL_SECONDS:
            return 1 / 30
        return None

    # ------------------------------------------------------------------ teclas

    def on_key(self, key: Key) -> None:
        config = self.app.config
        if key.name == "enter":
            self.app.start_test()
        elif key.name == "char":
            char = key.char.lower()
            if char == "q":
                self.app.quit()
            elif char == "s":
                self.app.show_settings()
            elif char == "h":
                self.app.show_history()
            elif char == "e":
                self.app.show_stats()
            elif char == "m":
                config.mode = "words" if config.mode == "time" else "time"
                self.app.save_config()
            elif char in "1234":
                self._apply_preset(int(char) - 1)
        elif key.name in ("left", "right"):
            self._cycle_preset(-1 if key.name == "left" else 1)

    def _presets(self) -> tuple[int, ...]:
        return TIME_PRESETS if self.app.config.mode == "time" else WORD_PRESETS

    def _current_value(self) -> int:
        config = self.app.config
        return config.time_seconds if config.mode == "time" else config.word_count

    def _apply_preset(self, index: int) -> None:
        presets = self._presets()
        if not 0 <= index < len(presets):
            return
        self._set_value(presets[index])

    def _cycle_preset(self, direction: int) -> None:
        presets = self._presets()
        current = self._current_value()
        # Si el valor actual no es un preajuste, empezamos por el más cercano.
        if current in presets:
            index = (presets.index(current) + direction) % len(presets)
        else:
            index = min(range(len(presets)), key=lambda i: abs(presets[i] - current))
        self._set_value(presets[index])

    def _set_value(self, value: int) -> None:
        config = self.app.config
        if config.mode == "time":
            config.time_seconds = value
        else:
            config.word_count = value
        self.app.save_config()

    # ------------------------------------------------------------------ dibujo

    def draw(self, screen: Screen) -> None:
        palette = self.palette
        compact = screen.height < 22

        reveal = 1.0
        if self.app.config.animations:
            elapsed = time.monotonic() - self._shown_at
            reveal = min(1.0, elapsed / REVEAL_SECONDS)

        logo_height = 1 if screen.width < 50 or compact else LOGO_HEIGHT
        spread = self._spread(screen, logo_height)
        block = logo_height + MENU_BLOCK + spread * SPREAD_GAPS
        top = max(1, (screen.height - block) // 2)

        if logo_height == 1:
            screen.put_center(top, "T Y P I N G", palette.style("accent", bold=True))
            y = top + 2
        else:
            y = draw_logo(screen, top, palette, reveal) + 1

        screen.put_center(y, "typingbash · test de mecanografía en la terminal", palette.style("muted"))
        y += 2 + spread

        y = self._draw_presets(screen, y)
        y += 1 + spread
        self._draw_summary(screen, y)
        y += 2 + spread
        self._draw_records(screen, y)

    def _spread(self, screen: Screen, logo_height: int) -> int:
        """Separación extra entre bloques, hasta donde llegue la ventana."""
        limit = MAX_SPREAD.get(self.size, 0)
        room = screen.height - 3 - logo_height - MENU_BLOCK
        return max(0, min(limit, room // SPREAD_GAPS))

    def _draw_presets(self, screen: Screen, y: int) -> int:
        palette = self.palette
        config = self.app.config

        modes = (("tiempo", "time"), ("palabras", "words"))
        parts = []
        for label, value in modes:
            parts.append((label, value == config.mode))
        rendered_width = sum(len(label) + 2 for label, _ in parts) + 2 * (len(parts) - 1)
        x = (screen.width - rendered_width) // 2
        for index, (label, active) in enumerate(parts):
            if index:
                x = screen.put(x, y, "  ", "")
            style = (
                palette.style("accent", bold=True) if active else palette.style("border")
            )
            x = screen.put(x, y, f" {label} ", style)

        y += 1
        presets = self._presets()
        current = self._current_value()
        labels = [str(value) for value in presets]
        width = sum(len(label) + 2 for label in labels) + 2 * (len(labels) - 1)
        x = (screen.width - width) // 2
        for index, (label, value) in enumerate(zip(labels, presets)):
            if index:
                x = screen.put(x, y, "  ", "")
            active = value == current
            style = (
                palette.style("accent", reverse=True)
                if active
                else palette.style("pending")
            )
            x = screen.put(x, y, f" {label} ", style)

        if current not in presets:
            y += 1
            screen.put_center(
                y, f"personalizado: {current}", palette.style("muted")
            )
        return y + 1

    def _draw_summary(self, screen: Screen, y: int) -> None:
        config = self.app.config
        palette = self.palette
        pieces = [
            config.describe_mode(),
            language_name(config.language).lower(),
            config.difficulty,
            config.theme,
        ]
        text = "  ·  ".join(pieces)
        screen.put_center(y, text, palette.style("muted"))

    def _draw_records(self, screen: Screen, y: int) -> None:
        history = self.app.history
        palette = self.palette
        if not len(history):
            screen.put_center(
                y, "todavía no hay resultados: pulsa enter y empieza",
                palette.style("border"),
            )
            return

        best = history.best_wpm()
        today = history.best_today()
        average = history.average_wpm(10)

        cells = []
        if best:
            cells.append((format_number(best.wpm), "récord wpm"))
        if today:
            cells.append((format_number(today.wpm), "hoy"))
        if average:
            cells.append((format_number(average), "media 10"))
        cells.append((str(len(history)), "tests"))

        gap = 4
        width = sum(max(len(value), len(label)) for value, label in cells)
        width += gap * (len(cells) - 1)
        x = max(0, (screen.width - width) // 2)
        for index, (value, label) in enumerate(cells):
            if index:
                x += gap
            cell_width = max(len(value), len(label))
            screen.put(
                x + (cell_width - len(value)) // 2, y, value,
                palette.style("text", bold=True),
            )
            screen.put(
                x + (cell_width - len(label)) // 2, y + 1, label, palette.style("muted")
            )
            x += cell_width
