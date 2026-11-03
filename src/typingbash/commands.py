"""Sistema de comandos estilo Monkeytype.

Cada comando es una entrada en un registro, con su nombre, sus alias, su ayuda
y una función pura que recibe el contexto y los argumentos. Añadir uno nuevo es
escribir una función y decorarla con :func:`command`; la ayuda y el
autocompletado se generan solos a partir del registro.

Los handlers no tocan la interfaz: devuelven un :class:`CommandResult` con un
mensaje y, opcionalmente, una acción que la aplicación interpreta. Así se
pueden testear sin terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from .config import FIELDS, FIELDS_BY_NAME, Config, ConfigError

# Acciones que la aplicación sabe ejecutar tras un comando.
ACTION_QUIT = "quit"
ACTION_RESTART = "restart"
ACTION_MENU = "menu"
ACTION_HELP = "help"
ACTION_STATS = "stats"
ACTION_SETTINGS = "settings"
ACTION_HISTORY = "history"


class Context(Protocol):
    """Lo mínimo que un comando necesita de la aplicación."""

    config: Config

    def save_config(self) -> None: ...


@dataclass
class CommandResult:
    message: str = ""
    level: str = "info"  # info | success | error
    action: str | None = None
    config_changed: bool = False

    @classmethod
    def error(cls, message: str) -> "CommandResult":
        return cls(message=message, level="error")

    @classmethod
    def ok(cls, message: str = "", **kwargs) -> "CommandResult":
        return cls(message=message, level="success", **kwargs)


Handler = Callable[[Context, list[str]], CommandResult]


@dataclass(frozen=True)
class Command:
    name: str
    usage: str
    summary: str
    handler: Handler
    aliases: tuple[str, ...] = ()
    group: str = "general"


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: Command) -> Command:
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name
        return command

    def resolve(self, name: str) -> Command | None:
        key = name.lower()
        if key in self._commands:
            return self._commands[key]
        target = self._aliases.get(key)
        return self._commands.get(target) if target else None

    def all(self) -> list[Command]:
        return list(self._commands.values())

    def suggestions(self, prefix: str) -> list[str]:
        """Nombres que empiezan por ``prefix``, para el autocompletado."""
        clean = prefix.lstrip("/").lower()
        names = sorted(set(self._commands) | set(self._aliases))
        if not clean:
            return sorted(self._commands)
        return [name for name in names if name.startswith(clean)]

    def dispatch(self, text: str, context: Context) -> CommandResult:
        """Interpreta una línea completa tal cual la escribe el usuario."""
        raw = text.strip()
        if not raw:
            return CommandResult()
        if raw.startswith("/"):
            raw = raw[1:]
        parts = raw.split()
        if not parts:
            return CommandResult()
        name, args = parts[0], parts[1:]

        command = self.resolve(name)
        if command is None:
            close = self.suggestions(name)
            hint = f" ¿Querías decir /{close[0]}?" if close else ""
            return CommandResult.error(
                f"Comando desconocido: /{name}.{hint} Escribe /help para ver la lista."
            )
        try:
            return command.handler(context, args)
        except ConfigError as exc:
            return CommandResult.error(str(exc))
        except Exception as exc:  # pragma: no cover - red de seguridad
            return CommandResult.error(f"El comando falló: {exc}")


registry = CommandRegistry()


def command(name: str, usage: str, summary: str, *, aliases=(), group="general"):
    def decorator(func: Handler) -> Handler:
        registry.register(
            Command(name=name, usage=usage, summary=summary, handler=func,
                    aliases=tuple(aliases), group=group)
        )
        return func

    return decorator


def _apply(context: Context, field_name: str, raw: str, label: str) -> CommandResult:
    """Valida y aplica un ajuste, con mensaje uniforme de confirmación."""
    value = context.config.set_value(field_name, raw)
    context.save_config()
    return CommandResult.ok(f"{label}: {value}", config_changed=True)


# --------------------------------------------------------------------- modos


@command("time", "/time <segundos>", "Cambia a modo tiempo", aliases=("t",), group="modo")
def _cmd_time(context: Context, args: list[str]) -> CommandResult:
    field = FIELDS_BY_NAME["time_seconds"]
    if not args:
        return CommandResult(
            f"Modo tiempo actual: {context.config.time_seconds}s "
            f"(válido de {field.minimum} a {field.maximum}). Usa /time <segundos>"
        )
    try:
        context.config.set_value("time_seconds", args[0])
    except ConfigError:
        return CommandResult.error(
            f"Tiempo inválido. Usa /time <segundos> entre {field.minimum} y {field.maximum}"
        )
    context.config.mode = "time"
    context.save_config()
    return CommandResult.ok(
        f"Modo tiempo · {context.config.time_seconds}s",
        action=ACTION_RESTART,
        config_changed=True,
    )


@command("words", "/words <cantidad>", "Cambia a modo palabras", aliases=("w",), group="modo")
def _cmd_words(context: Context, args: list[str]) -> CommandResult:
    field = FIELDS_BY_NAME["word_count"]
    if not args:
        return CommandResult(
            f"Modo palabras actual: {context.config.word_count} "
            f"(válido de {field.minimum} a {field.maximum}). Usa /words <cantidad>"
        )
    try:
        context.config.set_value("word_count", args[0])
    except ConfigError:
        return CommandResult.error(
            f"Cantidad inválida. Usa /words <cantidad> entre {field.minimum} y {field.maximum}"
        )
    context.config.mode = "words"
    context.save_config()
    return CommandResult.ok(
        f"Modo palabras · {context.config.word_count}",
        action=ACTION_RESTART,
        config_changed=True,
    )


@command("difficulty", "/difficulty <nivel>", "Cambia la dificultad",
         aliases=("diff", "d"), group="modo")
def _cmd_difficulty(context: Context, args: list[str]) -> CommandResult:
    if not args:
        options = ", ".join(FIELDS_BY_NAME["difficulty"].options())
        return CommandResult(
            f"Dificultad actual: {context.config.difficulty}. Opciones: {options}"
        )
    result = _apply(context, "difficulty", args[0], "Dificultad")
    result.action = ACTION_RESTART
    return result


@command("language", "/language <idioma>", "Cambia el idioma",
         aliases=("lang", "l"), group="modo")
def _cmd_language(context: Context, args: list[str]) -> CommandResult:
    from .words import language_name

    options = FIELDS_BY_NAME["language"].options()
    if not args:
        listing = ", ".join(f"{code} ({language_name(code)})" for code in options)
        return CommandResult(
            f"Idioma actual: {context.config.language} "
            f"({language_name(context.config.language)}). Disponibles: {listing}"
        )
    result = _apply(context, "language", args[0], "Idioma")
    result.action = ACTION_RESTART
    return result


@command("theme", "/theme <tema>", "Cambia la paleta de colores", group="apariencia")
def _cmd_theme(context: Context, args: list[str]) -> CommandResult:
    options = FIELDS_BY_NAME["theme"].options()
    if not args:
        return CommandResult(
            f"Tema actual: {context.config.theme}. Disponibles: {', '.join(options)}"
        )
    return _apply(context, "theme", args[0], "Tema")


@command("size", "/size <tamaño>", "Cuánta pantalla ocupa la interfaz",
         aliases=("ui",), group="apariencia")
def _cmd_size(context: Context, args: list[str]) -> CommandResult:
    options = FIELDS_BY_NAME["ui_size"].options()
    if not args:
        return CommandResult(
            f"Tamaño actual: {context.config.ui_size}. Disponibles: {', '.join(options)}"
        )
    return _apply(context, "ui_size", args[0], "Tamaño")


@command("set", "/set <ajuste> <valor>", "Cambia cualquier ajuste", group="apariencia")
def _cmd_set(context: Context, args: list[str]) -> CommandResult:
    if len(args) < 2:
        names = ", ".join(f.name for f in FIELDS)
        return CommandResult.error(f"Usa /set <ajuste> <valor>. Ajustes: {names}")
    name = args[0].lower()
    if name not in FIELDS_BY_NAME:
        return CommandResult.error(f"Ajuste desconocido: {name}. Escribe /settings")
    return _apply(context, name, " ".join(args[1:]), FIELDS_BY_NAME[name].label)


# ------------------------------------------------------------------ pantallas


@command("help", "/help", "Muestra esta ayuda", aliases=("h", "?"), group="pantalla")
def _cmd_help(context: Context, args: list[str]) -> CommandResult:
    return CommandResult(action=ACTION_HELP)


@command("settings", "/settings", "Muestra los ajustes actuales",
         aliases=("config",), group="pantalla")
def _cmd_settings(context: Context, args: list[str]) -> CommandResult:
    return CommandResult(action=ACTION_SETTINGS)


@command("stats", "/stats", "Estadísticas de la sesión y globales", group="pantalla")
def _cmd_stats(context: Context, args: list[str]) -> CommandResult:
    return CommandResult(action=ACTION_STATS)


@command("history", "/history", "Historial de resultados", aliases=("hist",), group="pantalla")
def _cmd_history(context: Context, args: list[str]) -> CommandResult:
    return CommandResult(action=ACTION_HISTORY)


@command("restart", "/restart", "Reinicia el test actual", aliases=("r",), group="pantalla")
def _cmd_restart(context: Context, args: list[str]) -> CommandResult:
    return CommandResult(action=ACTION_RESTART)


@command("menu", "/menu", "Vuelve al menú principal", group="pantalla")
def _cmd_menu(context: Context, args: list[str]) -> CommandResult:
    return CommandResult(action=ACTION_MENU)


@command("quit", "/quit", "Sale del programa", aliases=("q", "exit"), group="pantalla")
def _cmd_quit(context: Context, args: list[str]) -> CommandResult:
    return CommandResult(action=ACTION_QUIT)
