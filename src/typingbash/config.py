"""Configuración del usuario: valores por defecto, validación y persistencia.

Cada ajuste se declara una sola vez en :data:`FIELDS`. De ahí salen la
validación, la pantalla de ajustes y los comandos ``/set``, así que añadir una
opción nueva es añadir una entrada a esa tabla.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from typing import Any, Callable

from . import paths

MIN_TIME, MAX_TIME = 5, 600
MIN_WORDS, MAX_WORDS = 5, 500

DIFFICULTIES = ("easy", "normal", "hard")
MODES = ("time", "words")
# Cuánto de la terminal ocupa la interfaz. Ver :mod:`typingbash.ui`.
UI_SIZES = ("large", "medium", "small")


class ConfigError(ValueError):
    """Valor de configuración inválido, con un mensaje apto para el usuario."""


@dataclass
class Field:
    """Descripción de un ajuste: cómo se valida y cómo se enseña."""

    name: str
    label: str
    kind: str  # "bool" | "int" | "choice"
    description: str
    choices: tuple[str, ...] = ()
    minimum: int = 0
    maximum: int = 0
    choices_provider: Callable[[], tuple[str, ...]] | None = None

    def options(self) -> tuple[str, ...]:
        if self.choices_provider is not None:
            return tuple(self.choices_provider())
        return self.choices


def _languages() -> tuple[str, ...]:
    from .words import available_languages

    return tuple(available_languages())


def _themes() -> tuple[str, ...]:
    from .theme import theme_names

    return tuple(theme_names())


FIELDS: tuple[Field, ...] = (
    Field("mode", "Modo", "choice", "Cómo termina el test", choices=MODES),
    Field("time_seconds", "Tiempo", "int", "Duración en modo tiempo",
          minimum=MIN_TIME, maximum=MAX_TIME),
    Field("word_count", "Palabras", "int", "Palabras en modo palabras",
          minimum=MIN_WORDS, maximum=MAX_WORDS),
    Field("language", "Idioma", "choice", "Diccionario en uso",
          choices_provider=_languages),
    Field("difficulty", "Dificultad", "choice", "Longitud y rareza de las palabras",
          choices=DIFFICULTIES),
    Field("theme", "Tema", "choice", "Paleta de colores", choices_provider=_themes),
    Field("ui_size", "Tamaño", "choice",
          "Cuánto ocupa la interfaz: large llena la pantalla", choices=UI_SIZES),
    Field("big_counter", "Contador grande", "bool",
          "Cronómetro en cifras de bloque si la ventana es alta"),
    Field("live_wpm", "WPM en vivo", "bool", "Mostrar velocidad durante el test"),
    Field("live_accuracy", "Precisión en vivo", "bool", "Mostrar precisión durante el test"),
    Field("animations", "Animaciones", "bool", "Logo, cuenta atrás y celebraciones"),
    Field("countdown", "Cuenta atrás", "bool", "Contar 3·2·1 antes de empezar"),
    Field("sound", "Sonido", "bool", "Pitido corto al fallar y al terminar"),
    Field("stop_on_error", "Parar al fallar", "bool",
          "No dejar avanzar mientras haya un error sin corregir"),
)

FIELDS_BY_NAME: dict[str, Field] = {field.name: field for field in FIELDS}


@dataclass
class Config:
    language: str = "es"
    mode: str = "time"
    time_seconds: int = 30
    word_count: int = 25
    difficulty: str = "normal"
    theme: str = "minimal"
    ui_size: str = "large"
    big_counter: bool = True
    live_wpm: bool = True
    live_accuracy: bool = True
    animations: bool = True
    countdown: bool = True
    sound: bool = False
    stop_on_error: bool = False

    # ------------------------------------------------------------ validación

    def validate(self) -> None:
        """Corrige silenciosamente cualquier valor fuera de rango.

        Un fichero de configuración corrupto o editado a mano no debe impedir
        que el juego arranque.
        """
        if self.mode not in MODES:
            self.mode = "time"
        if self.difficulty not in DIFFICULTIES:
            self.difficulty = "normal"
        from .theme import THEMES
        if self.theme not in THEMES:
            self.theme = "minimal"
        from .words import available_languages
        if self.language not in available_languages():
            self.language = "es"
        if self.ui_size not in UI_SIZES:
            self.ui_size = "large"
        self.time_seconds = _clamp(self.time_seconds, MIN_TIME, MAX_TIME, 30)
        self.word_count = _clamp(self.word_count, MIN_WORDS, MAX_WORDS, 25)
        for field in FIELDS:
            if field.kind == "bool":
                setattr(self, field.name, bool(getattr(self, field.name)))

    def set_value(self, name: str, raw: Any) -> Any:
        """Asigna un ajuste validando el valor. Lanza :class:`ConfigError`."""
        field = FIELDS_BY_NAME.get(name)
        if field is None:
            raise ConfigError(f"Ajuste desconocido: {name}")
        value = parse_value(field, raw)
        setattr(self, name, value)
        return value

    # ---------------------------------------------------------- persistencia

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f.name for f in fields(cls)}
        config = cls(**{k: v for k, v in data.items() if k in known})
        config.validate()
        return config

    @classmethod
    def load(cls) -> "Config":
        path = paths.config_file()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, json.JSONDecodeError, TypeError):
            # Configuración ilegible: seguimos con los valores por defecto.
            return cls()
        if not isinstance(data, dict):
            return cls()
        try:
            return cls.from_dict(data)
        except TypeError:
            return cls()

    def save(self) -> bool:
        """Guarda de forma atómica. Devuelve False si no se pudo escribir."""
        try:
            paths.ensure_user_dir()
            path = paths.config_file()
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------- ayudantes

    def describe_mode(self) -> str:
        if self.mode == "time":
            return f"{self.time_seconds}s"
        return f"{self.word_count} palabras"


def _clamp(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


_TRUE = {"1", "true", "on", "yes", "sí", "si", "y"}
_FALSE = {"0", "false", "off", "no", "n"}


def parse_value(field: Field, raw: Any) -> Any:
    """Convierte y valida un valor textual para el ajuste ``field``."""
    if field.kind == "bool":
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        raise ConfigError(f"{field.label}: usa on u off")

    if field.kind == "int":
        try:
            number = int(str(raw).strip())
        except (TypeError, ValueError):
            raise ConfigError(
                f"{field.label}: debe ser un número entre {field.minimum} y {field.maximum}"
            ) from None
        if not field.minimum <= number <= field.maximum:
            raise ConfigError(
                f"{field.label}: debe estar entre {field.minimum} y {field.maximum}"
            )
        return number

    text = str(raw).strip().lower()
    options = field.options()
    if text not in options:
        raise ConfigError(f"{field.label}: opciones válidas → {', '.join(options)}")
    return text
