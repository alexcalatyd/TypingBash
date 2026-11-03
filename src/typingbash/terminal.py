"""Control de bajo nivel de la terminal.

Responsabilidades:
  * entrar/salir de modo raw sin dejar la terminal rota;
  * pantalla alternativa (no ensucia el scrollback del usuario);
  * ocultar/mostrar el cursor hardware;
  * detectar el tamaño y los cambios de tamaño (SIGWINCH).

La restauración es lo más crítico del módulo: se registra en ``atexit`` y en
los manejadores de señales, de modo que ni una excepción ni un SIGTERM dejan
la terminal en modo raw.
"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import sys
import termios
import tty
from dataclasses import dataclass

CSI = "\x1b["

# Secuencias ANSI usadas en toda la aplicación.
ALT_SCREEN_ON = CSI + "?1049h"
ALT_SCREEN_OFF = CSI + "?1049l"
CURSOR_HIDE = CSI + "?25l"
CURSOR_SHOW = CSI + "?25h"
CLEAR_SCREEN = CSI + "2J"
CURSOR_HOME = CSI + "H"
RESET_SGR = CSI + "0m"


@dataclass(frozen=True)
class Size:
    columns: int
    rows: int


class TerminalError(RuntimeError):
    """La terminal no reúne las condiciones mínimas para ejecutar el juego."""


class Terminal:
    """Envoltorio con estado sobre el TTY.

    Uso previsto::

        with Terminal() as term:
            ...
    """

    def __init__(self) -> None:
        self._in = sys.stdin
        self._out = sys.stdout
        self._saved_attrs: list | None = None
        self._prev_winch = None
        self._prev_term = None
        self._prev_hup = None
        self._active = False
        self.resized = False

    # ------------------------------------------------------------------ setup

    def require_tty(self) -> None:
        if not self._in.isatty() or not self._out.isatty():
            raise TerminalError(
                "Este juego necesita una terminal interactiva.\n"
                "Ejecútalo directamente en la terminal, sin pipes ni redirecciones."
            )

    @property
    def fd(self) -> int:
        return self._in.fileno()

    def __enter__(self) -> "Terminal":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        if self._active:
            return
        self.require_tty()

        # UTF-8 explícito: no dependemos de que el locale esté bien configurado.
        try:
            self._out.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - stdout exótico
            pass

        self._saved_attrs = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        # Mantenemos el post-procesado de salida: si algo imprime un "\n"
        # suelto no se produce el efecto escalera.
        raw = termios.tcgetattr(self.fd)
        raw[1] |= termios.OPOST
        termios.tcsetattr(self.fd, termios.TCSADRAIN, raw)

        self.write(ALT_SCREEN_ON + CURSOR_HIDE + CLEAR_SCREEN + CURSOR_HOME)
        self.flush()

        self._prev_winch = signal.signal(signal.SIGWINCH, self._on_winch)
        self._prev_term = signal.signal(signal.SIGTERM, self._on_fatal_signal)
        try:
            self._prev_hup = signal.signal(signal.SIGHUP, self._on_fatal_signal)
        except (ValueError, OSError):  # pragma: no cover
            self._prev_hup = None

        atexit.register(self.close)
        self._active = True

    def close(self) -> None:
        """Restaura la terminal. Es idempotente y nunca lanza excepciones."""
        if not self._active:
            return
        self._active = False
        try:
            self.write(RESET_SGR + CURSOR_SHOW + ALT_SCREEN_OFF)
            self.flush()
        except Exception:  # pragma: no cover - la salida puede estar cerrada
            pass
        if self._saved_attrs is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self._saved_attrs)
            except Exception:  # pragma: no cover
                pass
        for sig, handler in (
            (signal.SIGWINCH, self._prev_winch),
            (signal.SIGTERM, self._prev_term),
            (signal.SIGHUP, self._prev_hup),
        ):
            if handler is not None:
                try:
                    signal.signal(sig, handler)
                except Exception:  # pragma: no cover
                    pass
        try:
            atexit.unregister(self.close)
        except Exception:  # pragma: no cover
            pass

    # ---------------------------------------------------------------- señales

    def _on_winch(self, signum, frame) -> None:
        self.resized = True

    def _on_fatal_signal(self, signum, frame) -> None:  # pragma: no cover
        self.close()
        # 128 + señal es la convención de los shells POSIX.
        os._exit(128 + signum)

    def take_resize(self) -> bool:
        """Consume la marca de redimensionado (patrón test-and-clear)."""
        if self.resized:
            self.resized = False
            return True
        return False

    # ------------------------------------------------------------------ salida

    def size(self) -> Size:
        size = shutil.get_terminal_size(fallback=(80, 24))
        return Size(columns=size.columns, rows=size.lines)

    def write(self, data: str) -> None:
        self._out.write(data)

    def flush(self) -> None:
        try:
            self._out.flush()
        except Exception:  # pragma: no cover
            pass
