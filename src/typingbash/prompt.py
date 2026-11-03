"""Línea de comandos superpuesta, al estilo del paleta de Monkeytype.

Se abre con ``/`` desde cualquier pantalla, acepta edición básica, historial
con las flechas y autocompletado con el tabulador.
"""

from __future__ import annotations

from .commands import CommandRegistry
from .keys import Key
from .render import Screen
from .theme import Palette

MAX_HISTORY = 50


class CommandPrompt:
    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry
        self.active = False
        self.text = ""
        self.cursor = 0
        self.history: list[str] = []
        self._history_index: int | None = None
        self._draft = ""

    # ------------------------------------------------------------ ciclo de vida

    def open(self, initial: str = "/") -> None:
        self.active = True
        self.text = initial
        self.cursor = len(initial)
        self._history_index = None

    def close(self) -> None:
        self.active = False
        self.text = ""
        self.cursor = 0

    def submit(self) -> str:
        text = self.text
        if text.strip() not in ("", "/"):
            if not self.history or self.history[-1] != text:
                self.history.append(text)
                del self.history[:-MAX_HISTORY]
        self.close()
        return text

    # ---------------------------------------------------------------- edición

    def on_key(self, key: Key) -> str | None:
        """Devuelve la línea a ejecutar cuando el usuario pulsa Enter."""
        if key.name == "char":
            self.text = self.text[: self.cursor] + key.char + self.text[self.cursor :]
            self.cursor += 1
        elif key.name == "backspace":
            if self.cursor > 0:
                self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
                self.cursor -= 1
            if not self.text:
                self.close()
        elif key.name == "delete":
            self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]
        elif key.name in ("delete-word", "ctrl-w"):
            head = self.text[: self.cursor].rstrip()
            cut = head.rfind(" ") + 1
            self.text = self.text[:cut] + self.text[self.cursor :]
            self.cursor = cut
        elif key.name == "delete-line":
            self.text, self.cursor = "/", 1
        elif key.name == "left":
            self.cursor = max(0, self.cursor - 1)
        elif key.name == "right":
            self.cursor = min(len(self.text), self.cursor + 1)
        elif key.name == "home":
            self.cursor = 0
        elif key.name == "end":
            self.cursor = len(self.text)
        elif key.name == "tab":
            self._complete()
        elif key.name in ("up", "down"):
            self._navigate_history(-1 if key.name == "up" else 1)
        elif key.name == "escape":
            self.close()
        elif key.name == "enter":
            return self.submit()
        return None

    def _complete(self) -> None:
        stripped = self.text.lstrip("/")
        if " " in stripped:
            return  # solo completamos el nombre del comando
        matches = self.registry.suggestions(stripped)
        if not matches:
            return
        if len(matches) == 1:
            self.text = "/" + matches[0] + " "
        else:
            self.text = "/" + _common_prefix(matches)
        self.cursor = len(self.text)

    def _navigate_history(self, direction: int) -> None:
        if not self.history:
            return
        if self._history_index is None:
            if direction > 0:
                return
            self._draft = self.text
            self._history_index = len(self.history) - 1
        else:
            self._history_index += direction
            if self._history_index >= len(self.history):
                self._history_index = None
                self.text = self._draft
                self.cursor = len(self.text)
                return
            self._history_index = max(0, self._history_index)
        self.text = self.history[self._history_index]
        self.cursor = len(self.text)

    # ----------------------------------------------------------------- dibujo

    def draw(self, screen: Screen, y: int, palette: Palette) -> None:
        if not self.active:
            return
        margin = 2
        width = screen.width - margin * 2
        screen.fill(margin, y, width, " ")
        x = screen.put(margin, y, "› ", palette.style("accent", bold=True))

        text_style = palette.style("text")
        visible = self.text[: max(0, width - 4)]
        screen.put(x, y, visible, text_style)
        # Cursor propio: bloque invertido sobre el carácter actual.
        caret_x = x + min(self.cursor, len(visible))
        char = visible[self.cursor] if self.cursor < len(visible) else " "
        screen.put(caret_x, y, char, palette.style("accent", reverse=True))

        matches = self._suggestion_line()
        if matches:
            screen.put(margin, y + 1, matches, palette.style("muted"))

    def _suggestion_line(self) -> str:
        stripped = self.text.lstrip("/")
        if " " in stripped:
            command = self.registry.resolve(stripped.split()[0])
            return f"{command.usage} — {command.summary}" if command else ""
        matches = self.registry.suggestions(stripped)
        if not matches:
            return "sin coincidencias"
        if len(matches) == 1:
            command = self.registry.resolve(matches[0])
            return f"{command.usage} — {command.summary}" if command else ""
        return "  ".join("/" + name for name in matches[:8])


def _common_prefix(words: list[str]) -> str:
    if not words:
        return ""
    prefix = words[0]
    for word in words[1:]:
        while not word.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix
