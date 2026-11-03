"""Tests de maquetación: ninguna pantalla debe salirse de la terminal.

No se comprueba que sea bonito (eso no se puede automatizar), pero sí que
nada desborda por los lados ni invade las dos filas inferiores, que son de la
aplicación (avisos y barra de atajos).
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest

os.environ.setdefault("TYPINGBASH_HOME", tempfile.mkdtemp())

from typingbash.app import MIN_HEIGHT, MIN_WIDTH
from typingbash.config import UI_SIZES, Config
from typingbash.engine import TypingTest
from typingbash.history import History, Records
from typingbash.render import Screen
from typingbash.stats import CharCounts, TestResult, WordCounts
from typingbash.theme import Palette, get_theme
from typingbash.words import Dictionary, WordSelector
from typingbash.screens import (
    HelpView,
    HistoryView,
    MenuView,
    ResultsView,
    SettingsView,
    StatsView,
    TestView,
)

SIZES = ((MIN_WIDTH, MIN_HEIGHT), (70, 20), (80, 24), (100, 30), (140, 45), (220, 60))


def make_result(**kwargs) -> TestResult:
    defaults = dict(
        wpm=87.4, raw_wpm=91.2, accuracy=96.4, consistency=84.0, score=1841,
        duration=30.0, chars=CharCounts(234, 9, 2, 3), words=WordCounts(42, 1),
        mode="time", mode_value=30, language="es", difficulty="normal",
        wpm_series=[40.0, 60.0, 75.0, 88.0, 92.0, 85.0] * 5,
    )
    defaults.update(kwargs)
    return TestResult(**defaults)


class FakeApp:
    """Lo mínimo que las pantallas piden de la aplicación."""

    def __init__(self, with_history: bool = True) -> None:
        self.config = Config()
        self.session: list[TestResult] = []
        self.palette = Palette(get_theme("minimal"), truecolor=True)
        self.history = History()
        if with_history:
            for index in range(12):
                self.history.add(
                    make_result(wpm=60.0 + index, timestamp=time.time() - index * 600)
                )
            self.session.append(make_result())

    def save_config(self) -> None:
        pass

    def notify(self, message: str, level: str = "info") -> None:
        pass

    def apply_config(self) -> None:
        pass


class LayoutCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = Dictionary.load("es")

    def make_test(self, **kwargs) -> TypingTest:
        selector = WordSelector(self.dictionary, "normal")
        test = TypingTest(selector, **kwargs)
        return test

    def assert_fits(self, view, width: int, height: int) -> None:
        screen = Screen(width, height)
        screen.clear()
        view.draw(screen)
        rows = ["".join(cell[0] for cell in row).rstrip() for row in screen._back]
        where = f"{width}x{height} (tamaño {view.app.config.ui_size})"

        widest = max((len(row) for row in rows), default=0)
        self.assertLessEqual(
            widest, width, f"{type(view).__name__} desborda a lo ancho en {where}"
        )
        used = [index for index, row in enumerate(rows) if row]
        if used:
            self.assertLessEqual(
                used[-1], height - 3,
                f"{type(view).__name__} invade la barra inferior en {where}",
            )

    def each_size(self, app: FakeApp):
        """Recorre los tres tamaños de interfaz sobre la misma aplicación."""
        for size in UI_SIZES:
            app.config.ui_size = size
            yield size

    def views(self, app: FakeApp):
        test = self.make_test(mode="time", time_seconds=30)
        for char in "casa co":
            test.type_char(char)
        finished = self.make_test(mode="words", word_count=5)
        return [
            MenuView(app),
            HelpView(app),
            SettingsView(app),
            HistoryView(app),
            StatsView(app),
            TestView(app, test),
            TestView(app, finished),
            ResultsView(app, make_result(), Records()),
            ResultsView(app, make_result(), Records(wpm=True, previous_wpm=79.1)),
            ResultsView(app, make_result(wpm_series=[]), Records(accuracy=True)),
        ]


class TestTodasLasPantallasCaben(LayoutCase):
    def test_con_historial(self):
        app = FakeApp(with_history=True)
        for _size in self.each_size(app):
            for width, height in SIZES:
                for view in self.views(app):
                    self.assert_fits(view, width, height)

    def test_sin_historial(self):
        app = FakeApp(with_history=False)
        for _size in self.each_size(app):
            for width, height in SIZES:
                for view in self.views(app):
                    self.assert_fits(view, width, height)

    def test_anchos_intermedios(self):
        """Barrido fino: los redondeos no deben desbordar en ningún ancho."""
        app = FakeApp()
        for _size in self.each_size(app):
            for width in range(MIN_WIDTH, 201, 7):
                for view in self.views(app):
                    self.assert_fits(view, width, 24)

    def test_altos_intermedios(self):
        """Lo mismo en vertical: nadie debe pisar la barra inferior."""
        app = FakeApp()
        for _size in self.each_size(app):
            for height in range(MIN_HEIGHT, 61, 3):
                for view in self.views(app):
                    self.assert_fits(view, 120, height)


class TestPantallaDelTest(LayoutCase):
    def test_el_texto_no_desborda_con_palabras_muy_largas(self):
        app = FakeApp()
        test = self.make_test(mode="words", word_count=20)
        test.words = ["extraordinariamente"] * 20
        for char in "extraordinaria":
            test.type_char(char)
        for _size in self.each_size(app):
            for width, height in SIZES:
                self.assert_fits(TestView(app, test), width, height)

    def test_muchos_caracteres_sobrantes_no_desbordan(self):
        app = FakeApp()
        test = self.make_test(mode="time", time_seconds=30)
        for char in test.target + "x" * 30:
            test.type_char(char)
        for _size in self.each_size(app):
            for width, height in SIZES:
                self.assert_fits(TestView(app, test), width, height)

    def test_la_cuenta_atras_cabe(self):
        app = FakeApp()
        app.config.countdown = True
        app.config.animations = True
        test = self.make_test(mode="time", time_seconds=30)
        view = TestView(app, test)
        view.on_enter()
        for _size in self.each_size(app):
            for width, height in SIZES:
                self.assert_fits(view, width, height)


if __name__ == "__main__":
    unittest.main()
