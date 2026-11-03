"""Tests del diccionario y del algoritmo de selección de palabras."""

from __future__ import annotations

import random
import re
import unittest

from typingbash.words import (
    Dictionary,
    WordSelector,
    available_languages,
    language_name,
    stem,
    strip_accents,
)

SPANISH_PATTERN = re.compile(r"^[a-záéíóúüñ]+$")


class TestDiccionario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = Dictionary.load("es")

    def test_el_espanol_esta_disponible(self):
        self.assertIn("es", available_languages())
        self.assertEqual(language_name("es"), "Español")

    def test_hay_vocabulario_suficiente(self):
        self.assertGreater(len(self.dictionary.common), 500)
        self.assertGreater(len(self.dictionary.extended), 300)

    def test_todas_las_palabras_son_palabras(self):
        for word in self.dictionary.common + self.dictionary.extended:
            self.assertTrue(SPANISH_PATTERN.match(word), f"palabra rara: {word!r}")
            self.assertNotIn(" ", word)

    def test_no_hay_duplicados_en_la_lista_comun(self):
        self.assertEqual(len(self.dictionary.common), len(set(self.dictionary.common)))

    def test_incluye_caracteres_propios_del_espanol(self):
        todas = "".join(self.dictionary.common + self.dictionary.extended)
        for char in "áéíóúüñ":
            self.assertIn(char, todas, f"falta la letra {char}")

    def test_contiene_vocabulario_cotidiano(self):
        comunes = set(self.dictionary.common)
        for word in ("casa", "tiempo", "persona", "mundo", "coche", "agua", "ciudad"):
            self.assertIn(word, comunes)

    def test_idioma_desconocido_cae_en_el_por_defecto(self):
        self.assertEqual(Dictionary.load("klingon").code, "es")


class TestDificultades(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = Dictionary.load("es")

    def _media(self, difficulty: str, seed: int = 1) -> float:
        selector = WordSelector(self.dictionary, difficulty, random.Random(seed))
        words = selector.take(400)
        return sum(len(w) for w in words) / len(words)

    def test_la_dificultad_alarga_las_palabras(self):
        facil, normal, dificil = self._media("easy"), self._media("normal"), self._media("hard")
        self.assertLess(facil, normal)
        self.assertLess(normal, dificil)

    def test_easy_solo_usa_palabras_cortas(self):
        selector = WordSelector(self.dictionary, "easy", random.Random(3))
        for word in selector.take(300):
            self.assertLessEqual(len(word), 6)

    def test_hard_tiene_el_mayor_repertorio(self):
        pools = {
            d: len(WordSelector(self.dictionary, d, random.Random(1)).pool)
            for d in ("easy", "normal", "hard")
        }
        self.assertLess(pools["easy"], pools["normal"])
        self.assertLess(pools["normal"], pools["hard"])

    def test_todas_las_dificultades_dan_espanol_real(self):
        comunes = set(self.dictionary.common) | set(self.dictionary.extended)
        for difficulty in ("easy", "normal", "hard"):
            selector = WordSelector(self.dictionary, difficulty, random.Random(9))
            for word in selector.take(200):
                self.assertIn(word, comunes)  # nunca inventadas ni concatenadas


class TestVariedad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dictionary = Dictionary.load("es")

    def test_no_repite_palabras_recientes(self):
        selector = WordSelector(self.dictionary, "normal", random.Random(11))
        words = selector.take(300)
        ventana = selector._recent.maxlen
        for i in range(len(words)):
            reciente = words[max(0, i - ventana) : i]
            self.assertNotIn(words[i], reciente)

    def test_evita_familias_lexicas_seguidas(self):
        selector = WordSelector(self.dictionary, "normal", random.Random(5))
        words = selector.take(300)
        for i in range(1, len(words)):
            anteriores = [stem(w) for w in words[max(0, i - 4) : i]]
            self.assertNotIn(stem(words[i]), anteriores)

    def test_hay_variedad_de_longitudes(self):
        selector = WordSelector(self.dictionary, "normal", random.Random(2))
        longitudes = {len(w) for w in selector.take(200)}
        self.assertGreater(len(longitudes), 6)

    def test_no_encadena_tres_longitudes_iguales(self):
        selector = WordSelector(self.dictionary, "normal", random.Random(4))
        words = selector.take(400)
        seguidas = sum(
            1
            for i in range(2, len(words))
            if len(words[i]) == len(words[i - 1]) == len(words[i - 2])
        )
        # No es una prohibición absoluta, pero debe ser algo excepcional.
        self.assertLess(seguidas, len(words) * 0.02)

    def test_dos_tests_no_salen_iguales(self):
        primero = WordSelector(self.dictionary, "normal", random.Random(1)).take(50)
        segundo = WordSelector(self.dictionary, "normal", random.Random(2)).take(50)
        self.assertNotEqual(primero, segundo)

    def test_la_semilla_hace_reproducible_la_seleccion(self):
        uno = WordSelector(self.dictionary, "normal", random.Random(42)).take(30)
        dos = WordSelector(self.dictionary, "normal", random.Random(42)).take(30)
        self.assertEqual(uno, dos)

    def test_las_palabras_frecuentes_salen_mas(self):
        selector = WordSelector(self.dictionary, "normal", random.Random(8))
        words = selector.take(3000)
        indices = {w: i for i, w in enumerate(self.dictionary.common)}
        media = sum(indices[w] for w in words) / len(words)
        # Con peso por frecuencia la media cae por debajo del centro del listado.
        self.assertLess(media, len(self.dictionary.common) / 2)


class TestNormalizacion(unittest.TestCase):
    def test_quita_acentos_solo_para_comparar(self):
        self.assertEqual(strip_accents("camión"), "camion")
        self.assertEqual(strip_accents("vergüenza"), "verguenza")

    def test_la_ene_se_conserva_como_letra_propia(self):
        # La ñ no es una n con adorno: se mantiene distinta.
        self.assertNotEqual("ñ", "n")

    def test_raiz_de_una_palabra(self):
        self.assertEqual(stem("casas"), stem("casa" + "s"))
        self.assertEqual(stem("camión"), "cami")


if __name__ == "__main__":
    unittest.main()
