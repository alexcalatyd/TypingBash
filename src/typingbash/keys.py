"""Decodificación de pulsaciones en modo raw.

Convierte el flujo de bytes de ``stdin`` en objetos :class:`Key`. Se ocupa de
tres problemas que son fáciles de resolver mal:

1. **UTF-8 multibyte.** ``á`` o ``ñ`` llegan en 2 bytes que pueden partirse
   entre dos lecturas; usamos un decodificador incremental.
2. **Secuencias de escape.** ``ESC`` suelto y ``ESC [ A`` (flecha) empiezan
   igual. Se distinguen esperando un instante muy corto por más bytes.
3. **Acentos por tecla muerta.** Si la terminal entrega el acento como marca
   combinante independiente, se emite una tecla ``combining`` para que la capa
   superior la fusione con el carácter anterior.
"""

from __future__ import annotations

import codecs
import os
import select
import unicodedata
from dataclasses import dataclass

# Espera máxima para decidir si un ESC es tecla suelta o inicio de secuencia.
_ESC_AMBIGUITY_TIMEOUT = 0.03


@dataclass(frozen=True)
class Key:
    """Una pulsación ya interpretada.

    ``name`` es la identidad lógica ("char", "enter", "escape", "ctrl-c"...).
    ``char`` solo tiene contenido cuando ``name`` es ``char`` o ``combining``.
    """

    name: str
    char: str = ""

    @property
    def is_char(self) -> bool:
        return self.name == "char"

    def __str__(self) -> str:  # pragma: no cover - ayuda al depurar
        return self.char if self.is_char else f"<{self.name}>"


# Teclas de control con significado propio; el resto de \x01-\x1a se mapea a
# "ctrl-<letra>" de forma genérica.
_CONTROL_KEYS = {
    "\x03": "ctrl-c",
    "\x04": "ctrl-d",
    "\r": "enter",
    "\n": "enter",
    "\t": "tab",
    "\x7f": "backspace",
    "\x08": "backspace",
    "\x17": "delete-word",  # ctrl+w
    "\x15": "delete-line",  # ctrl+u
}

_CSI_FINAL = {
    "A": "up",
    "B": "down",
    "C": "right",
    "D": "left",
    "H": "home",
    "F": "end",
    "Z": "shift-tab",
}

_SPECIAL_TILDE = {
    "1": "home",
    "3": "delete",
    "4": "end",
    "5": "page-up",
    "6": "page-down",
    "7": "home",
    "8": "end",
}


class InputReader:
    """Lee y decodifica pulsaciones sin bloquear el bucle principal."""

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pending = ""  # texto decodificado aún sin interpretar

    # ------------------------------------------------------------------ E/S

    def wait(self, timeout: float | None) -> bool:
        """Bloquea hasta que haya entrada disponible o expire ``timeout``."""
        if self._pending:
            return True
        try:
            ready, _, _ = select.select([self._fd], [], [], timeout)
        except (InterruptedError, OSError):
            # SIGWINCH interrumpe select(); no es un error.
            return False
        return bool(ready)

    def _pump(self, timeout: float = 0.0) -> bool:
        """Intenta añadir bytes al buffer. Devuelve True si llegó algo."""
        try:
            ready, _, _ = select.select([self._fd], [], [], timeout)
        except (InterruptedError, OSError):
            return False
        if not ready:
            return False
        try:
            data = os.read(self._fd, 1024)
        except (InterruptedError, BlockingIOError):
            return False
        except OSError:
            return False
        if not data:
            return False
        self._pending += self._decoder.decode(data)
        return True

    def read_keys(self, timeout: float | None = 0.0) -> list[Key]:
        """Devuelve todas las teclas disponibles (posiblemente ninguna)."""
        if not self._pending:
            if not self.wait(timeout):
                return []
            self._pump(0.0)
        # Vacía cualquier resto que ya esté en el buffer del sistema: teclear
        # rápido genera ráfagas y así no se pierde ni se retrasa ninguna.
        while self._pump(0.0):
            pass

        keys: list[Key] = []
        while self._pending:
            key, consumed = self._parse(self._pending)
            if key is None:
                break  # secuencia incompleta: esperamos a la siguiente lectura
            self._pending = self._pending[consumed:]
            keys.append(key)
        return keys

    # ---------------------------------------------------------------- parseo

    def _parse(self, buf: str) -> tuple[Key | None, int]:
        first = buf[0]

        if first == "\x1b":
            return self._parse_escape(buf)

        if first in _CONTROL_KEYS:
            return Key(_CONTROL_KEYS[first]), 1

        if "\x01" <= first <= "\x1a":
            letter = chr(ord(first) + 96)
            return Key(f"ctrl-{letter}"), 1

        if first < " ":
            return Key("unknown"), 1

        if unicodedata.combining(first):
            return Key("combining", first), 1

        return Key("char", first), 1

    def _parse_escape(self, buf: str) -> tuple[Key | None, int]:
        if len(buf) == 1:
            # ¿ESC suelto o principio de secuencia? Damos un margen mínimo.
            if self._pump(_ESC_AMBIGUITY_TIMEOUT):
                buf = self._pending
                if len(buf) == 1:
                    return Key("escape"), 1
            else:
                return Key("escape"), 1

        second = buf[1]

        if second == "\x7f":  # option/alt + backspace
            return Key("delete-word"), 2

        if second == "\x1b":
            return Key("escape"), 1

        if second == "O" and len(buf) >= 3:  # teclado de aplicación (SS3)
            return Key(_CSI_FINAL.get(buf[2], "unknown")), 3

        if second != "[":
            # ESC + carácter: lo tratamos como alt+tecla, que no usamos.
            return Key("unknown"), 2

        # Secuencia CSI: ESC [ parámetros final
        index = 2
        while index < len(buf) and (buf[index].isdigit() or buf[index] == ";"):
            index += 1
        if index >= len(buf):
            return None, 0  # aún incompleta
        final = buf[index]
        params = buf[2:index]
        consumed = index + 1

        if final == "~":
            return Key(_SPECIAL_TILDE.get(params.split(";")[0], "unknown")), consumed
        return Key(_CSI_FINAL.get(final, "unknown")), consumed


def compose(base: str, mark: str) -> str:
    """Fusiona un carácter con una marca combinante (``a`` + ``´`` -> ``á``).

    Si la combinación no produce un único carácter precompuesto se devuelve el
    original, evitando así insertar basura en el texto tecleado.
    """
    combined = unicodedata.normalize("NFC", base + mark)
    return combined if len(combined) == 1 else base
