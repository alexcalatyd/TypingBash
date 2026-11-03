"""Diccionarios y selección de palabras.

El objetivo no es solo "sacar una palabra al azar", sino que cada test se
sienta distinto y natural:

  * las listas están ordenadas por frecuencia aproximada y se ponderan, de
    modo que salen más veces las palabras comunes sin que las raras
    desaparezcan;
  * no se repite ninguna de las últimas N palabras;
  * se evitan familias léxicas seguidas (``casa casas casita``) comparando
    prefijos sin acentos;
  * se evita encadenar demasiadas palabras de la misma longitud.
"""

from __future__ import annotations

import json
import random
import unicodedata
from collections import deque
from dataclasses import dataclass
from functools import lru_cache

from . import paths

DEFAULT_LANGUAGE = "es"
_STEM_LENGTH = 4
_STEM_WINDOW = 8
_MAX_ATTEMPTS = 40


class DictionaryError(RuntimeError):
    """No se pudo cargar un diccionario."""


@dataclass(frozen=True)
class LanguageInfo:
    code: str
    name: str
    common: str
    extended: str | None = None


@lru_cache(maxsize=1)
def _registry() -> dict[str, LanguageInfo]:
    path = paths.data_dir() / "languages.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DictionaryError(f"No se pudo leer {path}: {exc}") from exc

    registry: dict[str, LanguageInfo] = {}
    for code, entry in raw.items():
        if not (paths.data_dir() / entry["common"]).exists():
            continue  # idioma declarado pero sin fichero: se ignora
        extended = entry.get("extended")
        if extended and not (paths.data_dir() / extended).exists():
            extended = None
        registry[code] = LanguageInfo(
            code=code, name=entry.get("name", code), common=entry["common"],
            extended=extended,
        )
    if not registry:
        raise DictionaryError(f"No hay diccionarios en {paths.data_dir()}")
    return registry


def available_languages() -> list[str]:
    try:
        return sorted(_registry())
    except DictionaryError:
        return [DEFAULT_LANGUAGE]


def language_name(code: str) -> str:
    try:
        info = _registry().get(code)
    except DictionaryError:
        return code
    return info.name if info else code


def _read_words(relative: str) -> list[str]:
    path = paths.data_dir() / relative
    words: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            word = line.strip()
            if not word or word.startswith("#") or word in seen:
                continue
            seen.add(word)
            words.append(word)
    return words


def strip_accents(text: str) -> str:
    """``camión`` -> ``camion``. Solo para comparar, nunca para mostrar."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def stem(word: str) -> str:
    return strip_accents(word.lower())[:_STEM_LENGTH]


@dataclass(frozen=True)
class Pool:
    """Conjunto de palabras candidatas con sus pesos de selección."""

    words: tuple[str, ...]
    weights: tuple[float, ...]

    def __len__(self) -> int:
        return len(self.words)


class Dictionary:
    """Las listas de un idioma, ya cargadas en memoria."""

    def __init__(self, code: str, name: str, common: list[str], extended: list[str]) -> None:
        self.code = code
        self.name = name
        self.common = common
        self.extended = extended

    @classmethod
    def load(cls, code: str) -> "Dictionary":
        registry = _registry()
        info = registry.get(code) or registry.get(DEFAULT_LANGUAGE) or next(iter(registry.values()))
        try:
            common = _read_words(info.common)
            extended = _read_words(info.extended) if info.extended else []
        except OSError as exc:
            raise DictionaryError(f"No se pudo leer el diccionario '{code}': {exc}") from exc
        if not common:
            raise DictionaryError(f"El diccionario '{code}' está vacío")
        return cls(info.code, info.name, common, extended)

    def pool(self, difficulty: str) -> Pool:
        """Construye el conjunto candidato para una dificultad.

        * ``easy``   palabras muy frecuentes y cortas (<= 6 letras);
        * ``normal`` toda la lista común, ponderada por frecuencia;
        * ``hard``   lista común sin las partículas más triviales, más la
          lista extendida, favoreciendo palabras largas.
        """
        if difficulty == "easy":
            head = self.common[: max(60, int(len(self.common) * 0.55))]
            words = [w for w in head if len(w) <= 6]
            if len(words) < 40:  # diccionario pequeño: no filtramos tanto
                words = head
            weights = [_frequency_weight(i, len(words)) for i in range(len(words))]
            return Pool(tuple(words), tuple(weights))

        if difficulty == "hard":
            skip = 100 if len(self.common) > 300 else 0
            words = list(self.common[skip:]) + [
                w for w in self.extended if w not in set(self.common)
            ]
            weights = [_length_weight(word) for word in words]
            return Pool(tuple(words), tuple(weights))

        words = list(self.common)
        weights = [_frequency_weight(i, len(words)) for i in range(len(words))]
        return Pool(tuple(words), tuple(weights))


def _frequency_weight(index: int, total: int) -> float:
    """Decae suavemente: la más común pesa 1.0 y la más rara 0.4."""
    if total <= 1:
        return 1.0
    return 1.0 - 0.6 * (index / (total - 1))


def _length_weight(word: str) -> float:
    """En ``hard`` las palabras largas salen más, sin excluir las cortas."""
    return 0.35 + min(len(word), 14) / 14.0


class WordSelector:
    """Generador de palabras con memoria de las recién usadas."""

    def __init__(
        self,
        dictionary: Dictionary,
        difficulty: str = "normal",
        rng: random.Random | None = None,
    ) -> None:
        self.dictionary = dictionary
        self.difficulty = difficulty
        self.rng = rng or random.Random()
        self.pool = dictionary.pool(difficulty)
        if not self.pool.words:
            raise DictionaryError("No hay palabras para esta dificultad")

        recent_size = max(8, min(60, len(self.pool) // 4))
        self._recent: deque[str] = deque(maxlen=recent_size)
        self._recent_set: set[str] = set()
        self._stems: deque[str] = deque(maxlen=_STEM_WINDOW)
        self._lengths: deque[int] = deque(maxlen=2)

    def next_word(self) -> str:
        candidate = self._pick()
        self._remember(candidate)
        return candidate

    def take(self, count: int) -> list[str]:
        return [self.next_word() for _ in range(max(0, count))]

    # ------------------------------------------------------------- interno

    def _pick(self) -> str:
        fallback: str | None = None
        for attempt in range(_MAX_ATTEMPTS):
            word = self.rng.choices(self.pool.words, weights=self.pool.weights, k=1)[0]
            if fallback is None:
                fallback = word
            if word in self._recent_set:
                continue
            if stem(word) in self._stems:
                continue
            # Solo en los primeros intentos exigimos variedad de longitud: es
            # una preferencia, no una restricción dura.
            if attempt < _MAX_ATTEMPTS // 2 and len(self._lengths) == 2:
                if all(length == len(word) for length in self._lengths):
                    continue
            return word
        return fallback or self.pool.words[0]

    def _remember(self, word: str) -> None:
        if len(self._recent) == self._recent.maxlen and self._recent:
            self._recent_set.discard(self._recent[0])
        self._recent.append(word)
        self._recent_set.add(word)
        self._stems.append(stem(word))
        self._lengths.append(len(word))
