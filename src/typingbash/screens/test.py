"""Pantalla del test: el sitio donde de verdad se escribe."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..engine import Phase, TypingTest
from ..keys import Key
from ..render import Screen
from ..ui import (
    BIG_GLYPH_HEIGHT,
    big_width,
    draw_progress,
    format_number,
    format_seconds,
    panel_width,
    render_big,
)
from .base import View

# La caja de texto se adapta a la terminal: en tamaño pequeño conserva el tope
# clásico para que las líneas no se hagan incómodas de seguir con la vista; en
# grande llega hasta los márgenes.
MAX_TEXT_WIDTH = 120
MIN_TEXT_WIDTH = 30

# Alturas a partir de las cuales caben más líneas de texto y el contador
# grande. Por debajo se usa la disposición compacta de siempre.
HEIGHT_FOR_4_LINES = 26
HEIGHT_FOR_5_LINES = 34
HEIGHT_FOR_BIG_COUNTER = 26
WIDTH_FOR_BIG_COUNTER = 70

# Máximo de líneas de texto a la vez, por tamaño de interfaz.
MAX_LINES = {"small": 5, "medium": 6, "large": 8}
# Cada cuántas filas de terminal se gana una línea más, por tamaño.
LINE_STEP = {"small": 8, "medium": 7, "large": 5}
# Con la interfaz grande y sitio de sobra, la cifra del cronómetro va al doble.
HEIGHT_FOR_HUGE_COUNTER = 34
WIDTH_FOR_HUGE_COUNTER = 100
MAX_GAP = 6  # tope de aire entre contador, texto y barra

COUNTDOWN_STEP = 0.28  # duración de cada número de la cuenta atrás
CARET_BLINK = 0.53


@dataclass(frozen=True)
class Layout:
    """Medidas ya resueltas del fotograma, para no recalcularlas por partes."""

    left: int
    width: int
    lines: int
    top: int
    text_top: int
    progress_y: int
    big_counter: bool
    counter_scale: int  # multiplicador de la cifra grande (1 o 2)


class TestView(View):
    hints = (("tab", "reiniciar"), ("esc", "menú"), ("/", "comandos"), ("ctrl+c", "salir"))

    def __init__(self, app, test: TypingTest) -> None:
        super().__init__(app)
        self.test = test
        self._countdown_until: float | None = None
        self._countdown_total = 0.0
        self._finished_handled = False

    # ------------------------------------------------------------ ciclo de vida

    def on_enter(self) -> None:
        config = self.app.config
        if config.countdown and config.animations:
            self._countdown_total = COUNTDOWN_STEP * 4  # 3, 2, 1 y "¡ya!"
            self._countdown_until = time.monotonic() + self._countdown_total

    @property
    def counting_down(self) -> bool:
        return self._countdown_until is not None and time.monotonic() < self._countdown_until

    def frame_interval(self) -> float | None:
        if self.counting_down:
            return 1 / 30
        if self.test.phase is Phase.RUNNING:
            return 1 / 20  # suficiente para un cronómetro con un decimal
        return 1 / 6  # parpadeo del cursor mientras espera

    def tick(self, now: float) -> None:
        if self.counting_down:
            return
        self.test.tick()
        if self.test.is_finished and not self._finished_handled:
            self._finished_handled = True
            self.app.finish_test(self.test)

    # ------------------------------------------------------------------ teclas

    def on_key(self, key: Key) -> None:
        if self.counting_down:
            # Cualquier tecla se salta la cuenta atrás sin colarse en el test.
            self._countdown_until = None
            return
        if self.test.is_finished:
            return

        if key.name == "char":
            was_error = self.test.has_error_in_buffer
            self.test.type_char(key.char)
            if not was_error and self.test.has_error_in_buffer:
                self.app.sound.play("error")
        elif key.name == "combining":
            self.test.compose_last(key.char)
        elif key.name == "backspace":
            self.test.backspace()
        elif key.name in ("delete-word", "delete-line"):
            self.test.backspace(whole_word=True)
        elif key.name == "tab":
            self.app.start_test()
        elif key.name == "escape":
            self.app.show_menu()

    # ------------------------------------------------------------------ dibujo

    def _layout(self, screen: Screen) -> Layout:
        """Reparte el espacio disponible entre contador, texto y barra."""
        size = self.size
        width = panel_width(screen, size, MAX_TEXT_WIDTH, MIN_TEXT_WIDTH)
        left = (screen.width - width) // 2

        lines = 3
        if screen.height >= HEIGHT_FOR_4_LINES:
            extra = (screen.height - HEIGHT_FOR_4_LINES) // LINE_STEP.get(size, 8)
            lines = min(MAX_LINES.get(size, 5), 4 + extra)

        big = (
            self.app.config.big_counter
            and screen.height >= HEIGHT_FOR_BIG_COUNTER
            and screen.width >= WIDTH_FOR_BIG_COUNTER
        )
        scale = (
            2
            if big
            and size == "large"
            and screen.height >= HEIGHT_FOR_HUGE_COUNTER
            and screen.width >= WIDTH_FOR_HUGE_COUNTER
            else 1
        )
        header = BIG_GLYPH_HEIGHT * scale if big else 1
        # En ventanas altas se separan más los bloques: llena mejor la pantalla
        # sin amontonar más texto del que da tiempo a escribir.
        gap = 2 if screen.height >= HEIGHT_FOR_4_LINES else 1
        if size == "large" and screen.height >= HEIGHT_FOR_5_LINES:
            gap = 3

        # Las dos filas de abajo son de la aplicación (avisos y atajos).
        budget = screen.height - 2
        if size == "large":
            # Reparte el hueco sobrante entre los dos espacios, dejando un
            # margen arriba y abajo: así el bloque abarca casi toda la ventana.
            slack = (budget - 4 - header - lines - 1) // 2
            gap = max(gap, min(MAX_GAP, slack))

        block = header + gap + lines + gap + 1
        while block > budget and (lines > 3 or gap > 1):
            if gap > 1:
                gap -= 1
            else:
                lines -= 1
            block = header + gap + lines + gap + 1

        top = max(0, (budget - block) // 2)
        text_top = top + header + gap
        return Layout(
            left=left, width=width, lines=lines, top=top,
            text_top=text_top, progress_y=text_top + lines + gap, big_counter=big,
            counter_scale=scale,
        )

    def draw(self, screen: Screen) -> None:
        layout = self._layout(screen)

        if self.counting_down:
            # La cuenta atrás ocupa el bloque entero: sin palabras ni barra,
            # para que el número se lea de un vistazo.
            self._draw_counter(screen, layout)
            self._draw_countdown(screen, layout)
            return

        self._draw_counter(screen, layout)
        self._draw_words(screen, layout)
        draw_progress(
            screen, layout.left, layout.progress_y, layout.width,
            self.test.progress, self.palette,
        )

    # -------------------------------------------------------------- contador

    def _counter_text(self) -> tuple[str, str]:
        """Cifra principal y su unidad, según el modo."""
        test = self.test
        if test.mode == "time":
            return format_seconds(test.remaining_seconds), "s"
        return str(min(test.index, test.word_count)), f"/ {test.word_count} palabras"

    def _live_metrics(self) -> list[tuple[str, str]]:
        test = self.test
        config = self.app.config
        metrics: list[tuple[str, str]] = []
        if config.live_wpm:
            value = format_number(test.live_wpm()) if test.phase is not Phase.READY else "—"
            metrics.append((value, "wpm"))
        if config.live_accuracy:
            value = f"{test.live_accuracy():.0f}%" if test.stats.total_keystrokes else "—"
            metrics.append((value, "acc"))
        return metrics

    def _draw_counter(self, screen: Screen, layout: Layout) -> None:
        if layout.big_counter:
            self._draw_big_counter(screen, layout)
        else:
            self._draw_small_counter(screen, layout)

    def _draw_small_counter(self, screen: Screen, layout: Layout) -> None:
        palette = self.palette
        y = layout.top
        counter, unit = self._counter_text()
        x = screen.put(layout.left, y, counter, palette.style("accent", bold=True))
        screen.put(x, y, unit if unit == "s" else " " + unit, palette.style("muted"))
        self._draw_metrics(screen, layout, y)

    def _draw_big_counter(self, screen: Screen, layout: Layout) -> None:
        palette = self.palette
        counter, unit = self._counter_text()
        style = palette.style("accent", bold=True)

        scale = layout.counter_scale
        rows = render_big(counter, scale)
        for offset, row in enumerate(rows):
            screen.put(layout.left, layout.top + offset, row, style)

        # La unidad va pegada al pie de la cifra, en pequeño.
        base = layout.top + len(rows) - 1
        screen.put(
            layout.left + big_width(counter, scale) + 2, base, unit, palette.style("muted")
        )
        # Las métricas se alinean con el centro vertical del número.
        self._draw_metrics(screen, layout, layout.top + len(rows) // 2)

    def _draw_metrics(self, screen: Screen, layout: Layout, y: int) -> None:
        """Velocidad y precisión en vivo, alineadas a la derecha del bloque."""
        palette = self.palette
        metrics = self._live_metrics()
        if not metrics:
            return
        rendered = "   ".join(f"{value} {label}" for value, label in metrics)
        x = layout.left + layout.width - len(rendered)
        for index, (value, label) in enumerate(metrics):
            if index:
                x = screen.put(x, y, "   ", "")
            x = screen.put(x, y, value, palette.style("text", bold=True))
            x = screen.put(x, y, " " + label, palette.style("muted"))

    # ----------------------------------------------------------------- texto

    def _draw_words(self, screen: Screen, layout: Layout) -> None:
        lines = self._wrap(layout.width)
        current_line = self._line_of(lines, self.test.index)
        # La línea activa se mantiene en el centro del bloque visible.
        start = max(0, min(current_line - 1, len(lines) - layout.lines))

        for row in range(layout.lines):
            index = start + row
            if index >= len(lines):
                break
            self._draw_line(screen, layout.left, layout.text_top + row, lines[index])

        if self.test.phase is Phase.READY:
            hint = "empieza a escribir para arrancar el cronómetro"
            screen.put_center(
                layout.text_top + layout.lines, hint, self.palette.style("border")
            )

    def _draw_line(self, screen: Screen, left: int, y: int, indices: list[int]) -> None:
        palette = self.palette
        pending = palette.style("pending")
        correct = palette.style("text")
        wrong = palette.style("incorrect")
        extra = palette.style("extra")

        show_caret = self._caret_visible()
        caret_style = palette.style(
            "incorrect" if (self.app.config.stop_on_error and self.test.has_error_in_buffer)
            else "accent",
            reverse=True,
        )

        x = left
        for slot, position in enumerate(indices):
            if slot:
                x += 1  # separación entre palabras, nunca al principio de línea
            target = self.test.words[position]
            is_current = position == self.test.index

            if position < self.test.index:
                typed = (
                    self.test.typed_words[position]
                    if position < len(self.test.typed_words)
                    else ""
                )
            elif is_current:
                typed = self.test.buffer
            else:
                typed = ""

            caret_at = len(typed) if is_current and show_caret else -1

            for i, char in enumerate(target):
                style = pending
                if i < len(typed):
                    style = correct if typed[i] == target[i] else wrong
                if i == caret_at:
                    style = caret_style
                screen.put(x, y, char, style)
                x += 1

            # Caracteres de más: se pintan a continuación, en rojo apagado.
            if len(typed) > len(target):
                for i in range(len(target), len(typed)):
                    style = caret_style if i == caret_at else extra
                    screen.put(x, y, typed[i], style)
                    x += 1

            if caret_at >= len(typed) and caret_at >= 0 and len(typed) >= len(target):
                # El cursor cae justo después de la palabra: se marca el hueco.
                screen.put(x, y, " ", caret_style)

    def _caret_visible(self) -> bool:
        if self.test.phase is not Phase.READY:
            return True  # sólido mientras se escribe: parpadear distrae
        return int(time.monotonic() / CARET_BLINK) % 2 == 0

    def _wrap(self, width: int) -> list[list[int]]:
        """Reparte los índices de palabra en líneas del ancho disponible."""
        limit = min(len(self.test.words), self.test.index + 250)
        lines: list[list[int]] = []
        current: list[int] = []
        used = 0
        for position in range(limit):
            length = self._display_width(position)
            needed = length if not current else length + 1
            if current and used + needed > width:
                lines.append(current)
                current, used = [], 0
                needed = length
            current.append(position)
            used += needed
        if current:
            lines.append(current)
        return lines or [[]]

    def _display_width(self, position: int) -> int:
        target = self.test.words[position]
        if position == self.test.index:
            return max(len(target), len(self.test.buffer))
        if position < len(self.test.typed_words):
            return max(len(target), len(self.test.typed_words[position]))
        return len(target)

    @staticmethod
    def _line_of(lines: list[list[int]], index: int) -> int:
        for number, indices in enumerate(lines):
            if indices and indices[0] <= index <= indices[-1]:
                return number
        return max(0, len(lines) - 1)

    # ------------------------------------------------------------ cuenta atrás

    def _draw_countdown(self, screen: Screen, layout: Layout) -> None:
        assert self._countdown_until is not None
        remaining = self._countdown_until - time.monotonic()
        step = max(0, min(3, int(remaining / COUNTDOWN_STEP)))
        palette = self.palette
        style = palette.style("accent", bold=True)

        center_y = layout.text_top + layout.lines // 2
        if step == 0:
            screen.put_center(center_y, "¡ y a !", style)
            return

        rows = render_big(str(step), layout.counter_scale)
        start_y = max(0, center_y - len(rows) // 2)
        for offset, row in enumerate(rows):
            if start_y + offset < screen.height - 2:
                screen.put_center(start_y + offset, row, style)
