"""Tests del sistema de comandos y su validación."""

from __future__ import annotations

import unittest

from typingbash import commands as cmd
from typingbash.commands import registry
from typingbash.config import Config


class FakeContext:
    """Contexto mínimo: lo único que los comandos necesitan."""

    def __init__(self) -> None:
        self.config = Config()
        self.saves = 0

    def save_config(self) -> None:
        self.saves += 1


class TestDespacho(unittest.TestCase):
    def setUp(self):
        self.context = FakeContext()

    def run_command(self, line: str):
        return registry.dispatch(line, self.context)

    def test_funciona_con_y_sin_barra(self):
        self.assertEqual(self.run_command("/time 45").level, "success")
        self.assertEqual(self.run_command("time 20").level, "success")

    def test_comando_desconocido_es_amable(self):
        result = self.run_command("/banana")
        self.assertEqual(result.level, "error")
        self.assertIn("desconocido", result.message.lower())
        self.assertIn("/help", result.message)

    def test_sugiere_el_comando_parecido(self):
        result = self.run_command("/tim")
        self.assertIn("/time", result.message)

    def test_linea_vacia_no_hace_nada(self):
        result = self.run_command("   ")
        self.assertEqual(result.message, "")
        self.assertIsNone(result.action)

    def test_los_alias_funcionan(self):
        self.assertEqual(self.run_command("/q").action, cmd.ACTION_QUIT)
        self.assertEqual(self.run_command("/r").action, cmd.ACTION_RESTART)
        self.assertEqual(self.run_command("/?").action, cmd.ACTION_HELP)


class TestComandoTime(unittest.TestCase):
    def setUp(self):
        self.context = FakeContext()

    def test_cambia_a_modo_tiempo(self):
        self.context.config.mode = "words"
        result = registry.dispatch("/time 60", self.context)
        self.assertEqual(self.context.config.mode, "time")
        self.assertEqual(self.context.config.time_seconds, 60)
        self.assertEqual(result.action, cmd.ACTION_RESTART)
        self.assertEqual(self.context.saves, 1)

    def test_rechaza_texto(self):
        result = registry.dispatch("/time abc", self.context)
        self.assertEqual(result.level, "error")
        self.assertIn("/time <segundos>", result.message)
        self.assertEqual(self.context.config.time_seconds, 30)  # sin cambios

    def test_rechaza_negativos_y_cero(self):
        for valor in ("-30", "0", "-1"):
            result = registry.dispatch(f"/time {valor}", self.context)
            self.assertEqual(result.level, "error", valor)

    def test_rechaza_valores_desmesurados(self):
        self.assertEqual(registry.dispatch("/time 99999", self.context).level, "error")

    def test_sin_argumento_informa(self):
        result = registry.dispatch("/time", self.context)
        self.assertEqual(result.level, "info")
        self.assertIn("30s", result.message)


class TestComandoWords(unittest.TestCase):
    def setUp(self):
        self.context = FakeContext()

    def test_cambia_a_modo_palabras(self):
        result = registry.dispatch("/words 50", self.context)
        self.assertEqual(self.context.config.mode, "words")
        self.assertEqual(self.context.config.word_count, 50)
        self.assertEqual(result.action, cmd.ACTION_RESTART)

    def test_rechaza_negativos(self):
        result = registry.dispatch("/words -50", self.context)
        self.assertEqual(result.level, "error")
        self.assertIn("/words <cantidad>", result.message)
        self.assertEqual(self.context.config.word_count, 25)

    def test_rechaza_texto(self):
        self.assertEqual(registry.dispatch("/words muchas", self.context).level, "error")


class TestOtrosAjustes(unittest.TestCase):
    def setUp(self):
        self.context = FakeContext()

    def test_dificultad(self):
        result = registry.dispatch("/difficulty hard", self.context)
        self.assertEqual(self.context.config.difficulty, "hard")
        self.assertEqual(result.action, cmd.ACTION_RESTART)

    def test_dificultad_invalida(self):
        result = registry.dispatch("/difficulty imposible", self.context)
        self.assertEqual(result.level, "error")
        self.assertIn("easy", result.message)
        self.assertEqual(self.context.config.difficulty, "normal")

    def test_idioma(self):
        registry.dispatch("/language en", self.context)
        self.assertEqual(self.context.config.language, "en")

    def test_idioma_inexistente(self):
        result = registry.dispatch("/language marciano", self.context)
        self.assertEqual(result.level, "error")
        self.assertEqual(self.context.config.language, "es")

    def test_tema(self):
        registry.dispatch("/theme nord", self.context)
        self.assertEqual(self.context.config.theme, "nord")

    def test_set_generico(self):
        registry.dispatch("/set animations off", self.context)
        self.assertFalse(self.context.config.animations)
        registry.dispatch("/set animations on", self.context)
        self.assertTrue(self.context.config.animations)

    def test_set_con_ajuste_inexistente(self):
        result = registry.dispatch("/set volumen 10", self.context)
        self.assertEqual(result.level, "error")

    def test_set_sin_valor(self):
        self.assertEqual(registry.dispatch("/set animations", self.context).level, "error")


class TestAcciones(unittest.TestCase):
    def setUp(self):
        self.context = FakeContext()

    def test_acciones_de_navegacion(self):
        casos = {
            "/help": cmd.ACTION_HELP,
            "/settings": cmd.ACTION_SETTINGS,
            "/stats": cmd.ACTION_STATS,
            "/history": cmd.ACTION_HISTORY,
            "/restart": cmd.ACTION_RESTART,
            "/menu": cmd.ACTION_MENU,
            "/quit": cmd.ACTION_QUIT,
        }
        for line, action in casos.items():
            self.assertEqual(registry.dispatch(line, self.context).action, action, line)


class TestRegistro(unittest.TestCase):
    def test_todos_los_comandos_estan_documentados(self):
        for command in registry.all():
            self.assertTrue(command.usage.startswith("/"), command.name)
            self.assertTrue(command.summary, command.name)

    def test_existen_los_comandos_pedidos(self):
        for name in ("help", "time", "words", "language", "difficulty",
                     "restart", "settings", "stats", "quit"):
            self.assertIsNotNone(registry.resolve(name), name)

    def test_autocompletado(self):
        self.assertIn("time", registry.suggestions("ti"))
        self.assertIn("stats", registry.suggestions("s"))
        self.assertEqual(registry.suggestions("zzz"), [])

    def test_los_alias_resuelven_al_mismo_comando(self):
        self.assertIs(registry.resolve("q"), registry.resolve("quit"))

    def test_un_handler_que_falla_no_rompe_el_juego(self):
        from typingbash.commands import Command, CommandRegistry

        local = CommandRegistry()
        local.register(
            Command("boom", "/boom", "explota", lambda ctx, args: 1 / 0)
        )
        result = local.dispatch("/boom", FakeContext())
        self.assertEqual(result.level, "error")
        self.assertIn("falló", result.message)


if __name__ == "__main__":
    unittest.main()
