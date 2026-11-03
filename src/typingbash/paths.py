"""Localización de los ficheros de datos y de usuario."""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "typingbash"


def data_dir() -> Path:
    """Directorio con los diccionarios.

    Se buscan varias ubicaciones para que funcione igual ejecutando desde el
    repositorio clonado que desde una instalación con ``pip install -e``.
    """
    env = os.environ.get("TYPINGBASH_DATA")
    if env:
        return Path(env).expanduser()

    package = Path(__file__).resolve().parent
    candidates = (
        package / "data",  # datos empaquetados dentro del paquete
        package.parent.parent / "data",  # repositorio: src/typingbash -> raíz
        Path.cwd() / "data",
    )
    for candidate in candidates:
        if (candidate / "languages.json").exists():
            return candidate
    return candidates[1]


def user_dir() -> Path:
    """Directorio de configuración e historial del usuario.

    Se puede redirigir con ``TYPINGBASH_HOME``, algo que aprovechan los tests
    para no tocar los ficheros reales.
    """
    env = os.environ.get("TYPINGBASH_HOME")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / APP_DIR_NAME


def config_file() -> Path:
    return user_dir() / "config.json"


def history_file() -> Path:
    return user_dir() / "history.json"


def ensure_user_dir() -> Path:
    directory = user_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory
