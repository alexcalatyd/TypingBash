"""Renderizador de doble búfer con repintado diferencial.

Cada fotograma se compone en un búfer en memoria (``back``). Al hacer
``flush`` se compara con lo que hay realmente en pantalla (``front``) y solo
se emiten las celdas que han cambiado. Eso elimina el parpadeo y mantiene el
tráfico por el TTY en unos pocos cientos de bytes por fotograma, incluso
actualizando el cronómetro diez veces por segundo.
"""

from __future__ import annotations

from .terminal import CSI, RESET_SGR

# Una celda es (carácter, estilo SGR). Se comparan como tuplas.
Cell = tuple[str, str]
EMPTY: Cell = (" ", "")


class Screen:
    """Lienzo de celdas del tamaño de la terminal."""

    def __init__(self, width: int, height: int) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self._back: list[list[Cell]] = self._blank()
        self._front: list[list[Cell]] | None = None

    def _blank(self) -> list[list[Cell]]:
        return [[EMPTY] * self.width for _ in range(self.height)]

    # --------------------------------------------------------------- tamaño

    def resize(self, width: int, height: int) -> None:
        if width == self.width and height == self.height:
            return
        self.width = max(1, width)
        self.height = max(1, height)
        self._back = self._blank()
        self.invalidate()

    def invalidate(self) -> None:
        """Fuerza un repintado completo en el siguiente ``flush``."""
        self._front = None

    def clear(self) -> None:
        """Vacía el búfer de composición (no toca la pantalla todavía)."""
        blank = EMPTY
        for row in self._back:
            for x in range(self.width):
                row[x] = blank

    # --------------------------------------------------------------- dibujo

    def put(self, x: int, y: int, text: str, style: str = "") -> int:
        """Escribe ``text`` en (x, y) recortando a los límites. Devuelve la x final."""
        if not (0 <= y < self.height) or not text:
            return x
        row = self._back[y]
        for char in text:
            if x >= self.width:
                break
            if x >= 0:
                row[x] = (char, style)
            x += 1
        return x

    def put_center(self, y: int, text: str, style: str = "") -> int:
        x = max(0, (self.width - len(text)) // 2)
        return self.put(x, y, text, style)

    def put_right(self, y: int, right_edge: int, text: str, style: str = "") -> int:
        return self.put(right_edge - len(text), y, text, style)

    def fill(self, x: int, y: int, width: int, char: str = " ", style: str = "") -> None:
        self.put(x, y, char * max(0, width), style)

    def hline(self, x: int, y: int, width: int, style: str = "", char: str = "─") -> None:
        self.fill(x, y, width, char, style)

    # --------------------------------------------------------------- volcado

    def flush(self, write, force: bool = False) -> None:
        """Emite a ``write`` únicamente las diferencias con el fotograma previo."""
        full = force or self._front is None
        if full:
            self._front = [[("\0", "")] * self.width for _ in range(self.height)]
        front = self._front
        assert front is not None

        out: list[str] = []
        if full:
            out.append(RESET_SGR + CSI + "2J")

        for y in range(self.height):
            back_row = self._back[y]
            front_row = front[y]
            x = 0
            while x < self.width:
                if back_row[x] == front_row[x]:
                    x += 1
                    continue
                # Agrupa celdas contiguas modificadas que comparten estilo.
                style = back_row[x][1]
                start = x
                chars: list[str] = []
                while (
                    x < self.width
                    and back_row[x] != front_row[x]
                    and back_row[x][1] == style
                ):
                    chars.append(back_row[x][0])
                    front_row[x] = back_row[x]
                    x += 1
                out.append(f"{CSI}{y + 1};{start + 1}H")
                out.append(RESET_SGR)
                if style:
                    out.append(style)
                out.append("".join(chars))

        if out:
            out.append(RESET_SGR)
            write("".join(out))


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Recorta preservando el ancho exacto, con puntos suspensivos si sobra."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return text[:width]
    return text[: width - len(ellipsis)] + ellipsis
