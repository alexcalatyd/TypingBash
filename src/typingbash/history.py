"""Persistencia del historial de resultados y cálculo de récords.

Los datos viven en un único JSON dentro del directorio del usuario. No hay
servidor ni base de datos: se lee al arrancar, se escribe de forma atómica al
terminar cada test y se conserva un máximo de :data:`MAX_ENTRIES` resultados.

Los récords se calculan **por modalidad** (``time:30``, ``words:50``...),
porque comparar un test de 15 segundos con uno de dos minutos no dice nada.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from . import paths
from .stats import TestResult

SCHEMA_VERSION = 1
MAX_ENTRIES = 500


@dataclass(frozen=True)
class Records:
    """Qué récords ha batido un resultado concreto."""

    wpm: bool = False
    accuracy: bool = False
    score: bool = False
    previous_wpm: float = 0.0

    @property
    def any(self) -> bool:
        return self.wpm or self.accuracy or self.score


class History:
    def __init__(self, entries: list[TestResult] | None = None) -> None:
        self.entries: list[TestResult] = entries or []

    # ---------------------------------------------------------- persistencia

    @classmethod
    def load(cls) -> "History":
        path = paths.history_file()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, json.JSONDecodeError):
            return cls()  # historial corrupto: se empieza de cero, sin fallar

        raw_entries = data.get("results", []) if isinstance(data, dict) else []
        entries: list[TestResult] = []
        for item in raw_entries:
            try:
                entries.append(TestResult.from_dict(item))
            except (TypeError, ValueError, KeyError):
                continue  # una entrada rota no invalida el resto
        entries.sort(key=lambda r: r.timestamp)
        return cls(entries)

    def save(self) -> bool:
        try:
            paths.ensure_user_dir()
            path = paths.history_file()
            payload = {
                "version": SCHEMA_VERSION,
                "results": [entry.to_dict() for entry in self.entries[-MAX_ENTRIES:]],
            }
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            temporary.replace(path)
            return True
        except OSError:
            return False

    # ---------------------------------------------------------------- récords

    @staticmethod
    def signature(result: TestResult) -> str:
        return f"{result.mode}:{result.mode_value}"

    def for_signature(self, signature: str) -> list[TestResult]:
        return [e for e in self.entries if self.signature(e) == signature]

    def evaluate(self, result: TestResult) -> Records:
        """Compara con el histórico **previo** a este resultado."""
        peers = self.for_signature(self.signature(result))
        if not peers:
            # El primer test de una modalidad no se anuncia como récord.
            return Records(previous_wpm=0.0)
        best_wpm = max(e.wpm for e in peers)
        best_accuracy = max(e.accuracy for e in peers)
        best_score = max(e.score for e in peers)
        return Records(
            wpm=result.wpm > best_wpm,
            accuracy=result.accuracy > best_accuracy,
            score=result.score > best_score,
            previous_wpm=best_wpm,
        )

    def add(self, result: TestResult) -> Records:
        records = self.evaluate(result)
        self.entries.append(result)
        if len(self.entries) > MAX_ENTRIES:
            self.entries = self.entries[-MAX_ENTRIES:]
        return records

    # -------------------------------------------------------------- consultas

    def recent(self, count: int = 10) -> list[TestResult]:
        return list(reversed(self.entries[-count:]))

    def best_wpm(self) -> TestResult | None:
        return max(self.entries, key=lambda e: e.wpm, default=None)

    def best_accuracy(self) -> TestResult | None:
        return max(self.entries, key=lambda e: e.accuracy, default=None)

    def best_score(self) -> TestResult | None:
        return max(self.entries, key=lambda e: e.score, default=None)

    def average_wpm(self, count: int = 10) -> float:
        window = self.entries[-count:]
        if not window:
            return 0.0
        return sum(e.wpm for e in window) / len(window)

    def average_accuracy(self, count: int = 10) -> float:
        window = self.entries[-count:]
        if not window:
            return 0.0
        return sum(e.accuracy for e in window) / len(window)

    def today(self) -> list[TestResult]:
        start = _start_of_today()
        return [e for e in self.entries if e.timestamp >= start]

    def best_today(self) -> TestResult | None:
        return max(self.today(), key=lambda e: e.wpm, default=None)

    def __len__(self) -> int:
        return len(self.entries)


def _start_of_today() -> float:
    now = time.localtime()
    midnight = time.struct_time(
        (now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, now.tm_wday, now.tm_yday, -1)
    )
    return time.mktime(midnight)
