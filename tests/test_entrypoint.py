"""Smoke tests for the Hunt Pro entrypoint module."""

from __future__ import annotations

import builtins
import importlib.util
import io
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

import pytest


def load_entrypoint_module():
    """Load the project entrypoint module without running it as ``__main__``."""
    module_path = Path(__file__).resolve().parents[1] / "__main__.py"
    spec = importlib.util.spec_from_file_location("hunt_pro_entry", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def entry_module():
    return load_entrypoint_module()


def test_check_dependencies_reports_missing_required(entry_module, monkeypatch):
    """check_dependencies should fail gracefully when PySide6 is unavailable."""
    numpy_stub = types.ModuleType("numpy")
    numpy_stub.__version__ = "0.0"
    monkeypatch.setitem(sys.modules, "numpy", numpy_stub)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: D401
        if name.startswith("PySide6"):
            raise ImportError("No module named PySide6")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = entry_module.check_dependencies()

    output = buffer.getvalue()

    assert result is False
    assert "Missing required dependencies" in output
    assert "PySide6" in output


def test_check_dependencies_succeeds_with_stubbed_gui(entry_module, monkeypatch):
    """check_dependencies should pass when core requirements are satisfied."""
    numpy_stub = types.ModuleType("numpy")
    numpy_stub.__version__ = "1.0"
    monkeypatch.setitem(sys.modules, "numpy", numpy_stub)

    pyside6 = types.ModuleType("PySide6")
    pyside6.__version__ = "6.0"
    pyside6.__file__ = "PySide6/__init__.py"

    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.__version__ = "6.0"
    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    qtwidgets.__version__ = "6.0"
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.__version__ = "6.0"

    monkeypatch.setitem(sys.modules, "PySide6", pyside6)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", qtwidgets)
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", qtgui)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = entry_module.check_dependencies()

    assert result is True


def test_main_reports_missing_dependencies(entry_module, monkeypatch):
    """The main function should exit early when dependencies are missing."""
    monkeypatch.setattr(entry_module, "setup_environment", lambda: None)
    monkeypatch.setattr(entry_module, "check_dependencies", lambda: False)
    monkeypatch.setitem(sys.modules, "main", types.ModuleType("main"))

    monkeypatch.setattr(sys, "argv", ["huntpro", "--check-deps"])

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = entry_module.main()

    output = buffer.getvalue()

    assert exit_code == 1
    assert "Some dependencies are missing" in output
