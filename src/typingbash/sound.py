"""Efectos de sonido opcionales (macOS).

Se apoyan en ``afplay`` y en los sonidos del sistema, así que no hace falta
empaquetar audio ni instalar nada. Están **desactivados por defecto** y nunca
bloquean: el proceso se lanza en segundo plano y, si algo falla, el sonido
simplemente se desactiva para el resto de la sesión.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_SYSTEM_SOUNDS = Path("/System/Library/Sounds")

EVENTS = {
    "error": "Basso.aiff",
    "finish": "Glass.aiff",
    "record": "Hero.aiff",
}


class SoundPlayer:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._player = shutil.which("afplay")
        self._processes: list[subprocess.Popen] = []

    @property
    def available(self) -> bool:
        return self._player is not None

    def play(self, event: str) -> None:
        if not self.enabled or not self._player:
            return
        name = EVENTS.get(event)
        if not name:
            return
        path = _SYSTEM_SOUNDS / name
        if not path.exists():
            return
        self._reap()
        if len(self._processes) >= 4:
            return  # evita acumular procesos si se dispara muy seguido
        try:
            self._processes.append(
                subprocess.Popen(
                    [self._player, "-v", "0.35", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            )
        except OSError:
            self.enabled = False  # sin ruido y sin molestar más

    def _reap(self) -> None:
        self._processes = [p for p in self._processes if p.poll() is None]

    def close(self) -> None:
        for process in self._processes:
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:  # pragma: no cover
                    pass
        self._processes.clear()
