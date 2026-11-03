"""Métricas del test.

Fórmulas empleadas (todas documentadas porque no hay un único estándar):

``WPM``
    ``caracteres_correctos / 5 / minutos``. Se usa la convención clásica de
    que una "palabra" equivale a 5 caracteres. Cuentan como correctos los
    caracteres que coinciden con el objetivo y los espacios que separan
    correctamente dos palabras.

``RAW WPM``
    ``caracteres_tecleados / 5 / minutos``, sin descontar errores. Es la
    velocidad bruta: siempre es mayor o igual que el WPM.

``ACCURACY``
    ``pulsaciones_correctas / pulsaciones_totales``. Se mide sobre las
    pulsaciones realmente efectuadas, así que **un error corregido con
    retroceso sigue penalizando**: borrar arregla el texto, no la precisión.

``CONSISTENCY``
    ``100 · (1 − σ/μ)`` sobre las muestras de WPM bruto tomadas cada segundo.
    Un ritmo uniforme se acerca a 100; los acelerones y frenazos lo bajan.

``SCORE``
    ``caracteres_correctos · (precisión)² · (1 + WPM/100)``. Premia escribir
    mucho, rápido y limpio; la precisión entra al cuadrado para que la
    velocidad sin control no compense.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field

CHARS_PER_WORD = 5


@dataclass
class CharCounts:
    """Recuento de caracteres al final del test."""

    correct: int = 0
    incorrect: int = 0
    extra: int = 0
    missed: int = 0

    @property
    def typed(self) -> int:
        """Caracteres que el usuario llegó a escribir."""
        return self.correct + self.incorrect + self.extra

    @property
    def total(self) -> int:
        """Incluye los que debería haber escrito y no escribió."""
        return self.typed + self.missed


@dataclass
class WordCounts:
    correct: int = 0
    incorrect: int = 0

    @property
    def total(self) -> int:
        return self.correct + self.incorrect


def wpm(correct_chars: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return (correct_chars / CHARS_PER_WORD) / (seconds / 60.0)


def raw_wpm(typed_chars: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return (typed_chars / CHARS_PER_WORD) / (seconds / 60.0)


def accuracy(correct_keystrokes: int, total_keystrokes: int) -> float:
    if total_keystrokes <= 0:
        return 100.0
    return 100.0 * correct_keystrokes / total_keystrokes


def consistency(samples: list[float]) -> float:
    """Uniformidad del ritmo a partir de las muestras de WPM por segundo."""
    usable = [s for s in samples if s > 0]
    if len(usable) < 2:
        return 100.0 if usable else 0.0
    mean = sum(usable) / len(usable)
    if mean <= 0:
        return 0.0
    variance = sum((s - mean) ** 2 for s in usable) / len(usable)
    coefficient = math.sqrt(variance) / mean
    return max(0.0, min(100.0, 100.0 * (1.0 - coefficient)))


def score(correct_chars: int, accuracy_pct: float, wpm_value: float) -> int:
    ratio = max(0.0, min(1.0, accuracy_pct / 100.0))
    return int(round(correct_chars * (ratio**2) * (1.0 + wpm_value / 100.0)))


@dataclass
class TestResult:
    """Resultado completo de un test, serializable para el historial."""

    wpm: float
    raw_wpm: float
    accuracy: float
    consistency: float
    score: int
    duration: float
    chars: CharCounts
    words: WordCounts
    mode: str
    mode_value: int
    language: str
    difficulty: str
    timestamp: float = field(default_factory=time.time)
    wpm_series: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["chars"] = asdict(self.chars)
        data["words"] = asdict(self.words)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TestResult":
        payload = dict(data)
        payload["chars"] = CharCounts(**payload.get("chars", {}))
        payload["words"] = WordCounts(**payload.get("words", {}))
        payload.setdefault("wpm_series", [])
        allowed = {
            "wpm", "raw_wpm", "accuracy", "consistency", "score", "duration",
            "chars", "words", "mode", "mode_value", "language", "difficulty",
            "timestamp", "wpm_series",
        }
        return cls(**{k: v for k, v in payload.items() if k in allowed})

    def describe_mode(self) -> str:
        return f"{self.mode_value}s" if self.mode == "time" else f"{self.mode_value} palabras"


class LiveStats:
    """Acumula pulsaciones durante el test y calcula métricas en vivo.

    Mantiene además una muestra de WPM bruto por segundo, que alimenta tanto
    la consistencia como el gráfico de la pantalla de resultados.
    """

    def __init__(self) -> None:
        self.correct_keystrokes = 0
        self.total_keystrokes = 0
        self.error_keystrokes = 0
        self.typed_chars = 0  # pulsaciones de texto, sin contar retrocesos
        self.series: list[float] = []
        self._last_sample_second = 0
        self._chars_at_last_sample = 0

    def record_keystroke(self, correct: bool) -> None:
        self.total_keystrokes += 1
        self.typed_chars += 1
        if correct:
            self.correct_keystrokes += 1
        else:
            self.error_keystrokes += 1

    def sample(self, elapsed: float) -> None:
        """Cierra las muestras de segundo completo que hayan transcurrido."""
        second = int(elapsed)
        while self._last_sample_second < second:
            self._last_sample_second += 1
            delta = self.typed_chars - self._chars_at_last_sample
            self._chars_at_last_sample = self.typed_chars
            self.series.append(raw_wpm(delta, 1.0))

    @property
    def live_accuracy(self) -> float:
        return accuracy(self.correct_keystrokes, self.total_keystrokes)
