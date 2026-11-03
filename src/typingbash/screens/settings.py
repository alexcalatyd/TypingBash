"""Pantalla de ajustes interactiva.

La lista se genera a partir de :data:`typingbash.config.FIELDS`, así que un
ajuste nuevo aparece aquí sin tocar esta pantalla.
"""

from __future__ import annotations

from ..config import FIELDS, ConfigError
from ..keys import Key
from ..render import Screen, truncate
from ..ui import draw_box, panel_height, panel_width
from .base import View

# Cuánto mueve una flecha a los ajustes numéricos.
INT_STEP = {"time_seconds": 5, "word_count": 5}

BASE_WIDTH, MIN_WIDTH = 66, 44


class SettingsView(View):
    hints = (
        ("↑↓", "elegir"),
        ("←→", "cambiar"),
        ("enter", "alternar"),
        ("esc", "volver"),
    )

    def __init__(self, app) -> None:
        super().__init__(app)
        self.selected = 0

    def on_key(self, key: Key) -> None:
        if key.name in ("escape",):
            self.app.go_back()
            return
        if key.name == "char" and key.char.lower() == "q":
            self.app.go_back()
            return

        if key.name == "up":
            self.selected = (self.selected - 1) % len(FIELDS)
        elif key.name == "down":
            self.selected = (self.selected + 1) % len(FIELDS)
        elif key.name == "left":
            self._change(-1)
        elif key.name in ("right", "enter"):
            self._change(1)

    def _change(self, direction: int) -> None:
        field = FIELDS[self.selected]
        config = self.app.config
        current = getattr(config, field.name)

        if field.kind == "bool":
            new_value = not current
        elif field.kind == "int":
            step = INT_STEP.get(field.name, 1) * direction
            new_value = max(field.minimum, min(field.maximum, int(current) + step))
        else:
            options = field.options()
            if not options:
                return
            index = options.index(current) if current in options else 0
            new_value = options[(index + direction) % len(options)]

        try:
            config.set_value(field.name, new_value)
        except ConfigError as exc:
            self.app.notify(str(exc), level="error")
            return
        self.app.apply_config()
        self.app.save_config()

    # ------------------------------------------------------------------ dibujo

    def draw(self, screen: Screen) -> None:
        palette = self.palette
        width = panel_width(screen, self.size, BASE_WIDTH, MIN_WIDTH)
        # En tamaño grande las filas van con aire entre ellas, si la ventana da.
        step = 2 if self.size == "large" and screen.height >= len(FIELDS) * 2 + 7 else 1
        content = len(FIELDS) * step - (step - 1)
        height = max(8, min(content + 5, panel_height(screen, self.size, content + 5, 8)))
        left = (screen.width - width) // 2
        top = max(0, (screen.height - height) // 2 - 1)

        draw_box(
            screen, left, top, width, height, palette.style("border"),
            title="ajustes", title_style=palette.style("accent", bold=True),
        )

        visible = max(1, (height - 5 + step - 1) // step)
        start = max(0, min(self.selected - visible + 2, len(FIELDS) - visible))
        start = max(0, start)

        label_x, value_x, description_x = _columns(width)
        for row, field in enumerate(FIELDS[start : start + visible]):
            index = start + row
            y = top + 2 + row * step
            active = index == self.selected
            value = _format_value(getattr(self.app.config, field.name))

            if active:
                screen.fill(left + 2, y, width - 4, " ")
                screen.put(left + 2, y, "›", palette.style("accent", bold=True))

            label_style = (
                palette.style("text", bold=True) if active else palette.style("muted")
            )
            value_style = (
                palette.style("accent", bold=True) if active else palette.style("text")
            )
            screen.put(left + label_x, y, truncate(field.label, value_x - label_x - 1), label_style)
            screen.put(
                left + value_x, y,
                truncate(value, description_x - value_x - 2), value_style,
            )
            description_width = width - description_x - 4
            if description_width >= 12:
                screen.put(
                    left + description_x, y,
                    truncate(field.description, description_width),
                    palette.style("border"),
                )

        field = FIELDS[self.selected]
        footer = _options_hint(field)
        screen.put_center(top + height - 2, truncate(footer, width - 4), palette.style("border"))


def _columns(width: int) -> tuple[int, int, int]:
    """Desplazamientos de etiqueta, valor y descripción dentro del marco.

    Con marcos anchos las columnas se reparten el espacio en vez de quedarse
    todas apelotonadas a la izquierda.
    """
    inner = width - 8
    label_width = min(30, max(23, inner * 35 // 100))
    value_width = min(22, max(16, inner * 22 // 100))
    return 4, 4 + label_width, 4 + label_width + value_width


def _format_value(value) -> str:
    if isinstance(value, bool):
        return "activado" if value else "desactivado"
    return str(value)


def _options_hint(field) -> str:
    if field.kind == "bool":
        return "enter o ← → para alternar"
    if field.kind == "int":
        return f"← → ajusta · entre {field.minimum} y {field.maximum}"
    return "opciones: " + ", ".join(field.options())
