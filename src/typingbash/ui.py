"""Piezas de dibujo reutilizables: marcos, logo, barras y formateo.

Aquí no hay lógica de juego, solo composición visual sobre un
:class:`~typingbash.render.Screen`.
"""

from __future__ import annotations

from .render import Screen
from .theme import Palette

# Logo "TYPING" en bloques (tipografía ANSI Shadow). 48 columnas de ancho.
LOGO = (
    "████████╗██╗   ██╗██████╗ ██╗███╗   ██╗ ██████╗ ",
    "╚══██╔══╝╚██╗ ██╔╝██╔══██╗██║████╗  ██║██╔════╝ ",
    "   ██║    ╚████╔╝ ██████╔╝██║██╔██╗ ██║██║  ███╗",
    "   ██║     ╚██╔╝  ██╔═══╝ ██║██║╚██╗██║██║   ██║",
    "   ██║      ██║   ██║     ██║██║ ╚████║╚██████╔╝",
    "   ╚═╝      ╚═╝   ╚═╝     ╚═╝╚═╝  ╚═══╝ ╚═════╝ ",
)
LOGO_WIDTH = len(LOGO[0])
LOGO_HEIGHT = len(LOGO)

SPARK_CHARS = "▁▂▃▄▅▆▇█"

# --------------------------------------------------------------- tamaño de la UI
#
# El ajuste ``ui_size`` decide cuánta terminal ocupan los paneles:
#
#   large   → hasta los márgenes: la interfaz llena la pantalla
#   medium  → a medio camino entre la medida clásica y la pantalla entera
#   small   → la medida clásica de cada pantalla, pase lo que pase
#
# Cada pantalla dice cuál es su ancho "clásico" (``base``) y su mínimo, y estas
# funciones se encargan del resto. Nunca devuelven algo que no quepa.

SIDE_MARGIN = 4  # columnas libres a cada lado en tamaño grande
TOP_MARGIN = 1  # filas libres arriba y abajo del panel
CHROME_ROWS = 2  # filas del final reservadas a avisos y atajos


def blend(base: int, available: int, size: str) -> int:
    """Interpola entre la medida clásica y todo el espacio disponible."""
    if size == "large":
        return available
    if size == "medium":
        return (base + available) // 2
    return base


def panel_width(screen: Screen, size: str, base: int, minimum: int = 0) -> int:
    """Ancho de un panel centrado, según el tamaño de interfaz elegido."""
    limit = max(minimum, screen.width - 4)  # nunca pegado a los bordes
    available = max(minimum, screen.width - SIDE_MARGIN * 2)
    return min(limit, max(minimum, blend(base, available, size)))


def panel_height(screen: Screen, size: str, base: int, minimum: int = 3) -> int:
    """Alto de un panel centrado, sin invadir la barra inferior."""
    limit = max(minimum, screen.height - CHROME_ROWS)
    available = max(minimum, screen.height - CHROME_ROWS - TOP_MARGIN * 2)
    return min(limit, max(minimum, blend(base, available, size)))

# Tipografía de bloque de 5 filas para el contador grande y la cuenta atrás.
# Cada columna se duplica al renderizar, así que un dígito ocupa 6 celdas.
BIG_GLYPH_HEIGHT = 5
BIG_GLYPHS: dict[str, tuple[str, ...]] = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": (" █ ", "██ ", " █ ", " █ ", "███"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ".": ("", "", "", "", "█"),
    "/": ("  █", "  █", " █ ", "█  ", "█  "),
    " ": ("", "", "", "", ""),
}


def render_big(text: str, scale: int = 1) -> list[str]:
    """Convierte ``29.7`` en filas de bloques listas para pintar.

    ``scale`` multiplica el tamaño: con 2 cada fila se repite dos veces y cada
    columna ocupa el doble, así que la cifra sale el doble de grande.
    """
    scale = max(1, scale)
    glyphs = [BIG_GLYPHS[char] for char in text if char in BIG_GLYPHS]
    if not glyphs:
        return [""] * (BIG_GLYPH_HEIGHT * scale)

    rows: list[str] = []
    for line in range(BIG_GLYPH_HEIGHT):
        parts = []
        for glyph in glyphs:
            width = max(len(row) for row in glyph) or 1
            cell = glyph[line].ljust(width)
            parts.append("".join(char * 2 * scale for char in cell))
        rows.extend([" ".join(parts)] * scale)
    return rows


def big_width(text: str, scale: int = 1) -> int:
    rows = render_big(text, scale)
    return max((len(row) for row in rows), default=0)

# Caracteres de marco: normal y doble (para celebrar récords).
BOX_ROUND = ("╭", "╮", "╰", "╯", "─", "│")
BOX_DOUBLE = ("╔", "╗", "╚", "╝", "═", "║")


def draw_box(
    screen: Screen,
    x: int,
    y: int,
    width: int,
    height: int,
    style: str,
    *,
    title: str = "",
    title_style: str | None = None,
    chars: tuple[str, ...] = BOX_ROUND,
) -> None:
    """Dibuja un marco. El interior no se rellena: se respeta el fondo."""
    if width < 2 or height < 2:
        return
    top_left, top_right, bottom_left, bottom_right, horizontal, vertical = chars

    screen.put(x, y, top_left + horizontal * (width - 2) + top_right, style)
    screen.put(x, y + height - 1, bottom_left + horizontal * (width - 2) + bottom_right, style)
    for row in range(y + 1, y + height - 1):
        screen.put(x, row, vertical, style)
        screen.put(x + width - 1, row, vertical, style)

    if title:
        label = f" {title} "
        if len(label) <= width - 4:
            screen.put(x + (width - len(label)) // 2, y, label, title_style or style)


def clear_box(screen: Screen, x: int, y: int, width: int, height: int) -> None:
    """Limpia el interior de una zona, útil para paneles superpuestos."""
    for row in range(y, y + height):
        screen.fill(x, row, width, " ")


def draw_logo(screen: Screen, y: int, palette: Palette, reveal: float = 1.0) -> int:
    """Pinta el logo centrado. ``reveal`` (0..1) lo descubre de izquierda a derecha."""
    style = palette.style("accent", bold=True)
    if screen.width < LOGO_WIDTH + 2:
        screen.put_center(y, "T Y P I N G", style)
        return y + 1
    visible = max(0, min(LOGO_WIDTH, int(round(LOGO_WIDTH * reveal))))
    x = (screen.width - LOGO_WIDTH) // 2
    for offset, line in enumerate(LOGO):
        screen.put(x, y + offset, line[:visible], style)
    return y + LOGO_HEIGHT


def progress_bar(width: int, fraction: float, filled: str = "█", empty: str = "░") -> tuple[str, str]:
    """Devuelve (parte llena, parte vacía) para poder darles color distinto."""
    width = max(0, width)
    fraction = max(0.0, min(1.0, fraction))
    done = int(round(width * fraction))
    return filled * done, empty * (width - done)


def draw_progress(
    screen: Screen, x: int, y: int, width: int, fraction: float, palette: Palette
) -> None:
    done, left = progress_bar(width, fraction)
    end = screen.put(x, y, done, palette.style("accent"))
    screen.put(end, y, left, palette.style("border"))


def sparkline(values: list[float], width: int) -> str:
    """Mini gráfico de una línea con los valores remuestreados a ``width``."""
    if not values or width <= 0:
        return ""
    if len(values) > width:
        # Remuestreo por promedio de bloques para no perder la forma.
        block = len(values) / width
        sampled = []
        for i in range(width):
            chunk = values[int(i * block) : max(int((i + 1) * block), int(i * block) + 1)]
            sampled.append(sum(chunk) / len(chunk) if chunk else 0.0)
    else:
        sampled = list(values)

    peak = max(sampled)
    if peak <= 0:
        return SPARK_CHARS[0] * len(sampled)
    scale = len(SPARK_CHARS) - 1
    return "".join(SPARK_CHARS[int(round(value / peak * scale))] for value in sampled)


def draw_hints(screen: Screen, y: int, palette: Palette, hints: list[tuple[str, str]]) -> None:
    """Barra inferior de atajos: la tecla resaltada y su acción atenuada."""
    key_style = palette.style("muted", bold=True)
    text_style = palette.style("border")
    separator = "   "

    width = sum(len(key) + 1 + len(label) for key, label in hints)
    width += len(separator) * (len(hints) - 1)
    x = max(0, (screen.width - width) // 2)

    for index, (key, label) in enumerate(hints):
        if index:
            x = screen.put(x, y, separator, text_style)
        x = screen.put(x, y, key, key_style)
        x = screen.put(x, y, " " + label, text_style)


def format_number(value: float) -> str:
    """Números compactos: sin decimales si no aportan."""
    if value >= 100 or float(value).is_integer():
        return str(int(round(value)))
    return f"{value:.1f}"


def format_seconds(value: float) -> str:
    """``29.7`` mientras corre el reloj, ``30`` cuando es exacto."""
    if value >= 10 and abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def format_duration(seconds: float) -> str:
    if seconds >= 60:
        minutes, rest = divmod(seconds, 60)
        return f"{int(minutes)}m {rest:04.1f}s"
    return f"{seconds:.1f}s"
