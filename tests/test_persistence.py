"""Tests de configuración e historial: validación y persistencia en disco."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from typingbash import paths
from typingbash.config import Config, ConfigError
from typingbash.history import History
from typingbash.stats import CharCounts, TestResult, WordCounts


class TempHomeCase(unittest.TestCase):
    """Redirige el directorio de usuario a uno temporal."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("TYPINGBASH_HOME")
        os.environ["TYPINGBASH_HOME"] = self._directory.name
        self.home = Path(self._directory.name)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("TYPINGBASH_HOME", None)
        else:
            os.environ["TYPINGBASH_HOME"] = self._previous
        self._directory.cleanup()


def make_result(**kwargs) -> TestResult:
    defaults = dict(
        wpm=60.0, raw_wpm=65.0, accuracy=95.0, consistency=80.0, score=1000,
        duration=30.0, chars=CharCounts(150, 5, 0, 1), words=WordCounts(30, 1),
        mode="time", mode_value=30, language="es", difficulty="normal",
    )
    defaults.update(kwargs)
    return TestResult(**defaults)


class TestConfigValidacion(unittest.TestCase):
    def test_valores_por_defecto_razonables(self):
        config = Config()
        self.assertEqual(config.language, "es")
        self.assertEqual(config.mode, "time")
        self.assertEqual(config.time_seconds, 30)
        self.assertEqual(config.difficulty, "normal")
        self.assertTrue(config.animations)
        self.assertFalse(config.sound)  # el sonido molesta: apagado de serie

    def test_corrige_valores_imposibles(self):
        config = Config(mode="teletransporte", difficulty="épica",
                        time_seconds=99999, word_count=-4, theme="inexistente")
        config.validate()
        self.assertEqual(config.mode, "time")
        self.assertEqual(config.difficulty, "normal")
        self.assertEqual(config.time_seconds, 600)
        self.assertEqual(config.word_count, 5)
        self.assertEqual(config.theme, "minimal")

    def test_set_value_valida(self):
        config = Config()
        self.assertEqual(config.set_value("time_seconds", "45"), 45)
        with self.assertRaises(ConfigError):
            config.set_value("time_seconds", "abc")
        with self.assertRaises(ConfigError):
            config.set_value("difficulty", "extrema")
        with self.assertRaises(ConfigError):
            config.set_value("ajuste_que_no_existe", 1)

    def test_los_booleanos_aceptan_varias_formas(self):
        config = Config()
        for verdadero in ("on", "true", "1", "sí", "yes"):
            config.set_value("sound", verdadero)
            self.assertTrue(config.sound, verdadero)
        for falso in ("off", "false", "0", "no"):
            config.set_value("sound", falso)
            self.assertFalse(config.sound, falso)

    def test_descripcion_del_modo(self):
        self.assertEqual(Config(mode="time", time_seconds=15).describe_mode(), "15s")
        self.assertEqual(Config(mode="words", word_count=50).describe_mode(), "50 palabras")


class TestConfigPersistencia(TempHomeCase):
    def test_guarda_y_recupera(self):
        config = Config(time_seconds=120, difficulty="hard", theme="nord", sound=True)
        self.assertTrue(config.save())

        recuperada = Config.load()
        self.assertEqual(recuperada.time_seconds, 120)
        self.assertEqual(recuperada.difficulty, "hard")
        self.assertEqual(recuperada.theme, "nord")
        self.assertTrue(recuperada.sound)

    def test_sin_fichero_usa_los_valores_por_defecto(self):
        self.assertEqual(Config.load().time_seconds, 30)

    def test_fichero_corrupto_no_rompe_el_arranque(self):
        paths.ensure_user_dir()
        paths.config_file().write_text("{esto no es json", encoding="utf-8")
        self.assertEqual(Config.load().time_seconds, 30)

    def test_fichero_con_basura_se_sanea(self):
        paths.ensure_user_dir()
        paths.config_file().write_text(
            json.dumps({"time_seconds": 9999, "mode": "???", "sobra": True}),
            encoding="utf-8",
        )
        config = Config.load()
        self.assertEqual(config.time_seconds, 600)
        self.assertEqual(config.mode, "time")

    def test_el_json_es_legible_a_mano(self):
        Config().save()
        data = json.loads(paths.config_file().read_text(encoding="utf-8"))
        self.assertIn("difficulty", data)


class TestHistorial(TempHomeCase):
    def test_guarda_y_recupera_resultados(self):
        history = History()
        history.add(make_result(wpm=70.0))
        history.add(make_result(wpm=80.0))
        self.assertTrue(history.save())

        recuperado = History.load()
        self.assertEqual(len(recuperado), 2)
        self.assertAlmostEqual(recuperado.entries[-1].wpm, 80.0)
        self.assertEqual(recuperado.entries[0].chars.correct, 150)

    def test_historial_vacio_al_principio(self):
        self.assertEqual(len(History.load()), 0)

    def test_historial_corrupto_no_rompe(self):
        paths.ensure_user_dir()
        paths.history_file().write_text("no soy json", encoding="utf-8")
        self.assertEqual(len(History.load()), 0)

    def test_una_entrada_rota_no_tira_el_resto(self):
        paths.ensure_user_dir()
        bueno = make_result().to_dict()
        paths.history_file().write_text(
            json.dumps({"version": 1, "results": [bueno, {"roto": True}, bueno]}),
            encoding="utf-8",
        )
        self.assertEqual(len(History.load()), 2)

    def test_se_limita_el_numero_de_entradas(self):
        from typingbash.history import MAX_ENTRIES

        history = History()
        for i in range(MAX_ENTRIES + 25):
            history.add(make_result(wpm=float(i)))
        self.assertEqual(len(history), MAX_ENTRIES)
        self.assertAlmostEqual(history.entries[-1].wpm, float(MAX_ENTRIES + 24))


class TestRecords(TempHomeCase):
    def test_el_primer_test_no_es_record(self):
        history = History()
        records = history.add(make_result(wpm=70.0))
        self.assertFalse(records.any)

    def test_detecta_record_de_velocidad(self):
        history = History()
        history.add(make_result(wpm=70.0))
        records = history.add(make_result(wpm=85.0, accuracy=90.0, score=900))
        self.assertTrue(records.wpm)
        self.assertAlmostEqual(records.previous_wpm, 70.0)

    def test_no_es_record_si_no_mejora(self):
        history = History()
        history.add(make_result(wpm=90.0, accuracy=99.0, score=5000))
        records = history.add(make_result(wpm=70.0, accuracy=90.0, score=100))
        self.assertFalse(records.any)

    def test_los_records_son_por_modalidad(self):
        history = History()
        history.add(make_result(wpm=90.0, mode="time", mode_value=30))
        # Un test de 60 s no compite contra los de 30 s.
        records = history.add(make_result(wpm=75.0, mode="time", mode_value=60))
        self.assertFalse(records.wpm)

        history.add(make_result(wpm=60.0, mode="time", mode_value=60))
        mejora = history.add(make_result(wpm=80.0, mode="time", mode_value=60))
        self.assertTrue(mejora.wpm)

    def test_record_de_precision_y_puntuacion(self):
        history = History()
        history.add(make_result(accuracy=90.0, score=500))
        records = history.add(make_result(wpm=10.0, accuracy=99.0, score=600))
        self.assertTrue(records.accuracy)
        self.assertTrue(records.score)
        self.assertFalse(records.wpm)

    def test_consultas_agregadas(self):
        history = History()
        for wpm in (60.0, 70.0, 80.0):
            history.add(make_result(wpm=wpm))
        self.assertAlmostEqual(history.best_wpm().wpm, 80.0)
        self.assertAlmostEqual(history.average_wpm(10), 70.0)
        self.assertEqual(len(history.today()), 3)
        self.assertAlmostEqual(history.best_today().wpm, 80.0)

    def test_recientes_van_del_mas_nuevo_al_mas_viejo(self):
        history = History()
        for wpm in (10.0, 20.0, 30.0):
            history.add(make_result(wpm=wpm))
        self.assertAlmostEqual(history.recent(2)[0].wpm, 30.0)


if __name__ == "__main__":
    unittest.main()
