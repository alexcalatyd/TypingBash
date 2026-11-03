"""Aplicación: bucle principal, navegación entre pantallas y estado global.

El bucle es deliberadamente simple: leer teclas → avanzar el tiempo → componer
el fotograma → volcar solo las diferencias. La frecuencia la marca la pantalla
activa, de modo que el menú no consume CPU y el test se refresca 20 veces por
segundo.
"""

from __future__ import annotations

import time

from . import commands as command_module
from .commands import CommandResult, registry
from .config import Config
from .engine import Phase, TypingTest
from .history import History
from .keys import InputReader, Key
from .prompt import CommandPrompt
from .render import Screen
from .sound import SoundPlayer
from .stats import TestResult
from .terminal import Terminal
from .theme import Palette, get_theme
from .ui import draw_hints
from .words import Dictionary, WordSelector
from .screens import (
    HelpView,
    HistoryView,
    MenuView,
    ResultsView,
    SettingsView,
    StatsView,
    TestView,
    View,
)

MIN_WIDTH = 60
MIN_HEIGHT = 18
MESSAGE_SECONDS = 3.5
IDLE_TIMEOUT = 0.25


class App:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()
        self.config.validate()
        self.history = History.load()
        self.session: list[TestResult] = []

        self.palette = Palette(get_theme(self.config.theme))
        self.dictionary = Dictionary.load(self.config.language)
        self.sound = SoundPlayer(self.config.sound)
        self.prompt = CommandPrompt(registry)

        self.terminal = Terminal()
        self.screen = Screen(80, 24)
        self.running = True

        self._view: View = MenuView(self)
        self._stack: list[View] = []
        self._entered = False
        self._message = ""
        self._message_level = "info"
        self._message_until = 0.0

    # --------------------------------------------------------------- arranque

    def run(self) -> int:
        with self.terminal:
            reader = InputReader(self.terminal.fd)
            self._sync_screen()
            if not self._entered:
                self._enter(self._view)
            try:
                self._loop(reader)
            except KeyboardInterrupt:
                pass
            finally:
                self.sound.close()
        return 0

    def _loop(self, reader: InputReader) -> None:
        while self.running:
            interval = self._view.frame_interval()
            timeout = IDLE_TIMEOUT if interval is None else min(interval, IDLE_TIMEOUT)

            for key in reader.read_keys(timeout):
                self._handle_key(key)
                if not self.running:
                    return

            if self.terminal.take_resize():
                self._sync_screen()

            now = time.monotonic()
            self._view.tick(now)
            self._draw()

    def _sync_screen(self) -> None:
        size = self.terminal.size()
        self.screen.resize(size.columns, size.rows)
        self.screen.invalidate()

    # ----------------------------------------------------------------- teclas

    def _handle_key(self, key: Key) -> None:
        if key.name == "ctrl-c":
            self.quit()
            return

        if self.prompt.active:
            line = self.prompt.on_key(key)
            if line is not None:
                self._run_command(line)
            return

        if key.name == "char" and key.char == "/" and self._prompt_allowed():
            self.prompt.open("/")
            return

        if key.name == "ctrl-l":
            self.screen.invalidate()
            return

        if key.name == "char" and key.char == "?" and not isinstance(self._view, TestView):
            self.show_help()
            return

        self._view.on_key(key)

    def _prompt_allowed(self) -> bool:
        """Durante un test en marcha, ``/`` es un carácter más, no un atajo."""
        view = self._view
        if isinstance(view, TestView):
            return view.test.phase is not Phase.RUNNING
        return True

    def _run_command(self, line: str) -> None:
        result = registry.dispatch(line, self)
        self.apply_command_result(result)

    def apply_command_result(self, result: CommandResult) -> None:
        if result.config_changed:
            self.apply_config()
        if result.message:
            self.notify(result.message, level=result.level)

        action = result.action
        if action == command_module.ACTION_QUIT:
            self.quit()
        elif action == command_module.ACTION_RESTART:
            self.start_test()
        elif action == command_module.ACTION_MENU:
            self.show_menu()
        elif action == command_module.ACTION_HELP:
            self.show_help()
        elif action == command_module.ACTION_STATS:
            self.show_stats()
        elif action == command_module.ACTION_SETTINGS:
            self.show_settings()
        elif action == command_module.ACTION_HISTORY:
            self.show_history()

    # ------------------------------------------------------------- navegación

    def _enter(self, view: View) -> None:
        self._view = view
        self._entered = True
        self.screen.invalidate()
        view.on_enter()

    def set_view(self, view: View, *, keep_history: bool = False) -> None:
        if not keep_history:
            self._stack.clear()
        self._view.on_exit()
        self._enter(view)

    def push_view(self, view: View) -> None:
        """Abre una pantalla encima, recordando a dónde volver."""
        self._stack.append(self._view)
        self._view.on_exit()
        self._enter(view)

    def go_back(self) -> None:
        if self._stack:
            previous = self._stack.pop()
            self._view.on_exit()
            self._enter(previous)
        else:
            self.show_menu()

    def show_menu(self) -> None:
        self.set_view(MenuView(self))

    def show_help(self) -> None:
        self.push_view(HelpView(self))

    def show_settings(self) -> None:
        self.push_view(SettingsView(self))

    def show_history(self) -> None:
        self.push_view(HistoryView(self))

    def show_stats(self) -> None:
        self.push_view(StatsView(self))

    def quit(self) -> None:
        self.running = False

    # ------------------------------------------------------------------ tests

    def new_selector(self) -> WordSelector:
        return WordSelector(self.dictionary, self.config.difficulty)

    def start_test(self) -> None:
        config = self.config
        test = TypingTest(
            self.new_selector(),
            mode=config.mode,
            time_seconds=config.time_seconds,
            word_count=config.word_count,
            language=config.language,
            difficulty=config.difficulty,
            stop_on_error=config.stop_on_error,
        )
        self.set_view(TestView(self, test))

    def finish_test(self, test: TypingTest) -> None:
        result = test.result()
        records = self.history.add(result)
        self.history.save()
        self.session.append(result)
        self.sound.play("record" if records.any else "finish")
        self.set_view(ResultsView(self, result, records))

    # ------------------------------------------------------------ config y avisos

    def apply_config(self) -> None:
        """Propaga los cambios de configuración a los objetos que dependen de ella."""
        self.config.validate()
        self.palette = Palette(get_theme(self.config.theme))
        if self.dictionary.code != self.config.language:
            try:
                self.dictionary = Dictionary.load(self.config.language)
            except Exception as exc:  # diccionario ilegible: se avisa y se sigue
                self.notify(f"No se pudo cargar el idioma: {exc}", level="error")
                self.config.language = self.dictionary.code
        self.sound.enabled = self.config.sound
        self.screen.invalidate()

    def save_config(self) -> None:
        self.apply_config()
        if not self.config.save():
            self.notify("No se pudo guardar la configuración", level="error")

    def notify(self, message: str, level: str = "info") -> None:
        self._message = message
        self._message_level = level
        self._message_until = time.monotonic() + MESSAGE_SECONDS

    # ----------------------------------------------------------------- dibujo

    def _draw(self) -> None:
        screen = self.screen
        screen.clear()

        if screen.width < MIN_WIDTH or screen.height < MIN_HEIGHT:
            self._draw_too_small(screen)
        else:
            self._view.draw(screen)
            self._draw_chrome(screen)

        screen.flush(self.terminal.write)
        self.terminal.flush()

    def _draw_too_small(self, screen: Screen) -> None:
        palette = self.palette
        middle = screen.height // 2
        screen.put_center(middle - 1, "ventana demasiado pequeña", palette.style("incorrect", bold=True))
        screen.put_center(
            middle + 1,
            f"necesito {MIN_WIDTH}x{MIN_HEIGHT} · ahora {screen.width}x{screen.height}",
            palette.style("muted"),
        )
        screen.put_center(middle + 2, "agranda la terminal para continuar", palette.style("border"))

    def _draw_chrome(self, screen: Screen) -> None:
        """Barra de atajos, avisos y línea de comandos."""
        hints_row = screen.height - 1
        message_row = screen.height - 2
        prompt_row = screen.height - 3

        if self._view.hints:
            draw_hints(screen, hints_row, self.palette, list(self._view.hints))

        if self.prompt.active:
            self.prompt.draw(screen, prompt_row, self.palette)
            return

        if self._message and time.monotonic() < self._message_until:
            role = {"error": "incorrect", "success": "success"}.get(self._message_level, "muted")
            screen.put_center(message_row, self._message, self.palette.style(role))
        elif self._message:
            self._message = ""
