"""Lógica del test de mecanografía, independiente de la interfaz.

Todo lo que hay aquí se puede ejercitar sin terminal: se le inyecta un reloj y
un selector de palabras, se le mandan pulsaciones y devuelve estado. Es lo que
permite testear las reglas de negocio de verdad.

Reglas de conteo
----------------
* Un carácter es correcto si coincide **exactamente** con el objetivo, así que
  ``ñ`` no vale por ``n`` ni ``á`` por ``a``.
* El espacio que separa dos palabras cuenta como un carácter más: correcto si
  la palabra recién cerrada era exacta, incorrecto si no lo era.
* Para la *precisión* se miran las pulsaciones, no el texto final: corregir un
  fallo con retroceso arregla el texto pero el fallo sigue contando.
* Los caracteres que el test corta a medias (se acabó el tiempo en mitad de
  una palabra) no cuentan como omitidos: no llegaste a tener la oportunidad.
"""

from __future__ import annotations

import time
from enum import Enum

from .stats import (
    CharCounts,
    LiveStats,
    TestResult,
    WordCounts,
    accuracy,
    consistency,
    raw_wpm,
    score,
    wpm,
)
from .words import WordSelector

# Cuántas palabras se mantienen por delante en modo tiempo. Tiene que dar de
# sobra para llenar la pantalla más grande posible (5 líneas de 120 columnas
# rondan las 100 palabras visibles), o se verían líneas a medias.
LOOKAHEAD = 180
REFILL_THRESHOLD = 120
# Tope de caracteres sobrantes que se aceptan al final de una palabra.
MAX_EXTRA_CHARS = 10


class Phase(Enum):
    READY = "ready"  # esperando la primera pulsación
    RUNNING = "running"
    FINISHED = "finished"


class TypingTest:
    """Una partida. Se crea una instancia nueva por cada test."""

    def __init__(
        self,
        selector: WordSelector,
        *,
        mode: str = "time",
        time_seconds: int = 30,
        word_count: int = 25,
        language: str = "es",
        difficulty: str = "normal",
        stop_on_error: bool = False,
        clock=time.monotonic,
    ) -> None:
        self.selector = selector
        self.mode = mode if mode in ("time", "words") else "time"
        self.time_seconds = max(1, int(time_seconds))
        self.word_count = max(1, int(word_count))
        self.language = language
        self.difficulty = difficulty
        self.stop_on_error = stop_on_error
        self._clock = clock

        self.phase = Phase.READY
        self.started_at: float | None = None
        self.finished_at: float | None = None

        initial = self.word_count if self.mode == "words" else LOOKAHEAD
        self.words: list[str] = selector.take(initial)
        self.typed_words: list[str] = []
        self.index = 0
        self.buffer = ""

        self.stats = LiveStats()
        self._chars = CharCounts()
        self._words = WordCounts()

    # ------------------------------------------------------------ propiedades

    @property
    def target(self) -> str:
        return self.words[self.index] if self.index < len(self.words) else ""

    @property
    def is_finished(self) -> bool:
        return self.phase is Phase.FINISHED

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else self._clock()
        return max(0.0, end - self.started_at)

    @property
    def remaining_seconds(self) -> float:
        if self.mode != "time":
            return 0.0
        return max(0.0, self.time_seconds - self.elapsed)

    @property
    def progress(self) -> float:
        """Fracción completada del test, entre 0.0 y 1.0."""
        if self.mode == "time":
            return min(1.0, self.elapsed / self.time_seconds)
        return min(1.0, self.index / self.word_count)

    @property
    def has_error_in_buffer(self) -> bool:
        target = self.target
        if len(self.buffer) > len(target):
            return True
        return any(self.buffer[i] != target[i] for i in range(len(self.buffer)))

    def live_wpm(self) -> float:
        return wpm(self._correct_chars_so_far(), self.elapsed)

    def live_accuracy(self) -> float:
        return self.stats.live_accuracy

    def _correct_chars_so_far(self) -> int:
        """Correctos ya consolidados más los del buffer en curso."""
        partial, _, _ = _compare(self.buffer, self.target)
        return self._chars.correct + partial

    # ------------------------------------------------------------------ input

    def _ensure_started(self) -> None:
        if self.phase is Phase.READY:
            self.phase = Phase.RUNNING
            self.started_at = self._clock()

    def type_char(self, char: str) -> None:
        """Procesa un carácter imprimible (incluido el espacio)."""
        if self.phase is Phase.FINISHED or not char:
            return
        if char == " ":
            self._submit_word()
            return

        self._ensure_started()

        if self.stop_on_error and self.has_error_in_buffer:
            # Modo estricto: no se avanza hasta corregir.
            return
        if len(self.buffer) >= len(self.target) + MAX_EXTRA_CHARS:
            return

        position = len(self.buffer)
        correct = position < len(self.target) and char == self.target[position]
        self.buffer += char
        self.stats.record_keystroke(correct)
        self._check_word_mode_autofinish()

    def compose_last(self, mark: str) -> None:
        """Fusiona una marca combinante con el último carácter tecleado.

        Solo entra en juego si la terminal entrega las teclas muertas sin
        precomponer; en macOS lo normal es que ya lleguen como ``á``.
        """
        from .keys import compose

        if not self.buffer or self.phase is Phase.FINISHED:
            return
        merged = compose(self.buffer[-1], mark)
        if merged == self.buffer[-1]:
            return
        position = len(self.buffer) - 1
        was_correct = position < len(self.target) and self.buffer[-1] == self.target[position]
        now_correct = position < len(self.target) and merged == self.target[position]
        self.buffer = self.buffer[:-1] + merged
        if was_correct != now_correct:
            # Reajusta la pulsación ya contabilizada.
            if now_correct:
                self.stats.correct_keystrokes += 1
                self.stats.error_keystrokes -= 1
            else:
                self.stats.correct_keystrokes -= 1
                self.stats.error_keystrokes += 1
        self._check_word_mode_autofinish()

    def backspace(self, whole_word: bool = False) -> None:
        """Borra un carácter, o la palabra entera con ctrl/alt + retroceso."""
        if self.phase is Phase.FINISHED:
            return
        if self.buffer:
            self.buffer = "" if whole_word else self.buffer[:-1]
            return
        # Buffer vacío: se puede volver a una palabra anterior mal escrita,
        # igual que en Monkeytype. Las palabras perfectas quedan cerradas.
        if self.index == 0 or not self.typed_words:
            return
        if self.typed_words[-1] == self.words[self.index - 1]:
            return
        self.index -= 1
        previous = self.typed_words.pop()
        self._unaccount_word(self.words[self.index], previous)
        self.buffer = "" if whole_word else previous

    def _submit_word(self) -> None:
        if self.phase is Phase.FINISHED:
            return
        if not self.buffer:
            return  # espacios sueltos: no abren palabra ni cuentan
        self._ensure_started()

        target = self.target
        typed = self.buffer

        self._account_word(target, typed, with_separator=True)
        # Pulsar espacio ahí era la acción correcta, así que la precisión no
        # se resiente aunque la palabra estuviera mal escrita.
        self.stats.record_keystroke(True)

        self.typed_words.append(typed)
        self.index += 1
        self.buffer = ""

        if self.mode == "words" and self.index >= self.word_count:
            self.finish()
            return
        self._refill()

    def _check_word_mode_autofinish(self) -> None:
        """En modo palabras, acertar la última palabra cierra el test."""
        if self.mode != "words" or self.index != self.word_count - 1:
            return
        if self.buffer and self.buffer == self.target:
            self._account_word(self.target, self.buffer, with_separator=False)
            self.typed_words.append(self.buffer)
            self.index += 1
            self.buffer = ""
            self.finish()

    # -------------------------------------------------------------- contadores

    def _account_word(self, target: str, typed: str, with_separator: bool) -> None:
        correct, incorrect, extra = _compare(typed, target)
        missed = max(0, len(target) - len(typed))
        self._chars.correct += correct
        self._chars.incorrect += incorrect
        self._chars.extra += extra
        self._chars.missed += missed
        if typed == target:
            self._words.correct += 1
            if with_separator:
                self._chars.correct += 1
        else:
            self._words.incorrect += 1
            if with_separator:
                self._chars.incorrect += 1

    def _unaccount_word(self, target: str, typed: str) -> None:
        """Revierte el conteo al volver atrás con retroceso."""
        correct, incorrect, extra = _compare(typed, target)
        missed = max(0, len(target) - len(typed))
        self._chars.correct -= correct
        self._chars.incorrect -= incorrect
        self._chars.extra -= extra
        self._chars.missed -= missed
        if typed == target:
            self._words.correct -= 1
            self._chars.correct -= 1
        else:
            self._words.incorrect -= 1
            self._chars.incorrect -= 1

    def _refill(self) -> None:
        if self.mode != "time":
            return
        if len(self.words) - self.index < REFILL_THRESHOLD:
            self.words.extend(self.selector.take(LOOKAHEAD))

    # ------------------------------------------------------------------ ciclo

    def tick(self) -> None:
        """Se llama en cada fotograma: muestrea el ritmo y vigila el tiempo."""
        if self.phase is not Phase.RUNNING:
            return
        self.stats.sample(self.elapsed)
        if self.mode == "time" and self.elapsed >= self.time_seconds:
            self.finish()

    def finish(self) -> None:
        if self.phase is Phase.FINISHED:
            return
        if self.phase is Phase.READY:
            self.started_at = self._clock()
        self.finished_at = self._clock()
        if self.mode == "time":
            # El corte es exacto aunque el fotograma llegue tarde.
            self.finished_at = min(
                self.finished_at, (self.started_at or self.finished_at) + self.time_seconds
            )
        # La palabra a medias también cuenta lo que se llegó a escribir.
        if self.buffer:
            correct, incorrect, extra = _compare(self.buffer, self.target)
            self._chars.correct += correct
            self._chars.incorrect += incorrect
            self._chars.extra += extra
            if self.buffer == self.target:
                self._words.correct += 1
            else:
                self._words.incorrect += 1
            self.typed_words.append(self.buffer)
            self.index += 1
            self.buffer = ""
        self.phase = Phase.FINISHED
        self.stats.sample(self.elapsed)

    def result(self) -> TestResult:
        duration = self.elapsed
        chars = CharCounts(**vars(self._chars))
        speed = wpm(chars.correct, duration)
        raw = raw_wpm(self.stats.typed_chars, duration)
        acc = accuracy(self.stats.correct_keystrokes, self.stats.total_keystrokes)
        cons = consistency(self.stats.series)
        return TestResult(
            wpm=speed,
            raw_wpm=raw,
            accuracy=acc,
            consistency=cons,
            score=score(chars.correct, acc, speed),
            duration=duration,
            chars=chars,
            words=WordCounts(**vars(self._words)),
            mode=self.mode,
            mode_value=self.time_seconds if self.mode == "time" else self.word_count,
            language=self.language,
            difficulty=self.difficulty,
            wpm_series=list(self.stats.series),
        )


def _compare(typed: str, target: str) -> tuple[int, int, int]:
    """Devuelve (correctos, incorrectos, sobrantes) comparando carácter a carácter."""
    correct = incorrect = 0
    shared = min(len(typed), len(target))
    for i in range(shared):
        if typed[i] == target[i]:
            correct += 1
        else:
            incorrect += 1
    extra = max(0, len(typed) - len(target))
    return correct, incorrect, extra
