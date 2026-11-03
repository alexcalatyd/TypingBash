"""Punto de entrada: ``typingbash``, ``python3 -m typingbash`` o ``./typingbash``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import DIFFICULTIES, UI_SIZES, Config, ConfigError
from .terminal import TerminalError
from .theme import theme_names
from .words import DictionaryError, available_languages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="typingbash",
        description="Juego de mecanografía para la terminal, en español.",
        epilog="Dentro del juego, escribe /help para ver todos los comandos.",
    )
    parser.add_argument("--time", type=int, metavar="SEGUNDOS",
                        help="modo tiempo con la duración indicada")
    parser.add_argument("--words", type=int, metavar="CANTIDAD",
                        help="modo palabras con la cantidad indicada")
    parser.add_argument("--difficulty", choices=DIFFICULTIES, help="nivel de dificultad")
    parser.add_argument("--language", metavar="IDIOMA", help="código de idioma (es, en...)")
    parser.add_argument("--theme", metavar="TEMA", help="paleta de colores")
    parser.add_argument("--size", choices=UI_SIZES,
                        help="cuánta pantalla ocupa la interfaz")
    parser.add_argument("--no-animations", action="store_true",
                        help="desactiva animaciones y cuenta atrás")
    parser.add_argument("--start", action="store_true",
                        help="salta el menú y empieza un test directamente")
    parser.add_argument("--list", action="store_true",
                        help="muestra idiomas y temas disponibles y sale")
    parser.add_argument("--version", action="version", version=f"typingbash {__version__}")
    return parser


def apply_arguments(config: Config, args: argparse.Namespace) -> None:
    """Los argumentos pisan la configuración guardada solo para esta ejecución."""
    if args.time is not None:
        config.set_value("time_seconds", args.time)
        config.mode = "time"
    if args.words is not None:
        config.set_value("word_count", args.words)
        config.mode = "words"
    if args.difficulty:
        config.set_value("difficulty", args.difficulty)
    if args.language:
        config.set_value("language", args.language)
    if args.theme:
        config.set_value("theme", args.theme)
    if args.size:
        config.set_value("ui_size", args.size)
    if args.no_animations:
        config.animations = False
        config.countdown = False


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        from .words import language_name

        print("Idiomas:")
        for code in available_languages():
            print(f"  {code:<4} {language_name(code)}")
        print("Temas:")
        for name in theme_names():
            print(f"  {name}")
        return 0

    config = Config.load()
    try:
        apply_arguments(config, args)
    except ConfigError as exc:
        parser.error(str(exc))
    config.validate()

    from .app import App

    try:
        app = App(config)
    except DictionaryError as exc:
        print(f"Error cargando el diccionario: {exc}", file=sys.stderr)
        return 2

    if args.start:
        app.start_test()

    try:
        return app.run()
    except TerminalError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
