import importlib
import sys
import types
from datetime import datetime
from pathlib import Path
import pytest
def _install_qt_stubs() -> None:
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
    gui_module = _create_module(
        "PySide6.QtGui",
        ["QFont", "QColor", "QPixmap", "QPainter"],
    )
    qt_module.QtGui = gui_module
    sys.modules["PySide6.QtGui"] = gui_module
    charts_module = _create_module(
        "PySide6.QtCharts",
        ["QChart", "QChartView", "QPieSeries", "QBarSeries", "QBarSet"],
    )
    qt_module.QtCharts = charts_module
    sys.modules["PySide6.QtCharts"] = charts_module
_install_qt_stubs()
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if "main" not in sys.modules:
    main_module = types.ModuleType("main")
    class BaseModule:
        def __init__(self, *args, **kwargs):
            pass
    main_module.BaseModule = BaseModule
    sys.modules["main"] = main_module
game_log = importlib.import_module("game_log")
GameLogValidator = game_log.GameLogValidator
GameLogValidationError = game_log.GameLogValidationError
EntryType = game_log.EntryType
GameSpecies = game_log.GameSpecies
WeatherCondition = game_log.WeatherCondition
WindDirection = game_log.WindDirection
def build_entry(**overrides):
    base_entry = {
        "id": "test-id",
        "timestamp": datetime(2024, 5, 1, 6, 30).isoformat(),
        "entry_type": EntryType.SIGHTING.value,
        "species": GameSpecies.WHITETAIL_DEER.value,
        "count": 2,
        "location": {
            "name": "North Stand",
            "description": "Overlooks feeding plot",
            "latitude": 45.1234,
            "longitude": -93.1234,
        },
        "weather": {
            "condition": WeatherCondition.OVERCAST.value,
            "temperature": "12.5",
            "humidity": "78",
            "pressure": 1009.3,
            "wind_speed": "8.2",
            "wind_direction": WindDirection.NORTH.value,
            "visibility": "5.5",
        },
        "weight": "85.4",
        "antler_points": "8",
        "weapon": "Compound Bow",
        "ammunition": "Fixed Blade",
        "shot_distance": "32.7",
        "field_dressed": "true",
        "notes": "Observed two does near the edge of the field.",
        "photos": ["/photos/entry1.jpg"],
    }
    base_entry.update(overrides)
    return base_entry
def test_validate_document_normalizes_legacy_list():
    entry = build_entry()
    version, entries = GameLogValidator.validate_document([entry])
    assert version == 0
    assert len(entries) == 1
    normalized = entries[0]
    assert normalized["entry_type"] == EntryType.SIGHTING.value
    assert normalized["species"] == GameSpecies.WHITETAIL_DEER.value
    assert isinstance(normalized["timestamp"], float)
    assert isinstance(normalized["weather"], dict)
    assert normalized["field_dressed"] is True
    assert normalized["antler_points"] == 8
    assert pytest.approx(normalized["shot_distance"], rel=1e-5) == 32.7
def test_validate_document_rejects_invalid_entry_type():
    entry = build_entry(entry_type="Invalid Type")
    with pytest.raises(GameLogValidationError):
        GameLogValidator.validate_document({
            "schema_version": GameLogValidator.CURRENT_VERSION,
            "entries": [entry],
        })
def test_validate_document_rejects_unknown_schema():
    with pytest.raises(GameLogValidationError):
        GameLogValidator.validate_document({
            "schema_version": 99,
            "entries": [],
        })
