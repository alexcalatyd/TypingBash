"""Utilidades compartidas por los tests."""

from __future__ import annotations


class StubSelector:
    """Selector determinista: entrega las palabras dadas, en orden y en bucle."""

    def __init__(self, words: list[str]) -> None:
        self.words = list(words)
        self.position = 0

    def take(self, count: int) -> list[str]:
        result = []
        for _ in range(count):
            result.append(self.words[self.position % len(self.words)])
            self.position += 1
        return result


class FakeClock:
    """Reloj controlado a mano, para no depender del tiempo real."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def type_text(test, text: str) -> None:
    """Envía una cadena carácter a carácter, espacios incluidos."""
    for char in text:
        test.type_char(char)
