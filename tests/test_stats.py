"""Tests de las fórmulas de estadísticas."""

from __future__ import annotations

import unittest

from typingbash.stats import (
    CharCounts,
    LiveStats,
    TestResult,
    WordCounts,
    accuracy,
    consistency,
    raw_wpm,
    score,
    wpm,
)


class TestWpm(unittest.TestCase):
    def test_wpm_usa_cinco_caracteres_por_palabra(self):
        # 250 caracteres en 60 s -> 250/5 = 50 palabras por minuto.
        self.assertAlmostEqual(wpm(250, 60), 50.0)

    def test_wpm_escala_con_la_duracion(self):
        # Los mismos caracteres en la mitad de tiempo doblan el resultado.
        self.assertAlmostEqual(wpm(125, 30), 50.0)
        self.assertAlmostEqual(wpm(125, 15), 100.0)

    def test_wpm_sin_tiempo_es_cero(self):
        self.assertEqual(wpm(100, 0), 0.0)
        self.assertEqual(wpm(100, -5), 0.0)

    def test_raw_incluye_los_errores(self):
        # 200 pulsaciones de texto en 60 s, aunque algunas fueran erróneas.
        self.assertAlmostEqual(raw_wpm(200, 60), 40.0)

    def test_raw_nunca_es_menor_que_el_wpm(self):
        correctos, total, segundos = 180, 220, 30
        self.assertGreaterEqual(raw_wpm(total, segundos), wpm(correctos, segundos))


class TestAccuracy(unittest.TestCase):
    def test_precision_basica(self):
        self.assertAlmostEqual(accuracy(95, 100), 95.0)

    def test_precision_perfecta(self):
        self.assertAlmostEqual(accuracy(50, 50), 100.0)

    def test_sin_pulsaciones_es_cien(self):
        self.assertAlmostEqual(accuracy(0, 0), 100.0)

    def test_todo_mal_es_cero(self):
        self.assertAlmostEqual(accuracy(0, 40), 0.0)


class TestConsistency(unittest.TestCase):
    def test_ritmo_constante_es_cien(self):
        self.assertAlmostEqual(consistency([60.0] * 10), 100.0)

    def test_ritmo_irregular_baja(self):
        irregular = consistency([10.0, 90.0, 20.0, 80.0, 15.0])
        self.assertLess(irregular, 70.0)
        self.assertGreaterEqual(irregular, 0.0)

    def test_mas_regular_puntua_mas(self):
        regular = consistency([50.0, 52.0, 48.0, 51.0])
        irregular = consistency([20.0, 80.0, 30.0, 70.0])
        self.assertGreater(regular, irregular)

    def test_pocas_muestras(self):
        self.assertEqual(consistency([]), 0.0)
        self.assertEqual(consistency([42.0]), 100.0)

    def test_siempre_dentro_de_rango(self):
        for muestras in ([1.0, 200.0], [0.0, 0.0, 5.0], [3.0] * 20):
            valor = consistency(muestras)
            self.assertGreaterEqual(valor, 0.0)
            self.assertLessEqual(valor, 100.0)


class TestScore(unittest.TestCase):
    def test_la_precision_pesa(self):
        limpio = score(300, 100.0, 60.0)
        sucio = score(300, 80.0, 60.0)
        self.assertGreater(limpio, sucio)

    def test_la_velocidad_pesa(self):
        self.assertGreater(score(300, 95.0, 80.0), score(300, 95.0, 40.0))

    def test_nunca_es_negativo(self):
        self.assertGreaterEqual(score(0, 0.0, 0.0), 0)


class TestCharCounts(unittest.TestCase):
    def test_totales(self):
        counts = CharCounts(correct=100, incorrect=5, extra=2, missed=3)
        self.assertEqual(counts.typed, 107)
        self.assertEqual(counts.total, 110)


class TestLiveStats(unittest.TestCase):
    def test_registro_de_pulsaciones(self):
        live = LiveStats()
        for _ in range(9):
            live.record_keystroke(True)
        live.record_keystroke(False)
        self.assertEqual(live.total_keystrokes, 10)
        self.assertEqual(live.correct_keystrokes, 9)
        self.assertEqual(live.error_keystrokes, 1)
        self.assertAlmostEqual(live.live_accuracy, 90.0)

    def test_muestreo_por_segundo(self):
        live = LiveStats()
        for _ in range(10):
            live.record_keystroke(True)
        live.sample(1.0)
        self.assertEqual(len(live.series), 1)
        # 10 caracteres en un segundo -> 10/5 * 60 = 120 wpm brutos.
        self.assertAlmostEqual(live.series[0], 120.0)

    def test_los_segundos_vacios_tambien_cuentan(self):
        live = LiveStats()
        live.sample(3.0)
        self.assertEqual(live.series, [0.0, 0.0, 0.0])


class TestResultSerialization(unittest.TestCase):
    def _result(self) -> TestResult:
        return TestResult(
            wpm=72.5, raw_wpm=78.0, accuracy=96.4, consistency=81.0, score=1200,
            duration=30.0, chars=CharCounts(200, 7, 1, 2), words=WordCounts(40, 2),
            mode="time", mode_value=30, language="es", difficulty="normal",
            wpm_series=[60.0, 70.0],
        )

    def test_ida_y_vuelta(self):
        original = self._result()
        copia = TestResult.from_dict(original.to_dict())
        self.assertAlmostEqual(copia.wpm, original.wpm)
        self.assertEqual(copia.chars.correct, 200)
        self.assertEqual(copia.words.incorrect, 2)
        self.assertEqual(copia.wpm_series, [60.0, 70.0])

    def test_tolera_campos_desconocidos(self):
        data = self._result().to_dict()
        data["campo_futuro"] = "ignorame"
        self.assertEqual(TestResult.from_dict(data).mode_value, 30)

    def test_descripcion_de_modo(self):
        self.assertEqual(self._result().describe_mode(), "30s")


if __name__ == "__main__":
    unittest.main()
