"""Pantallas de la aplicación."""

from .base import View
from .help import HelpView
from .history import HistoryView
from .menu import MenuView
from .results import ResultsView
from .settings import SettingsView
from .stats import StatsView
from .test import TestView

__all__ = [
    "View",
    "HelpView",
    "HistoryView",
    "MenuView",
    "ResultsView",
    "SettingsView",
    "StatsView",
    "TestView",
]
