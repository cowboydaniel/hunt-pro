import importlib
import json
import sys
import types
from datetime import datetime
from pathlib import Path
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
        "QSlider",
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
        "QObject",
    ]:
        setattr(core_module, name, type(name, (), {}))
    qt_module.QtCore = core_module
    sys.modules["PySide6.QtCore"] = core_module
    gui_module = _create_module(
        "PySide6.QtGui",
        ["QFont", "QColor", "QPixmap", "QPainter", "QPen"],
    )
    qt_module.QtGui = gui_module
    sys.modules["PySide6.QtGui"] = gui_module
    charts_module = _create_module(
        "PySide6.QtCharts",
        [
            "QChart",
            "QChartView",
            "QPieSeries",
            "QBarSeries",
            "QBarSet",
            "QLineSeries",
            "QValueAxis",
        ],
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
migrations = importlib.import_module("migrations")
game_log = importlib.import_module("game_log")
ballistics = importlib.import_module("ballistics")
GameLogValidator = game_log.GameLogValidator
BallisticProfile = ballistics.BallisticProfile
class _StubLogger:
    def info(self, *args, **kwargs):
        pass
def test_migrate_game_log_store_upgrades_legacy(tmp_path: Path):
    legacy_entry = {
        "id": "legacy-entry",
        "timestamp": datetime(2023, 5, 1, 6, 30).isoformat(),
        "entry_type": game_log.EntryType.SIGHTING.value,
        "species": game_log.GameSpecies.WHITETAIL_DEER.value,
        "count": 2,
        "location": {
            "name": "Legacy Ridge",
            "description": "Converted from list payload",
        },
        "weather": {
            "condition": game_log.WeatherCondition.CLEAR.value,
            "temperature": "10",
            "humidity": "70",
            "pressure": 1012.5,
            "wind_speed": "3.5",
            "wind_direction": game_log.WindDirection.NORTH.value,
            "visibility": "5.0",
        },
        "notes": "Legacy serialized entry",
        "field_dressed": False,
    }
    data_file = tmp_path / "game_log.json"
    data_file.write_text(json.dumps([legacy_entry], indent=2))
    outcome = migrations.migrate_game_log_store(
        data_file,
        validator=GameLogValidator,
        target_version=GameLogValidator.CURRENT_VERSION,
        logger=_StubLogger(),
    )
    assert outcome is not None
    assert outcome.previous_version == 0
    assert outcome.new_version == GameLogValidator.CURRENT_VERSION
    assert outcome.backup_path is not None
    assert outcome.backup_path.exists()
    document = json.loads(data_file.read_text())
    assert document["schema_version"] == GameLogValidator.CURRENT_VERSION
    assert "migrated_at" in document
    assert len(document.get("entries", [])) == 1
    normalized_entry = document["entries"][0]
    assert normalized_entry["count"] == 2
    assert normalized_entry["entry_type"] == game_log.EntryType.SIGHTING.value
def test_migrate_ballistic_profile_store_from_list(tmp_path: Path):
    storage_file = tmp_path / "profiles.json"
    backup_dir = tmp_path / "backups"
    legacy_profiles = [
        {
            "name": "Legacy 308",
            "ammunition": {
                "name": "308 Win 168gr",
                "caliber": ".308",
                "bullet_weight": 168,
                "muzzle_velocity": 820,
                "ballistic_coefficient": 0.475,
                "drag_model": ballistics.DragModel.G1.value,
                "bullet_diameter": 7.82,
                "case_length": 51.18,
                "overall_length": 71.12,
            },
            "environment": {
                "temperature": 15,
                "pressure": 1013.25,
                "humidity": 55,
                "altitude": 320,
                "wind_speed": 3.2,
                "wind_direction": 45,
            },
            "zero_distance": 100,
            "max_range": 800,
            "vital_zone_diameter": 0.3,
            "notes": "Legacy profile without version",
        }
    ]
    storage_file.write_text(json.dumps(legacy_profiles, indent=2))
    outcome = migrations.migrate_ballistic_profile_store(
        storage_file,
        loader=BallisticProfile.from_dict,
        dumper=lambda profile: profile.to_dict(),
        target_version=ballistics.BALLISTIC_PROFILE_SCHEMA_VERSION,
        backup_dir=backup_dir,
        logger=_StubLogger(),
    )
    assert outcome is not None
    assert outcome.previous_version == 0
    assert outcome.new_version == ballistics.BALLISTIC_PROFILE_SCHEMA_VERSION
    assert outcome.backup_path is not None
    assert outcome.backup_path.exists()
    payload = json.loads(storage_file.read_text())
    assert payload["version"] == ballistics.BALLISTIC_PROFILE_SCHEMA_VERSION
    assert "migrated_at" in payload
    assert len(payload.get("profiles", [])) == 1
    migrated_profile = payload["profiles"][0]
    assert "created_at" in migrated_profile
    assert migrated_profile["ammunition"]["drag_model"] == ballistics.DragModel.G1.value
