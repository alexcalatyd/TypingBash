"""Tests del renderizador diferencial y de las piezas visuales."""

from __future__ import annotations

import unittest

from typingbash.render import Screen, truncate
from typingbash.theme import Palette, get_theme, theme_names
from typingbash.ui import progress_bar, sparkline


class Recorder:
    """Recoge lo que el renderizador querría escribir en el TTY."""

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def __call__(self, data: str) -> None:
        self.chunks.append(data)

    @property
    def output(self) -> str:
        return "".join(self.chunks)

    def reset(self) -> None:
        self.chunks.clear()


class TestScreen(unittest.TestCase):
    def setUp(self):
        self.screen = Screen(20, 5)
        self.out = Recorder()

    def text_at(self, y: int) -> str:
        return "".join(cell[0] for cell in self.screen._back[y])

    def test_escribe_texto(self):
        self.screen.put(2, 1, "hola")
        self.assertEqual(self.text_at(1).strip(), "hola")

    def test_recorta_en_el_borde_derecho(self):
        self.screen.put(18, 0, "desbordamiento")
        self.assertEqual(self.text_at(0)[18:], "de")

    def test_ignora_filas_fuera_de_pantalla(self):
        self.screen.put(0, 99, "invisible")  # no debe lanzar
        self.screen.put(0, -3, "invisible")

    def test_centrado(self):
        self.screen.put_center(0, "abc")
        self.assertEqual(self.text_at(0).strip(), "abc")
        self.assertTrue(self.text_at(0).startswith(" " * 8))

    def test_alineado_a_la_derecha(self):
        self.screen.put_right(0, 20, "fin")
        self.assertTrue(self.text_at(0).endswith("fin"))

    def test_limpiar(self):
        self.screen.put(0, 0, "algo")
        self.screen.clear()
        self.assertEqual(self.text_at(0).strip(), "")


class TestRepintadoDiferencial(unittest.TestCase):
    def setUp(self):
        self.screen = Screen(20, 4)
        self.out = Recorder()

    def test_el_primer_volcado_pinta_todo(self):
        self.screen.put(0, 0, "hola")
        self.screen.flush(self.out)
        self.assertIn("hola", self.out.output)
        self.assertIn("2J", self.out.output)  # borrado inicial

    def test_sin_cambios_no_escribe_nada(self):
        self.screen.put(0, 0, "hola")
        self.screen.flush(self.out)
        self.out.reset()
        self.screen.flush(self.out)
        self.assertEqual(self.out.output, "")

    def test_solo_se_envia_lo_que_cambia(self):
        self.screen.put(0, 0, "tiempo 30")
        self.screen.flush(self.out)
        self.out.reset()

        self.screen.put(0, 0, "tiempo 29")
        self.screen.flush(self.out)
        salida = self.out.output
        self.assertIn("9", salida)
        self.assertNotIn("tiempo", salida)  # el resto no se reenvía
        self.assertLess(len(salida), 40)

    def test_invalidar_fuerza_repintado_completo(self):
        self.screen.put(0, 0, "hola")
        self.screen.flush(self.out)
        self.out.reset()
        self.screen.invalidate()
        self.screen.flush(self.out)
        self.assertIn("hola", self.out.output)

    def test_redimensionar_ajusta_el_lienzo(self):
        self.screen.resize(40, 10)
        self.assertEqual(self.screen.width, 40)
        self.assertEqual(self.screen.height, 10)
        self.screen.put(35, 9, "ok")  # no debe lanzar
        self.screen.flush(self.out)

    def test_el_estilo_se_emite_con_el_texto(self):
        palette = Palette(get_theme("minimal"), truecolor=True)
        self.screen.put(0, 0, "x", palette.style("accent", bold=True))
        self.screen.flush(self.out)
        self.assertIn("\x1b[", self.out.output)
        self.assertIn("x", self.out.output)


class TestTruncate(unittest.TestCase):
    def test_no_toca_lo_que_cabe(self):
        self.assertEqual(truncate("hola", 10), "hola")

    def test_añade_puntos_suspensivos(self):
        self.assertEqual(truncate("mecanografía", 6), "mecan…")

    def test_ancho_minusculo(self):
        self.assertEqual(truncate("hola", 0), "")
        self.assertEqual(len(truncate("hola", 1)), 1)

    def test_el_resultado_nunca_excede_el_ancho(self):
        for width in range(0, 15):
            self.assertLessEqual(len(truncate("una cadena larga", width)), width)


class TestPalette(unittest.TestCase):
    def test_todos_los_temas_definen_todos_los_roles(self):
        roles = ("accent", "text", "pending", "incorrect", "extra",
                 "muted", "border", "success", "warning")
        for name in theme_names():
            palette = Palette(get_theme(name), truecolor=True)
            for role in roles:
                self.assertTrue(palette.style(role).startswith("\x1b["), (name, role))

    def test_tema_desconocido_cae_en_el_por_defecto(self):
        self.assertEqual(get_theme("no-existe").name, "minimal")

    def test_modo_256_colores(self):
        palette = Palette(get_theme("minimal"), truecolor=False)
        self.assertIn("38;5;", palette.style("accent"))

    def test_modo_color_verdadero(self):
        palette = Palette(get_theme("minimal"), truecolor=True)
        self.assertIn("38;2;", palette.style("accent"))

    def test_sin_atributos_no_emite_secuencia(self):
        self.assertEqual(Palette(get_theme("minimal")).style(), "")


class TestPiezasVisuales(unittest.TestCase):
    def test_barra_de_progreso(self):
        lleno, vacio = progress_bar(10, 0.5)
        self.assertEqual(len(lleno) + len(vacio), 10)
        self.assertEqual(len(lleno), 5)

    def test_barra_en_los_extremos(self):
        self.assertEqual(progress_bar(10, 0.0)[0], "")
        self.assertEqual(len(progress_bar(10, 1.0)[0]), 10)
        self.assertEqual(len(progress_bar(10, 5.0)[0]), 10)  # se satura, no desborda
        self.assertEqual(len(progress_bar(10, -2.0)[0]), 0)

    def test_sparkline_respeta_el_ancho(self):
        self.assertEqual(len(sparkline([1, 2, 3, 4, 5], 5)), 5)
        self.assertEqual(len(sparkline(list(range(100)), 20)), 20)

    def test_sparkline_refleja_la_forma(self):
        graph = sparkline([1, 50, 1], 3)
        self.assertGreater(graph[1], graph[0])

    def test_sparkline_con_casos_limite(self):
        self.assertEqual(sparkline([], 10), "")
        self.assertEqual(sparkline([0, 0, 0], 3), "▁▁▁")


if __name__ == "__main__":
    unittest.main()
