"""Resumen de estadísticas: la sesión actual y el acumulado histórico."""

from __future__ import annotations

from ..keys import Key
from ..render import Screen, truncate
from ..stats import TestResult
from ..ui import draw_box, format_number, panel_width, sparkline
from .base import View

BASE_WIDTH, MIN_WIDTH = 64, 44


class StatsView(View):
    hints = (("esc", "volver"), ("h", "historial"), ("/", "comandos"))

    def on_key(self, key: Key) -> None:
        if key.name in ("escape", "enter"):
            self.app.go_back()
        elif key.name == "char":
            char = key.char.lower()
            if char in ("q", "e"):
                self.app.go_back()
            elif char == "h":
                self.app.show_history()

    def draw(self, screen: Screen) -> None:
        palette = self.palette
        history = self.app.history
        session = self.app.session

        width = panel_width(screen, self.size, BASE_WIDTH, MIN_WIDTH)
        rows = self._rows()
        # En tamaño grande las filas van con aire entre ellas, si la ventana da.
        step = 2 if self.size == "large" and screen.height >= len(rows) * 2 + 7 else 1
        content = len(rows) * step - (step - 1)
        height = min(content + 6, screen.height - 2)
        left = (screen.width - width) // 2
        top = max(0, (screen.height - height) // 2 - 1)

        draw_box(
            screen, left, top, width, height, palette.style("border"),
            title="estadísticas", title_style=palette.style("accent", bold=True),
        )

        visible = max(1, (height - 4 + step - 1) // step)
        for index, (kind, label, value) in enumerate(rows[:visible]):
            y = top + 2 + index * step
            if kind == "title":
                screen.put(left + 3, y, label, palette.style("accent", bold=True))
            elif kind == "blank":
                pass
            else:
                screen.put(left + 4, y, truncate(label, width - 22), palette.style("muted"))
                screen.put_right(y, left + width - 4, value, palette.style("text"))

        end_y = top + 2 + min(len(rows), visible) * step
        series = [entry.wpm for entry in history.entries[-40:]]
        graph = sparkline(series, min(len(series), width - 20))
        if graph and end_y <= top + height - 2:
            screen.put(left + 4, top + height - 2, "evolución", palette.style("muted"))
            screen.put(left + 14, top + height - 2, graph, palette.style("accent"))

        if not history.entries and not session:
            screen.put_center(
                top + height // 2, "todavía no hay datos que enseñar",
                palette.style("border"),
            )

    def _rows(self) -> list[tuple[str, str, str]]:
        history = self.app.history
        session = self.app.session
        rows: list[tuple[str, str, str]] = [("title", "sesión actual", "")]

        if session:
            rows += [
                ("row", "tests completados", str(len(session))),
                ("row", "mejor wpm", format_number(max(e.wpm for e in session))),
                ("row", "media wpm", format_number(_mean(e.wpm for e in session))),
                ("row", "media precisión", f"{_mean(e.accuracy for e in session):.1f}%"),
                ("row", "caracteres escritos", str(sum(e.chars.typed for e in session))),
            ]
        else:
            rows.append(("row", "todavía sin tests en esta sesión", "—"))

        rows += [("blank", "", ""), ("title", "histórico", "")]
        if history.entries:
            best = history.best_wpm()
            accurate = history.best_accuracy()
            top_score = history.best_score()
            today = history.best_today()
            rows += [
                ("row", "tests guardados", str(len(history))),
                ("row", "récord wpm", _record_line(best)),
                ("row", "récord precisión", f"{accurate.accuracy:.1f}%" if accurate else "—"),
                ("row", "récord score", str(top_score.score) if top_score else "—"),
                ("row", "media últimos 10", format_number(history.average_wpm(10))),
                ("row", "precisión últimos 10", f"{history.average_accuracy(10):.1f}%"),
                ("row", "mejor de hoy", format_number(today.wpm) if today else "—"),
                ("row", "tests hoy", str(len(history.today()))),
            ]
        else:
            rows.append(("row", "sin resultados guardados", "—"))
        return rows


def _record_line(result: TestResult | None) -> str:
    if result is None:
        return "—"
    return f"{format_number(result.wpm)}  ·  {result.describe_mode()}"


def _mean(values) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0
