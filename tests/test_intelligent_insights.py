"""Tests for the intelligent insights module."""
from __future__ import annotations

import sys
import types
from datetime import datetime

import pytest


def _install_qt_stubs() -> None:
    """Provide lightweight Qt replacements so ``game_log`` can be imported."""

    if "PySide6" in sys.modules:
        return

    qt_module = types.ModuleType("PySide6")
    sys.modules["PySide6"] = qt_module

    def _create_module(name: str, class_names):
        module = types.ModuleType(name)
        for class_name in class_names:
            setattr(module, class_name, type(class_name, (), {}))
        return module

    widgets_names = [
        "QWidget",
        "QVBoxLayout",
        "QHBoxLayout",
        "QFormLayout",
        "QGridLayout",
        "QTabWidget",
        "QPushButton",
        "QLabel",
        "QLineEdit",
        "QTextEdit",
        "QSpinBox",
        "QDoubleSpinBox",
        "QComboBox",
        "QCheckBox",
        "QDateEdit",
        "QTimeEdit",
        "QTableWidget",
        "QTableWidgetItem",
        "QHeaderView",
        "QGroupBox",
        "QScrollArea",
        "QProgressBar",
        "QMessageBox",
        "QFileDialog",
        "QFrame",
        "QSplitter",
        "QTreeWidget",
        "QTreeWidgetItem",
    ]
    widgets_module = _create_module("PySide6.QtWidgets", widgets_names)
    qt_module.QtWidgets = widgets_module
    sys.modules["PySide6.QtWidgets"] = widgets_module

    class Signal:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            pass

        def emit(self, *args, **kwargs):
            pass

    class QThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def quit(self):
            pass

        def wait(self):
            pass

    class QTimer:
        @staticmethod
        def singleShot(*args, **kwargs):
            pass

    class QtNamespace:
        ScrollBarAsNeeded = 0
        Horizontal = 1
        UserRole = 32
        AlignRight = 0

    core_module = types.ModuleType("PySide6.QtCore")
    core_module.Signal = Signal
    core_module.QThread = QThread
    core_module.QTimer = QTimer
    core_module.Qt = QtNamespace
    for name in [
        "QDate",
        "QTime",
        "QDateTime",
        "QSettings",
        "QAbstractTableModel",
        "QModelIndex",
    ]:
        setattr(core_module, name, type(name, (), {}))
    qt_module.QtCore = core_module
    sys.modules["PySide6.QtCore"] = core_module

    gui_module = _create_module("PySide6.QtGui", ["QFont", "QColor", "QPixmap", "QPainter"])
    qt_module.QtGui = gui_module
    sys.modules["PySide6.QtGui"] = gui_module

    charts_module = _create_module(
        "PySide6.QtCharts", ["QChart", "QChartView", "QPieSeries", "QBarSeries", "QBarSet"]
    )
    qt_module.QtCharts = charts_module
    sys.modules["PySide6.QtCharts"] = charts_module


_install_qt_stubs()

from game_log import (  # noqa: E402  (import after installing stubs)
    EntryType,
    GameEntry,
    GameSpecies,
    Location,
    Weather,
    WeatherCondition,
    WindDirection,
)
from intelligent_insights import HistoricalHuntInsightModel


def _build_entry(
    *,
    location_name: str,
    hour: int,
    entry_type: EntryType = EntryType.SIGHTING,
    species: GameSpecies = GameSpecies.WHITETAIL_DEER,
    weather_condition: WeatherCondition = WeatherCondition.OVERCAST,
    wind_direction: WindDirection = WindDirection.NORTH,
) -> GameEntry:
    base_time = datetime(2024, 10, 15, hour, 0)
    return GameEntry(
        timestamp=base_time.timestamp(),
        entry_type=entry_type,
        species=species,
        location=Location(name=location_name),
        weather=Weather(condition=weather_condition, wind_direction=wind_direction),
    )


def test_recommendations_prioritise_matching_conditions():
    entries = [
        _build_entry(location_name="North Stand", hour=6, entry_type=EntryType.HARVEST),
        _build_entry(location_name="North Stand", hour=7),
        _build_entry(location_name="North Stand", hour=6, wind_direction=WindDirection.NORTHWEST),
        _build_entry(
            location_name="South Stand",
            hour=14,
            entry_type=EntryType.SIGHTING,
            weather_condition=WeatherCondition.CLEAR,
            wind_direction=WindDirection.SOUTH,
        ),
        _build_entry(
            location_name="South Stand",
            hour=13,
            entry_type=EntryType.TRACK,
            weather_condition=WeatherCondition.CLEAR,
            wind_direction=WindDirection.SOUTH,
        ),
    ]

    model = HistoricalHuntInsightModel()
    model.fit(entries)

    recommendations = model.recommend_stands(
        species=GameSpecies.WHITETAIL_DEER,
        weather=WeatherCondition.OVERCAST,
        wind=WindDirection.NORTH,
        hour=6,
        top_n=2,
    )

    assert len(recommendations) == 2
    assert recommendations[0].location == "North Stand"
    assert recommendations[0].probability > recommendations[1].probability
    assert recommendations[0].supporting_entries >= 3
    assert "species" in recommendations[0].contributing_factors
    assert "weather" in recommendations[0].contributing_factors


def test_movement_patterns_surface_peak_hours_and_hotspots():
    entries = [
        _build_entry(location_name="North Stand", hour=6, entry_type=EntryType.HARVEST),
        _build_entry(location_name="North Stand", hour=6),
        _build_entry(location_name="North Stand", hour=7),
        _build_entry(location_name="South Stand", hour=18),
        _build_entry(location_name="South Stand", hour=18, entry_type=EntryType.TRACK),
    ]

    model = HistoricalHuntInsightModel()
    model.fit(entries)

    prediction = model.predict_movement_patterns(GameSpecies.WHITETAIL_DEER)

    assert prediction.peak_hours[0] == 6
    assert prediction.hotspot_locations[0] == "North Stand"
    assert pytest.approx(sum(prediction.hourly_intensity.values()), rel=1e-5) == 1.0
    assert prediction.hourly_intensity[6] > prediction.hourly_intensity[18]
