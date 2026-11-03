"""Tests de la lógica del test de mecanografía."""

from __future__ import annotations

import unittest

from helpers import FakeClock, StubSelector, type_text
from typingbash.engine import Phase, TypingTest


def make_test(words, **kwargs) -> tuple[TypingTest, FakeClock]:
    clock = FakeClock()
    defaults = dict(mode="words", word_count=len(words), clock=clock)
    defaults.update(kwargs)
    return TypingTest(StubSelector(words), **defaults), clock


class TestArranque(unittest.TestCase):
    def test_empieza_en_ready(self):
        test, _ = make_test(["casa", "coche"])
        self.assertIs(test.phase, Phase.READY)
        self.assertEqual(test.elapsed, 0.0)

    def test_el_cronometro_arranca_al_escribir(self):
        test, clock = make_test(["casa", "coche"], mode="time", time_seconds=30)
        clock.advance(5)  # tiempo mirando la pantalla: no cuenta
        self.assertEqual(test.elapsed, 0.0)

        test.type_char("c")
        self.assertIs(test.phase, Phase.RUNNING)
        clock.advance(2)
        self.assertAlmostEqual(test.elapsed, 2.0)

    def test_el_espacio_suelto_no_arranca_nada(self):
        test, _ = make_test(["casa"], mode="time", time_seconds=30)
        test.type_char(" ")
        self.assertIs(test.phase, Phase.READY)
        self.assertEqual(test.index, 0)


class TestComparacionDeCaracteres(unittest.TestCase):
    def test_acierto_y_fallo(self):
        test, _ = make_test(["coche"])
        type_text(test, "co")
        self.assertFalse(test.has_error_in_buffer)
        test.type_char("h")  # debería ser 'c'
        self.assertTrue(test.has_error_in_buffer)

    def test_la_ene_con_virgulilla_no_vale_por_ene(self):
        test, _ = make_test(["año"])
        type_text(test, "an")
        self.assertTrue(test.has_error_in_buffer)

        otro, _ = make_test(["año"])
        type_text(otro, "añ")
        self.assertFalse(otro.has_error_in_buffer)

    def test_las_vocales_acentuadas_son_distintas(self):
        test, _ = make_test(["rápido"])
        type_text(test, "ra")
        self.assertTrue(test.has_error_in_buffer)

        otro, _ = make_test(["rápido"])
        type_text(otro, "rá")
        self.assertFalse(otro.has_error_in_buffer)

    def test_palabra_con_acento_completa(self):
        test, _ = make_test(["mañana", "camión"])
        type_text(test, "mañana camión")
        test.finish()
        result = test.result()
        self.assertEqual(result.words.correct, 2)
        self.assertEqual(result.chars.incorrect, 0)

    def test_composicion_de_tecla_muerta(self):
        # Terminal que entrega el acento aparte: 'a' + U+0301 -> 'á'.
        test, _ = make_test(["rápido"])
        test.type_char("r")
        test.type_char("a")
        self.assertTrue(test.has_error_in_buffer)
        test.compose_last("́")
        self.assertEqual(test.buffer, "rá")
        self.assertFalse(test.has_error_in_buffer)


class TestEspacioYPalabras(unittest.TestCase):
    def test_el_espacio_avanza_de_palabra(self):
        test, _ = make_test(["casa", "coche"])
        type_text(test, "casa ")
        self.assertEqual(test.index, 1)
        self.assertEqual(test.buffer, "")
        self.assertEqual(test.target, "coche")

    def test_palabra_incorrecta_queda_registrada(self):
        test, _ = make_test(["casa", "coche"])
        type_text(test, "cosa coche")
        test.finish()
        result = test.result()
        self.assertEqual(result.words.correct, 1)
        self.assertEqual(result.words.incorrect, 1)

    def test_palabra_corta_cuenta_omitidos(self):
        test, _ = make_test(["ventana", "sol"])
        type_text(test, "vent sol")
        test.finish()
        chars = test.result().chars
        self.assertEqual(chars.missed, 3)  # a-n-a sin escribir

    def test_caracteres_de_mas_cuentan_como_extra(self):
        test, _ = make_test(["sol", "mar"])
        type_text(test, "solll mar")
        test.finish()
        self.assertEqual(test.result().chars.extra, 2)

    def test_hay_tope_de_caracteres_extra(self):
        test, _ = make_test(["sol"], mode="time", time_seconds=30)
        type_text(test, "sol" + "x" * 50)
        self.assertLessEqual(len(test.buffer), 3 + 10)


class TestRetroceso(unittest.TestCase):
    def test_borra_un_caracter(self):
        test, _ = make_test(["casa"])
        type_text(test, "cas")
        test.backspace()
        self.assertEqual(test.buffer, "ca")

    def test_borra_la_palabra_entera(self):
        test, _ = make_test(["casa"])
        type_text(test, "cas")
        test.backspace(whole_word=True)
        self.assertEqual(test.buffer, "")

    def test_vuelve_a_una_palabra_mal_escrita(self):
        test, _ = make_test(["casa", "coche"])
        type_text(test, "cosa ")
        self.assertEqual(test.index, 1)
        test.backspace()
        self.assertEqual(test.index, 0)
        self.assertEqual(test.buffer, "cosa")

    def test_no_vuelve_a_una_palabra_perfecta(self):
        test, _ = make_test(["casa", "coche"])
        type_text(test, "casa ")
        test.backspace()
        self.assertEqual(test.index, 1)
        self.assertEqual(test.buffer, "")

    def test_al_volver_atras_se_deshace_el_conteo(self):
        test, _ = make_test(["casa", "coche"])
        type_text(test, "cosa ")
        test.backspace()  # vuelve a la palabra anterior, con lo que se escribió
        self.assertEqual(test.buffer, "cosa")
        test.backspace(whole_word=True)  # la borra para reescribirla
        type_text(test, "casa coche")
        test.finish()
        result = test.result()
        self.assertEqual(result.words.correct, 2)
        self.assertEqual(result.words.incorrect, 0)
        self.assertEqual(result.chars.incorrect, 0)

    def test_borrar_no_borra_el_error_de_la_precision(self):
        test, _ = make_test(["casa"])
        type_text(test, "co")  # la 'o' está mal
        test.backspace()
        type_text(test, "asa")
        test.finish()
        result = test.result()
        self.assertEqual(result.chars.incorrect, 0)  # el texto acabó perfecto
        self.assertLess(result.accuracy, 100.0)  # pero el fallo sigue contando


class TestFinalPorPalabras(unittest.TestCase):
    def test_termina_al_completar_la_ultima(self):
        test, _ = make_test(["uno", "dos", "tres"], word_count=3)
        type_text(test, "uno dos tres")
        self.assertTrue(test.is_finished)
        self.assertEqual(test.result().words.total, 3)

    def test_no_hace_falta_espacio_final(self):
        test, _ = make_test(["uno", "dos"], word_count=2)
        type_text(test, "uno dos")
        self.assertIs(test.phase, Phase.FINISHED)

    def test_el_espacio_tambien_cierra_el_test(self):
        test, _ = make_test(["uno", "dos"], word_count=2)
        type_text(test, "uno dsx ")
        self.assertIs(test.phase, Phase.FINISHED)

    def test_el_progreso_llega_a_uno(self):
        test, _ = make_test(["uno", "dos"], word_count=2)
        self.assertAlmostEqual(test.progress, 0.0)
        type_text(test, "uno ")
        self.assertAlmostEqual(test.progress, 0.5)
        type_text(test, "dos")
        self.assertAlmostEqual(test.progress, 1.0)

    def test_no_se_aceptan_teclas_despues_del_final(self):
        test, _ = make_test(["uno"], word_count=1)
        type_text(test, "uno")
        self.assertTrue(test.is_finished)
        type_text(test, "xxx")
        self.assertEqual(test.buffer, "")


class TestFinalPorTiempo(unittest.TestCase):
    def test_termina_al_agotarse_el_tiempo(self):
        test, clock = make_test(["casa", "coche"], mode="time", time_seconds=10)
        test.type_char("c")
        clock.advance(9.0)
        test.tick()
        self.assertFalse(test.is_finished)
        clock.advance(1.1)
        test.tick()
        self.assertTrue(test.is_finished)

    def test_la_duracion_registrada_es_exacta(self):
        test, clock = make_test(["casa"], mode="time", time_seconds=15)
        test.type_char("c")
        clock.advance(15.4)  # el fotograma llega tarde
        test.tick()
        self.assertAlmostEqual(test.result().duration, 15.0, places=5)

    def test_el_tiempo_restante_baja(self):
        test, clock = make_test(["casa"], mode="time", time_seconds=30)
        test.type_char("c")
        clock.advance(0.5)
        self.assertAlmostEqual(test.remaining_seconds, 29.5)

    def test_se_generan_mas_palabras_al_avanzar(self):
        from typingbash.engine import LOOKAHEAD, REFILL_THRESHOLD

        test, _ = make_test(["uno", "dos", "tres"], mode="time", time_seconds=60)
        inicial = len(test.words)
        self.assertEqual(inicial, LOOKAHEAD)
        # Se avanza justo hasta cruzar el umbral de recarga.
        for _ in range(LOOKAHEAD - REFILL_THRESHOLD + 1):
            type_text(test, test.target + " ")
        self.assertGreater(len(test.words), inicial)
        self.assertNotEqual(test.target, "")

    def test_siempre_hay_palabras_para_llenar_la_pantalla(self):
        """Ni al principio ni avanzando debe faltar texto por delante."""
        from typingbash.engine import REFILL_THRESHOLD

        test, _ = make_test(["uno", "dos", "tres"], mode="time", time_seconds=120)
        for _ in range(300):
            self.assertGreaterEqual(len(test.words) - test.index, REFILL_THRESHOLD)
            type_text(test, test.target + " ")

    def test_la_palabra_a_medias_cuenta_lo_escrito(self):
        test, clock = make_test(["ventana"], mode="time", time_seconds=5)
        type_text(test, "vent")
        clock.advance(5.0)
        test.tick()
        chars = test.result().chars
        self.assertEqual(chars.correct, 4)
        self.assertEqual(chars.missed, 0)  # cortado por tiempo, no es culpa suya


class TestModoEstricto(unittest.TestCase):
    def test_no_deja_avanzar_con_un_error(self):
        # Dos palabras para que completar la primera no cierre el test.
        test, _ = make_test(["casa", "coche"], stop_on_error=True)
        type_text(test, "cx")
        self.assertEqual(test.buffer, "cx")
        type_text(test, "sa")  # se ignoran mientras haya error
        self.assertEqual(test.buffer, "cx")
        test.backspace()
        type_text(test, "asa")
        self.assertEqual(test.buffer, "casa")

    def test_sin_modo_estricto_si_deja_avanzar(self):
        test, _ = make_test(["casa", "coche"], stop_on_error=False)
        type_text(test, "cxsa")
        self.assertEqual(test.buffer, "cxsa")


class TestResultadoGlobal(unittest.TestCase):
    def test_cuentas_de_una_partida_perfecta(self):
        test, clock = make_test(["casa", "coche", "mundo"], word_count=3)
        test.type_char("c")
        clock.advance(60.0)
        type_text(test, "asa coche mundo")
        result = test.result()

        # 14 letras + 2 separadores correctos = 16 caracteres correctos.
        self.assertEqual(result.chars.correct, 16)
        self.assertEqual(result.chars.incorrect, 0)
        self.assertEqual(result.words.correct, 3)
        self.assertAlmostEqual(result.accuracy, 100.0)
        self.assertAlmostEqual(result.wpm, 16 / 5, places=4)
        self.assertGreaterEqual(result.raw_wpm, result.wpm)

    def test_metadatos_del_resultado(self):
        test, _ = make_test(["casa"], mode="words", word_count=1,
                            language="es", difficulty="hard")
        type_text(test, "casa")
        result = test.result()
        self.assertEqual(result.mode, "words")
        self.assertEqual(result.mode_value, 1)
        self.assertEqual(result.language, "es")
        self.assertEqual(result.difficulty, "hard")


if __name__ == "__main__":
    unittest.main()
