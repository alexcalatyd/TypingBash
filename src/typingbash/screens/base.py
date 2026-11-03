"""Contrato común de las pantallas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..keys import Key
from ..render import Screen

if TYPE_CHECKING:  # pragma: no cover
    from ..app import App


class View:
    """Una pantalla de la aplicación.

    El bucle principal pregunta ``frame_interval()`` para saber cada cuánto
    refrescar: las pantallas estáticas devuelven ``None`` y solo se redibujan
    cuando ocurre algo, lo que deja la CPU en reposo.
    """

    #: Atajos que la aplicación pinta en la barra inferior.
    hints: tuple[tuple[str, str], ...] = ()

    def __init__(self, app: "App") -> None:
        self.app = app

    @property
    def palette(self):
        return self.app.palette

    @property
    def size(self) -> str:
        """Tamaño de interfaz elegido: ``large``, ``medium`` o ``small``."""
        return self.app.config.ui_size

    def on_enter(self) -> None:
        """Se llama al mostrar la pantalla."""

    def on_exit(self) -> None:
        """Se llama al abandonarla."""

    def frame_interval(self) -> float | None:
        return None

    def tick(self, now: float) -> None:
        """Avance temporal (animaciones, cronómetro)."""

    def on_key(self, key: Key) -> None:
        """Procesa una pulsación."""

    def draw(self, screen: Screen) -> None:
        raise NotImplementedError
