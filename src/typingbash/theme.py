"""Temas de color y generación de secuencias SGR.

Los colores se definen una sola vez en RGB y se traducen al mejor formato que
soporte la terminal: color verdadero (24 bits) si está disponible, o la paleta
de 256 colores en caso contrario. Nunca se pinta el fondo de la pantalla, de
modo que el juego respeta el fondo que el usuario tenga configurado.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    """Paleta semántica: cada rol tiene un significado, no un color fijo."""

    name: str
    accent: RGB  # color de marca: títulos, cifras destacadas
    text: RGB  # texto principal y caracteres acertados
    pending: RGB  # texto todavía no escrito
    incorrect: RGB  # caracteres erróneos
    extra: RGB  # caracteres sobrantes al final de una palabra
    muted: RGB  # información secundaria
    border: RGB  # marcos y separadores
    success: RGB
    warning: RGB


THEMES: dict[str, Theme] = {
    "minimal": Theme(
        name="minimal",
        accent=(226, 183, 20),
        text=(209, 208, 197),
        pending=(100, 102, 105),
        incorrect=(202, 71, 84),
        extra=(126, 47, 55),
        muted=(100, 102, 105),
        border=(70, 72, 75),
        success=(120, 190, 120),
        warning=(226, 183, 20),
    ),
    "nord": Theme(
        name="nord",
        accent=(136, 192, 208),
        text=(216, 222, 233),
        pending=(76, 86, 106),
        incorrect=(191, 97, 106),
        extra=(120, 65, 70),
        muted=(76, 86, 106),
        border=(59, 66, 82),
        success=(163, 190, 140),
        warning=(235, 203, 139),
    ),
    "dracula": Theme(
        name="dracula",
        accent=(189, 147, 249),
        text=(248, 248, 242),
        pending=(98, 114, 164),
        incorrect=(255, 85, 85),
        extra=(140, 50, 50),
        muted=(98, 114, 164),
        border=(68, 71, 90),
        success=(80, 250, 123),
        warning=(241, 250, 140),
    ),
    "matrix": Theme(
        name="matrix",
        accent=(0, 255, 65),
        text=(180, 255, 190),
        pending=(40, 90, 50),
        incorrect=(255, 70, 70),
        extra=(120, 40, 40),
        muted=(40, 90, 50),
        border=(30, 70, 40),
        success=(0, 255, 65),
        warning=(200, 255, 100),
    ),
    "solar": Theme(
        name="solar",
        accent=(181, 137, 0),
        text=(238, 232, 213),
        pending=(101, 123, 131),
        incorrect=(220, 50, 47),
        extra=(130, 40, 38),
        muted=(101, 123, 131),
        border=(88, 110, 117),
        success=(133, 153, 0),
        warning=(203, 75, 22),
    ),
}

DEFAULT_THEME = "minimal"


def theme_names() -> list[str]:
    return sorted(THEMES)


def get_theme(name: str) -> Theme:
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def supports_truecolor() -> bool:
    return os.environ.get("COLORTERM", "").lower() in {"truecolor", "24bit"}


@lru_cache(maxsize=512)
def _to_256(rgb: RGB) -> int:
    """Aproxima un RGB al índice más cercano de la paleta xterm-256."""
    r, g, b = rgb
    # Escala de grises (índices 232-255) cuando los canales son casi iguales.
    if abs(r - g) < 12 and abs(g - b) < 12 and abs(r - b) < 12:
        gray = round((r + g + b) / 3)
        if gray < 8:
            return 16
        if gray > 248:
            return 231
        return 232 + round((gray - 8) / 247 * 23)
    levels = (0, 95, 135, 175, 215, 255)

    def nearest(value: int) -> int:
        return min(range(6), key=lambda i: abs(levels[i] - value))

    return 16 + 36 * nearest(r) + 6 * nearest(g) + nearest(b)


class Palette:
    """Convierte roles del tema en secuencias SGR listas para escribir."""

    def __init__(self, theme: Theme, truecolor: bool | None = None) -> None:
        self.theme = theme
        self.truecolor = supports_truecolor() if truecolor is None else truecolor
        self._cache: dict[tuple, str] = {}

    def _fg(self, rgb: RGB) -> str:
        if self.truecolor:
            return f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}"
        return f"38;5;{_to_256(rgb)}"

    def style(
        self,
        role: str | None = None,
        *,
        bold: bool = False,
        dim: bool = False,
        reverse: bool = False,
        underline: bool = False,
        italic: bool = False,
    ) -> str:
        key = (role, bold, dim, reverse, underline, italic)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        parts: list[str] = []
        if bold:
            parts.append("1")
        if dim:
            parts.append("2")
        if italic:
            parts.append("3")
        if underline:
            parts.append("4")
        if reverse:
            parts.append("7")
        if role is not None:
            parts.append(self._fg(getattr(self.theme, role)))

        result = "\x1b[" + ";".join(parts) + "m" if parts else ""
        self._cache[key] = result
        return result
