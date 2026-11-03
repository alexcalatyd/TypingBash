"""Tests de la decodificación de teclado en modo raw."""

from __future__ import annotations

import os
import unittest

from typingbash.keys import InputReader, compose


class ReaderCase(unittest.TestCase):
    def setUp(self):
        self.read_fd, self.write_fd = os.pipe()
        self.reader = InputReader(self.read_fd)
        self.addCleanup(self._close)

    def _close(self):
        for fd in (self.read_fd, self.write_fd):
            try:
                os.close(fd)
            except OSError:
                pass

    def send(self, data: bytes) -> None:
        os.write(self.write_fd, data)

    def keys(self, timeout: float = 0.2):
        return self.reader.read_keys(timeout)


class TestCaracteres(ReaderCase):
    def test_ascii(self):
        self.send(b"casa")
        keys = self.keys()
        self.assertEqual([k.char for k in keys], list("casa"))
        self.assertTrue(all(k.is_char for k in keys))

    def test_acentos_y_ene(self):
        self.send("año rápido".encode("utf-8"))
        texto = "".join(k.char for k in self.keys())
        self.assertEqual(texto, "año rápido")

    def test_multibyte_partido_entre_lecturas(self):
        # La 'ñ' son dos bytes: llegan en lecturas distintas.
        raw = "ñ".encode("utf-8")
        self.send(raw[:1])
        self.assertEqual(self.keys(0.05), [])  # aún incompleta, sin basura
        self.send(raw[1:])
        keys = self.keys()
        self.assertEqual([k.char for k in keys], ["ñ"])

    def test_rafaga_larga_no_pierde_teclas(self):
        texto = "el veloz murciélago comía kiwi" * 5
        self.send(texto.encode("utf-8"))
        recibido = ""
        for _ in range(10):
            recibido += "".join(k.char for k in self.keys(0.05) if k.is_char)
            if len(recibido) >= len(texto):
                break
        self.assertEqual(recibido, texto)

    def test_marca_combinante(self):
        self.send("́".encode("utf-8"))
        keys = self.keys()
        self.assertEqual(keys[0].name, "combining")


class TestTeclasEspeciales(ReaderCase):
    def test_control_basicas(self):
        casos = {
            b"\r": "enter",
            b"\n": "enter",
            b"\t": "tab",
            b"\x7f": "backspace",
            b"\x08": "backspace",
            b"\x03": "ctrl-c",
            b"\x04": "ctrl-d",
            b"\x17": "delete-word",
            b"\x15": "delete-line",
        }
        for raw, name in casos.items():
            self.send(raw)
            self.assertEqual(self.keys()[0].name, name, raw)

    def test_ctrl_generico(self):
        self.send(b"\x0c")  # ctrl+l
        self.assertEqual(self.keys()[0].name, "ctrl-l")

    def test_flechas(self):
        for raw, name in ((b"\x1b[A", "up"), (b"\x1b[B", "down"),
                          (b"\x1b[C", "right"), (b"\x1b[D", "left")):
            self.send(raw)
            self.assertEqual(self.keys()[0].name, name, raw)

    def test_secuencias_con_tilde(self):
        self.send(b"\x1b[3~")
        self.assertEqual(self.keys()[0].name, "delete")

    def test_escape_suelto(self):
        self.send(b"\x1b")
        keys = self.keys()
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0].name, "escape")

    def test_escape_seguido_de_texto_no_se_confunde(self):
        self.send(b"\x1b")
        self.assertEqual(self.keys()[0].name, "escape")
        self.send(b"a")
        self.assertEqual(self.keys()[0].char, "a")

    def test_alt_retroceso_borra_palabra(self):
        self.send(b"\x1b\x7f")
        self.assertEqual(self.keys()[0].name, "delete-word")

    def test_teclado_de_aplicacion(self):
        self.send(b"\x1bOA")
        self.assertEqual(self.keys()[0].name, "up")

    def test_secuencia_desconocida_no_rompe(self):
        self.send(b"\x1b[200~")
        self.assertEqual(self.keys()[0].name, "unknown")


class TestMezclas(ReaderCase):
    def test_texto_y_teclas_juntos(self):
        self.send("ca\x7fsa\r".encode("utf-8"))
        nombres = [k.name for k in self.keys()]
        self.assertEqual(nombres, ["char", "char", "backspace", "char", "char", "enter"])

    def test_sin_entrada_devuelve_lista_vacia(self):
        self.assertEqual(self.reader.read_keys(0.01), [])


class TestComposicion(unittest.TestCase):
    def test_une_vocal_y_acento(self):
        self.assertEqual(compose("a", "́"), "á")
        self.assertEqual(compose("n", "̃"), "ñ")
        self.assertEqual(compose("u", "̈"), "ü")

    def test_combinacion_imposible_devuelve_el_original(self):
        # No existe una 'q' con tilde precompuesta: se descarta la marca en
        # lugar de meter dos caracteres en el buffer.
        self.assertEqual(compose("q", "́"), "q")
        self.assertEqual(compose("b", "̈"), "b")


if __name__ == "__main__":
    unittest.main()
