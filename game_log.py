"""
Game Log Module for Hunt Pro.
Comprehensive hunting activity tracking including harvests, sightings,
and field observations with detailed statistics and export capabilities.
"""
import json
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, date, time as time_module
from typing import List, Dict, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from enum import Enum, auto
import uuid
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QTabWidget, QPushButton, QLabel, QLineEdit, QTextEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QDateEdit, QTimeEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QScrollArea, QProgressBar, QMessageBox, QFileDialog,
    QFrame, QSplitter, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QThread, QDate, QTime, QDateTime,
    QSettings, QAbstractTableModel, QModelIndex
)
from PySide6.QtGui import QFont, QColor, QPixmap, QPainter
from PySide6.QtCharts import QChart, QChartView, QPieSeries, QBarSeries, QBarSet
from main import BaseModule
from logger import get_logger, LoggableMixin
from migrations import migrate_game_log_store, MigrationError
GAME_LOG_SCHEMA_VERSION = 1
class GameLogValidationError(Exception):
    """Raised when game log data fails validation."""
class EntryType(Enum):
    """Types of game log entries."""
    SIGHTING = "Sighting"
    HARVEST = "Harvest"
    TRACK = "Track/Sign"
    SCOUT = "Scouting"
    SETUP = "Stand/Blind Setup"
    WEATHER = "Weather Observation"
class GameSpecies(Enum):
    """Game species for tracking."""
    WHITETAIL_DEER = "Whitetail Deer"
    MULE_DEER = "Mule Deer"
    ELK = "Elk"
    MOOSE = "Moose"
    BLACK_BEAR = "Black Bear"
    BROWN_BEAR = "Brown Bear"
    WILD_TURKEY = "Wild Turkey"
    DUCK = "Duck"
    GOOSE = "Goose"
    PHEASANT = "Pheasant"
    QUAIL = "Quail"
    RABBIT = "Rabbit"
    SQUIRREL = "Squirrel"
    COYOTE = "Coyote"
    WILD_HOG = "Wild Hog"
    OTHER = "Other"
class WeatherCondition(Enum):
    """Weather conditions."""
    CLEAR = "Clear"
    PARTLY_CLOUDY = "Partly Cloudy"
    OVERCAST = "Overcast"
    LIGHT_RAIN = "Light Rain"
    HEAVY_RAIN = "Heavy Rain"
    DRIZZLE = "Drizzle"
    SNOW = "Snow"
    FOG = "Fog"
    WINDY = "Windy"
class WindDirection(Enum):
    """Wind directions."""
    NORTH = "North"
    NORTHEAST = "Northeast"
    EAST = "East"
    SOUTHEAST = "Southeast"
    SOUTH = "South"
    SOUTHWEST = "Southwest"
    WEST = "West"
    NORTHWEST = "Northwest"
    CALM = "Calm"
@dataclass
class Location:
    """Location information for game entries."""
    name: str = ""
    description: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
@dataclass
class Weather:
    """Weather conditions for game entries."""
    condition: WeatherCondition = WeatherCondition.CLEAR
    temperature: float = 20.0  # Celsius
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    wind_speed: float = 0.0  # km/h
    wind_direction: WindDirection = WindDirection.CALM
    visibility: Optional[float] = None
@dataclass
class GameEntry:
    """Individual game log entry."""
    id: str = ""
    timestamp: float = 0.0
    entry_type: EntryType = EntryType.SIGHTING
    species: GameSpecies = GameSpecies.WHITETAIL_DEER
    count: int = 1
    # Location and weather
    location: Location = None
    weather: Weather = None
    # Harvest-specific fields
    weight: Optional[float] = None  # kg
    antler_points: Optional[int] = None
    weapon: str = ""
    ammunition: str = ""
    shot_distance: Optional[float] = None  # meters
    field_dressed: bool = False
    # General fields
    notes: str = ""
    photos: List[str] = None  # Photo file paths
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.timestamp == 0.0:
            self.timestamp = datetime.now().timestamp()
        if self.location is None:
            self.location = Location()
        if self.weather is None:
            self.weather = Weather()
        if self.photos is None:
            self.photos = []
    @property
    def date_string(self) -> str:
        """Get formatted date string."""
        return datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d")
    @property
    def time_string(self) -> str:
        """Get formatted time string."""
        return datetime.fromtimestamp(self.timestamp).strftime("%H:%M")
    @property
    def datetime_obj(self) -> datetime:
        """Get datetime object."""
        return datetime.fromtimestamp(self.timestamp)
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert enums to strings
        data['entry_type'] = self.entry_type.value
        data['species'] = self.species.value
        data['weather']['condition'] = self.weather.condition.value
        data['weather']['wind_direction'] = self.weather.wind_direction.value
        return data
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameEntry':
        """Create from dictionary."""
        # Convert string enums back
        if 'entry_type' in data and isinstance(data['entry_type'], str):
            data['entry_type'] = EntryType(data['entry_type'])
        if 'species' in data and isinstance(data['species'], str):
            data['species'] = GameSpecies(data['species'])
        if 'weather' in data and isinstance(data['weather'], dict):
            if 'condition' in data['weather']:
                data['weather']['condition'] = WeatherCondition(data['weather']['condition'])
            if 'wind_direction' in data['weather']:
                data['weather']['wind_direction'] = WindDirection(data['weather']['wind_direction'])
            data['weather'] = Weather(**data['weather'])
        if 'location' in data and isinstance(data['location'], dict):
            data['location'] = Location(**data['location'])
        return cls(**data)
class GameLogValidator:
    """Validate and normalize persisted game log data."""
    CURRENT_VERSION = GAME_LOG_SCHEMA_VERSION
    SUPPORTED_VERSIONS = {0, CURRENT_VERSION}
    @classmethod
    def _normalize_enum(
        cls,
        enum_cls: Enum,
        value: Any,
        field_label: str,
        entry_index: int,
    ) -> str:
        """Return the enum value ensuring it is valid."""
        if isinstance(value, enum_cls):
            return value.value
        if isinstance(value, str):
            try:
                return enum_cls(value).value
            except ValueError:
                try:
                    return enum_cls[value].value
                except (KeyError, ValueError):
                    raise GameLogValidationError(
                        f"Entry {entry_index}: Invalid {field_label.lower()} '{value}'"
                    ) from None
        raise GameLogValidationError(
            f"Entry {entry_index}: {field_label} must be a string"
        )
    @classmethod
    def _normalize_timestamp(cls, value: Any, entry_index: int) -> float:
        if isinstance(value, (int, float)):
            timestamp = float(value)
        elif isinstance(value, str):
            try:
                timestamp = datetime.fromisoformat(value).timestamp()
            except ValueError as exc:
                raise GameLogValidationError(
                    f"Entry {entry_index}: Invalid timestamp string '{value}'"
                ) from exc
        else:
            raise GameLogValidationError(
                f"Entry {entry_index}: Timestamp must be a number or ISO formatted string"
            )
        if timestamp <= 0:
            raise GameLogValidationError(
                f"Entry {entry_index}: Timestamp must be a positive value"
            )
        return timestamp
    @classmethod
    def _normalize_optional_float(
        cls, value: Any, field_label: str, entry_index: int
    ) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError as exc:
                raise GameLogValidationError(
                    f"Entry {entry_index}: {field_label} must be numeric"
                ) from exc
        raise GameLogValidationError(
            f"Entry {entry_index}: {field_label} must be numeric or null"
        )
    @classmethod
    def _normalize_optional_int(
        cls, value: Any, field_label: str, entry_index: int
    ) -> Optional[int]:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise GameLogValidationError(
                f"Entry {entry_index}: {field_label} must be an integer"
            )
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError as exc:
                raise GameLogValidationError(
                    f"Entry {entry_index}: {field_label} must be an integer"
                ) from exc
        raise GameLogValidationError(
            f"Entry {entry_index}: {field_label} must be an integer"
        )
    @classmethod
    def _normalize_bool(cls, value: Any, field_label: str, entry_index: int) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1"}:
                return True
            if lowered in {"false", "no", "0"}:
                return False
        raise GameLogValidationError(
            f"Entry {entry_index}: {field_label} must be a boolean"
        )
    @classmethod
    def _normalize_photos(cls, value: Any, entry_index: int) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise GameLogValidationError(
                f"Entry {entry_index}: Photos must be a list of file paths"
            )
        photos: List[str] = []
        for photo in value:
            if not isinstance(photo, str):
                raise GameLogValidationError(
                    f"Entry {entry_index}: Photo entries must be strings"
                )
            photos.append(photo)
        return photos
    @classmethod
    def _normalize_notes(cls, value: Any, entry_index: int) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise GameLogValidationError(
                f"Entry {entry_index}: Notes must be a string"
            )
        return value
    @classmethod
    def _normalize_location(cls, value: Any, entry_index: int) -> Dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise GameLogValidationError(
                f"Entry {entry_index}: Location must be an object"
            )
        normalized = {}
        for key in [
            "name",
            "description",
            "latitude",
            "longitude",
            "accuracy",
            "altitude",
        ]:
            if key in value:
                normalized[key] = value[key]
        return normalized
    @classmethod
    def _normalize_weather(cls, value: Any, entry_index: int) -> Dict[str, Any]:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise GameLogValidationError(
                f"Entry {entry_index}: Weather must be an object"
            )
        normalized: Dict[str, Any] = {}
        default_weather = Weather()
        normalized["condition"] = cls._normalize_enum(
            WeatherCondition,
            value.get("condition", default_weather.condition),
            "Weather Condition",
            entry_index,
        )
        temperature = value.get("temperature")
        if temperature is None or temperature == "":
            normalized["temperature"] = default_weather.temperature
        elif isinstance(temperature, (int, float)):
            normalized["temperature"] = float(temperature)
        elif isinstance(temperature, str):
            try:
                normalized["temperature"] = float(temperature)
            except ValueError as exc:
                raise GameLogValidationError(
                    f"Entry {entry_index}: Temperature must be numeric"
                ) from exc
        else:
            raise GameLogValidationError(
                f"Entry {entry_index}: Temperature must be numeric"
            )
        normalized["humidity"] = cls._normalize_optional_float(
            value.get("humidity"), "Humidity", entry_index
        )
        normalized["pressure"] = cls._normalize_optional_float(
            value.get("pressure"), "Pressure", entry_index
        )
        wind_speed = value.get("wind_speed")
        if wind_speed is None or wind_speed == "":
            normalized["wind_speed"] = default_weather.wind_speed
        elif isinstance(wind_speed, (int, float)):
            normalized["wind_speed"] = float(wind_speed)
        elif isinstance(wind_speed, str):
            try:
                normalized["wind_speed"] = float(wind_speed)
            except ValueError as exc:
                raise GameLogValidationError(
                    f"Entry {entry_index}: Wind speed must be numeric"
                ) from exc
        else:
            raise GameLogValidationError(
                f"Entry {entry_index}: Wind speed must be numeric"
            )
        normalized["wind_direction"] = cls._normalize_enum(
            WindDirection,
            value.get("wind_direction", default_weather.wind_direction),
            "Wind Direction",
            entry_index,
        )
        normalized["visibility"] = cls._normalize_optional_float(
            value.get("visibility"), "Visibility", entry_index
        )
        return normalized
    @classmethod
    def _normalize_entry(cls, entry: Dict[str, Any], entry_index: int) -> Dict[str, Any]:
        if not isinstance(entry, dict):
            raise GameLogValidationError(
                f"Entry {entry_index}: Each entry must be an object"
            )
        normalized: Dict[str, Any] = {}
        entry_id = entry.get("id")
        if entry_id is None:
            entry_id = str(uuid.uuid4())
        elif not isinstance(entry_id, str):
            raise GameLogValidationError(
                f"Entry {entry_index}: id must be a string"
            )
        normalized["id"] = entry_id
        normalized["timestamp"] = cls._normalize_timestamp(
            entry.get("timestamp", datetime.now().timestamp()), entry_index
        )
        normalized["entry_type"] = cls._normalize_enum(
            EntryType, entry.get("entry_type", EntryType.SIGHTING),
            "Entry Type",
            entry_index,
        )
        normalized["species"] = cls._normalize_enum(
            GameSpecies, entry.get("species", GameSpecies.WHITETAIL_DEER),
            "Species",
            entry_index,
        )
        count = entry.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, (int, float)):
            raise GameLogValidationError(
                f"Entry {entry_index}: Count must be a whole number"
            )
        count = int(count)
        if count <= 0:
            raise GameLogValidationError(
                f"Entry {entry_index}: Count must be positive"
            )
        normalized["count"] = count
        normalized["location"] = cls._normalize_location(
            entry.get("location"), entry_index
        )
        normalized["weather"] = cls._normalize_weather(
            entry.get("weather"), entry_index
        )
        normalized["weight"] = cls._normalize_optional_float(
            entry.get("weight"), "Weight", entry_index
        )
        normalized["antler_points"] = cls._normalize_optional_int(
            entry.get("antler_points"), "Antler points", entry_index
        )
        normalized["weapon"] = entry.get("weapon", "") if isinstance(entry.get("weapon"), str) else ""
        normalized["ammunition"] = entry.get("ammunition", "") if isinstance(entry.get("ammunition"), str) else ""
        normalized["shot_distance"] = cls._normalize_optional_float(
            entry.get("shot_distance"), "Shot distance", entry_index
        )
        field_dressed = entry.get("field_dressed", False)
        normalized["field_dressed"] = (
            field_dressed
            if isinstance(field_dressed, bool)
            else cls._normalize_bool(field_dressed, "Field dressed", entry_index)
        )
        normalized["notes"] = cls._normalize_notes(entry.get("notes"), entry_index)
        normalized["photos"] = cls._normalize_photos(entry.get("photos"), entry_index)
        return normalized
    @classmethod
    def validate_document(cls, document: Any) -> Tuple[int, List[Dict[str, Any]]]:
        """Validate the persisted document structure and entries."""
        if isinstance(document, list):
            schema_version = 0
            entries = document
        elif isinstance(document, dict):
            schema_version = document.get("schema_version", 0)
            entries = document.get("entries", [])
        else:
            raise GameLogValidationError("Game log data must be a list or object")
        if schema_version not in cls.SUPPORTED_VERSIONS:
            raise GameLogValidationError(
                f"Unsupported schema version: {schema_version}"
            )
        if not isinstance(entries, list):
            raise GameLogValidationError("Entries must be provided as a list")
        normalized_entries: List[Dict[str, Any]] = []
        for index, raw_entry in enumerate(entries):
            normalized_entries.append(cls._normalize_entry(raw_entry, index))
        return schema_version, normalized_entries
class ExportThread(QThread):
    """Background thread for exporting game log data."""
    export_complete = Signal(str)  # file_path
    export_error = Signal(str)  # error_message
    export_progress = Signal(int)  # progress percentage
    def __init__(self, entries: List[GameEntry], file_path: str, format_type: str):
        super().__init__()
        self.entries = entries
        self.file_path = file_path
        self.format_type = format_type.upper()
        self.logger = get_logger()
    def run(self):
        """Run export in background thread."""
        try:
            self.logger.info(f"Starting export of {len(self.entries)} entries to {self.file_path}")
            if self.format_type == "JSON":
                self.export_json()
            elif self.format_type == "CSV":
                self.export_csv()
            elif self.format_type == "KML":
                self.export_kml()
            elif self.format_type == "HTML":
                self.export_html()
            else:
                raise ValueError(f"Unsupported format: {self.format_type}")
            self.export_complete.emit(self.file_path)
            self.logger.info(f"Export completed successfully: {self.file_path}")
        except Exception as e:
            self.logger.error(f"Export failed: {str(e)}", exception=e)
            self.export_error.emit(str(e))
    def export_json(self):
        """Export to JSON format."""
        data = []
        for i, entry in enumerate(self.entries):
            data.append(entry.to_dict())
            self.export_progress.emit(int((i + 1) / len(self.entries) * 100))
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    def export_csv(self):
        """Export to CSV format."""
        fieldnames = [
            'id', 'date', 'time', 'entry_type', 'species', 'count',
            'location_name', 'location_description', 'latitude', 'longitude',
            'weather_condition', 'temperature', 'wind_speed', 'wind_direction',
            'weight', 'antler_points', 'weapon', 'ammunition', 'shot_distance',
            'field_dressed', 'notes'
        ]
        with open(self.file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for i, entry in enumerate(self.entries):
                row = {
                    'id': entry.id,
                    'date': entry.date_string,
                    'time': entry.time_string,
                    'entry_type': entry.entry_type.value,
                    'species': entry.species.value,
                    'count': entry.count,
                    'location_name': entry.location.name,
                    'location_description': entry.location.description,
                    'latitude': entry.location.latitude,
                    'longitude': entry.location.longitude,
                    'weather_condition': entry.weather.condition.value,
                    'temperature': entry.weather.temperature,
                    'wind_speed': entry.weather.wind_speed,
                    'wind_direction': entry.weather.wind_direction.value,
                    'weight': entry.weight,
                    'antler_points': entry.antler_points,
                    'weapon': entry.weapon,
                    'ammunition': entry.ammunition,
                    'shot_distance': entry.shot_distance,
                    'field_dressed': entry.field_dressed,
                    'notes': entry.notes
                }
                writer.writerow(row)
                self.export_progress.emit(int((i + 1) / len(self.entries) * 100))
    def export_html(self):
        """Export to HTML format."""
        html_content = self.generate_html_report()
        with open(self.file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        self.export_progress.emit(100)

    def export_kml(self):
        """Export to KML format for mapping hunts."""
        kml = ET.Element('kml', xmlns="http://www.opengis.net/kml/2.2")
        document = ET.SubElement(kml, 'Document')
        ET.SubElement(document, 'name').text = 'Hunt Pro Game Log'
        ET.SubElement(document, 'open').text = '1'

        for index, entry in enumerate(self.entries):
            placemark = ET.SubElement(document, 'Placemark')
            ET.SubElement(placemark, 'name').text = f"{entry.entry_type.value} - {entry.species.value}"

            timestamp_element = ET.SubElement(placemark, 'TimeStamp')
            ET.SubElement(timestamp_element, 'when').text = entry.datetime_obj.strftime('%Y-%m-%dT%H:%M:%SZ')

            description_parts = [
                f"Date: {entry.date_string}",
                f"Time: {entry.time_string}",
                f"Count: {entry.count}",
                f"Location: {entry.location.name or 'Unknown'}",
                f"Notes: {entry.notes or 'None'}",
            ]
            ET.SubElement(placemark, 'description').text = '\n'.join(description_parts)

            if entry.location.longitude is not None and entry.location.latitude is not None:
                point = ET.SubElement(placemark, 'Point')
                ET.SubElement(point, 'coordinates').text = f"{entry.location.longitude},{entry.location.latitude},0"

            extended_data = ET.SubElement(placemark, 'ExtendedData')
            metadata = {
                'EntryType': entry.entry_type.value,
                'Species': entry.species.value,
                'WeatherCondition': entry.weather.condition.value if entry.weather else None,
                'WindDirection': entry.weather.wind_direction.value if entry.weather else None,
                'WindSpeedKmh': entry.weather.wind_speed if entry.weather else None,
                'TemperatureC': entry.weather.temperature if entry.weather else None,
                'Weapon': entry.weapon,
                'Ammunition': entry.ammunition,
                'ShotDistanceMeters': entry.shot_distance,
                'FieldDressed': entry.field_dressed,
            }
            for key, value in metadata.items():
                if value in (None, ""):
                    continue
                data_element = ET.SubElement(extended_data, 'Data', name=key)
                ET.SubElement(data_element, 'value').text = str(value)

            self.export_progress.emit(int((index + 1) / len(self.entries) * 100))

        tree = ET.ElementTree(kml)
        tree.write(self.file_path, encoding='utf-8', xml_declaration=True)
    def generate_html_report(self) -> str:
        """Generate HTML report content."""
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hunt Pro - Game Log Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .header { background-color: #2c5aa0; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .header h1 { margin: 0; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; }
        .stat-number { font-size: 2em; font-weight: bold; color: #2c5aa0; }
        .entries { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .entry { border-bottom: 1px solid #eee; padding: 15px 0; }
        .entry:last-child { border-bottom: none; }
        .entry-header { font-weight: bold; color: #2c5aa0; margin-bottom: 5px; }
        .entry-details { color: #666; font-size: 0.9em; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; font-weight: bold; }
        .harvest { background-color: #e8f5e8; }
        .sighting { background-color: #e3f2fd; }
    </style>
</head>
<body>
"""
        # Header
        html += f"""
    <div class="header">
        <h1>ðŸ¹ Hunt Pro - Game Log Report</h1>
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
"""
        # Statistics
        harvests = [e for e in self.entries if e.entry_type == EntryType.HARVEST]
        sightings = [e for e in self.entries if e.entry_type == EntryType.SIGHTING]
        species_count = len(set(e.species for e in self.entries))
        html += f"""
    <div class="stats">
        <div class="stat-card">
            <div class="stat-number">{len(self.entries)}</div>
            <div>Total Entries</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{len(harvests)}</div>
            <div>Harvests</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{len(sightings)}</div>
            <div>Sightings</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{species_count}</div>
            <div>Species</div>
        </div>
    </div>
"""
        # Entries table
        html += """
    <div class="entries">
        <h2>Log Entries</h2>
        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Time</th>
                    <th>Type</th>
                    <th>Species</th>
                    <th>Count</th>
                    <th>Location</th>
                    <th>Notes</th>
                </tr>
            </thead>
            <tbody>
"""
        for entry in sorted(self.entries, key=lambda x: x.timestamp, reverse=True):
            row_class = "harvest" if entry.entry_type == EntryType.HARVEST else "sighting"
            html += f"""
                <tr class="{row_class}">
                    <td>{entry.date_string}</td>
                    <td>{entry.time_string}</td>
                    <td>{entry.entry_type.value}</td>
                    <td>{entry.species.value}</td>
                    <td>{entry.count}</td>
                    <td>{entry.location.name}</td>
                    <td>{entry.notes[:100]}{'...' if len(entry.notes) > 100 else ''}</td>
                </tr>
"""
        html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        return html
class GameLogModule(BaseModule):
    """Main game logging module for Hunt Pro."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: List[GameEntry] = []
        self.data_file = Path.home() / "HuntPro" / "game_log.json"
        self.export_thread: Optional[ExportThread] = None
        # Ensure data directory exists
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.setup_ui()
        self.load_data()
        self.log_info("Game log module initialized")
    def setup_ui(self):
        """Setup the game log user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        # Create tabs
        self.tab_widget.addTab(self._create_entry_tab(), "ðŸ“ New Entry")
        self.tab_widget.addTab(self._create_history_tab(), "ðŸ“‹ History")
        self.tab_widget.addTab(self._create_statistics_tab(), "ðŸ“Š Statistics")
        self.tab_widget.addTab(self._create_export_tab(), "ðŸ’¾ Export")
        # Apply styling
        self.apply_styling()
    def _create_entry_tab(self) -> QWidget:
        """Create the entry form tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # Scroll area for the form
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Form widget
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(20)
        # Basic information group
        basic_group = QGroupBox("ðŸ“‹ Basic Information")
        basic_layout = QFormLayout()
        self.entry_type_combo = QComboBox()
        self.entry_type_combo.setMinimumHeight(50)
        for entry_type in EntryType:
            self.entry_type_combo.addItem(entry_type.value, entry_type)
        basic_layout.addRow("Entry Type:", self.entry_type_combo)
        self.species_combo = QComboBox()
        self.species_combo.setMinimumHeight(50)
        for species in GameSpecies:
            self.species_combo.addItem(species.value, species)
        basic_layout.addRow("Species:", self.species_combo)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setMinimumHeight(50)
        basic_layout.addRow("Count:", self.count_spin)
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumHeight(50)
        basic_layout.addRow("Date:", self.date_edit)
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        self.time_edit.setMinimumHeight(50)
        basic_layout.addRow("Time:", self.time_edit)
        basic_group.setLayout(basic_layout)
        form_layout.addWidget(basic_group)
        # Location group
        location_group = QGroupBox("ðŸ“ Location")
        location_layout = QFormLayout()
        self.location_name_edit = QLineEdit()
        self.location_name_edit.setPlaceholderText("e.g., 'North Stand', 'Oak Ridge'")
        self.location_name_edit.setMinimumHeight(50)
        location_layout.addRow("Location Name:", self.location_name_edit)
        self.location_desc_edit = QTextEdit()
        self.location_desc_edit.setMaximumHeight(80)
        self.location_desc_edit.setPlaceholderText("Describe the location...")
        location_layout.addRow("Description:", self.location_desc_edit)
        # GPS coordinates (placeholder for future GPS integration)
        gps_layout = QHBoxLayout()
        self.latitude_spin = QDoubleSpinBox()
        self.latitude_spin.setRange(-90, 90)
        self.latitude_spin.setDecimals(6)
        self.latitude_spin.setMinimumHeight(50)
        gps_layout.addWidget(QLabel("Lat:"))
        gps_layout.addWidget(self.latitude_spin)
        self.longitude_spin = QDoubleSpinBox()
        self.longitude_spin.setRange(-180, 180)
        self.longitude_spin.setDecimals(6)
        self.longitude_spin.setMinimumHeight(50)
        gps_layout.addWidget(QLabel("Lon:"))
        gps_layout.addWidget(self.longitude_spin)
        location_layout.addRow("GPS Coordinates:", gps_layout)
        location_group.setLayout(location_layout)
        form_layout.addWidget(location_group)
        # Weather group
        weather_group = QGroupBox("ðŸŒ¤ï¸ Weather Conditions")
        weather_layout = QFormLayout()
        self.weather_condition_combo = QComboBox()
        self.weather_condition_combo.setMinimumHeight(50)
        for condition in WeatherCondition:
            self.weather_condition_combo.addItem(condition.value, condition)
        weather_layout.addRow("Condition:", self.weather_condition_combo)
        self.temperature_spin = QSpinBox()
        self.temperature_spin.setRange(-40, 50)
        self.temperature_spin.setValue(20)
        self.temperature_spin.setSuffix("Â°C")
        self.temperature_spin.setMinimumHeight(50)
        weather_layout.addRow("Temperature:", self.temperature_spin)
        self.wind_speed_spin = QSpinBox()
        self.wind_speed_spin.setRange(0, 100)
        self.wind_speed_spin.setSuffix(" km/h")
        self.wind_speed_spin.setMinimumHeight(50)
        weather_layout.addRow("Wind Speed:", self.wind_speed_spin)
        self.wind_direction_combo = QComboBox()
        self.wind_direction_combo.setMinimumHeight(50)
        for direction in WindDirection:
            self.wind_direction_combo.addItem(direction.value, direction)
        weather_layout.addRow("Wind Direction:", self.wind_direction_combo)
        weather_group.setLayout(weather_layout)
        form_layout.addWidget(weather_group)
        # Harvest details group (initially hidden)
        self.harvest_group = QGroupBox("ðŸŽ¯ Harvest Details")
        harvest_layout = QFormLayout()
        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(0, 1000)
        self.weight_spin.setDecimals(1)
        self.weight_spin.setSuffix(" kg")
        self.weight_spin.setMinimumHeight(50)
        harvest_layout.addRow("Weight:", self.weight_spin)
        self.antler_points_spin = QSpinBox()
        self.antler_points_spin.setRange(0, 50)
        self.antler_points_spin.setMinimumHeight(50)
        harvest_layout.addRow("Antler Points:", self.antler_points_spin)
        self.weapon_edit = QLineEdit()
        self.weapon_edit.setPlaceholderText("e.g., 'Remington 700 .308'")
        self.weapon_edit.setMinimumHeight(50)
        harvest_layout.addRow("Weapon:", self.weapon_edit)
        self.ammunition_edit = QLineEdit()
        self.ammunition_edit.setPlaceholderText("e.g., '150gr Nosler Partition'")
        self.ammunition_edit.setMinimumHeight(50)
        harvest_layout.addRow("Ammunition:", self.ammunition_edit)
        self.shot_distance_spin = QSpinBox()
        self.shot_distance_spin.setRange(0, 1000)
        self.shot_distance_spin.setSuffix(" m")
        self.shot_distance_spin.setMinimumHeight(50)
        harvest_layout.addRow("Shot Distance:", self.shot_distance_spin)
        self.field_dressed_check = QCheckBox("Field dressed")
        self.field_dressed_check.setMinimumHeight(50)
        harvest_layout.addRow(self.field_dressed_check)
        self.harvest_group.setLayout(harvest_layout)
        form_layout.addWidget(self.harvest_group)
        # Notes group
        notes_group = QGroupBox("ðŸ“ Notes")
        notes_layout = QVBoxLayout()
        self.notes_edit = QTextEdit()
        self.notes_edit.setMinimumHeight(120)
        self.notes_edit.setPlaceholderText("Add detailed notes about this entry...")
        notes_layout.addWidget(self.notes_edit)
        notes_group.setLayout(notes_layout)
        form_layout.addWidget(notes_group)
        # Form action buttons
        form_buttons_layout = QHBoxLayout()
        form_buttons_layout.setSpacing(15)
        # Save Entry button
        self.save_entry_btn = QPushButton("ðŸ’¾ Save Entry")
        self.save_entry_btn.setObjectName("primary")
        self.save_entry_btn.setMinimumHeight(60)
        self.save_entry_btn.clicked.connect(self.save_entry)
        form_buttons_layout.addWidget(self.save_entry_btn)
        # Clear Form button
        self.clear_form_btn = QPushButton("ðŸ—‘ï¸ Clear Form")
        self.clear_form_btn.setObjectName("secondary")
        self.clear_form_btn.setMinimumHeight(60)
        self.clear_form_btn.clicked.connect(self.clear_form)
        form_buttons_layout.addWidget(self.clear_form_btn)
        form_buttons_layout.addStretch()
        form_layout.addLayout(form_buttons_layout)
        # Add some bottom padding
        form_layout.addStretch()
        scroll_area.setWidget(form_widget)
        layout.addWidget(scroll_area)
        # Connect entry type change to show/hide harvest details
        self.entry_type_combo.currentIndexChanged.connect(self.on_entry_type_changed)
        self.on_entry_type_changed()  # Initialize visibility
        return tab
    def _create_history_tab(self) -> QWidget:
        """Create the history/log view tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # Filter controls
        filter_frame = QFrame()
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.addWidget(QLabel("Filter by Species:"))
        self.filter_species_combo = QComboBox()
        self.filter_species_combo.addItem("All Species", None)
        for species in GameSpecies:
            self.filter_species_combo.addItem(species.value, species)
        self.filter_species_combo.currentIndexChanged.connect(self.update_history_display)
        filter_layout.addWidget(self.filter_species_combo)
        filter_layout.addWidget(QLabel("Filter by Type:"))
        self.filter_type_combo = QComboBox()
        self.filter_type_combo.addItem("All Types", None)
        for entry_type in EntryType:
            self.filter_type_combo.addItem(entry_type.value, entry_type)
        self.filter_type_combo.currentIndexChanged.connect(self.update_history_display)
        filter_layout.addWidget(self.filter_type_combo)
        filter_layout.addStretch()
        # Delete selected button
        self.delete_selected_btn = QPushButton("ðŸ—‘ï¸ Delete Selected")
        self.delete_selected_btn.setObjectName("danger")
        self.delete_selected_btn.clicked.connect(self.delete_selected_entries)
        filter_layout.addWidget(self.delete_selected_btn)
        layout.addWidget(filter_frame)
        # History table
        self.history_table = QTableWidget()
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        headers = ["Date", "Time", "Type", "Species", "Count", "Location", "Weather", "Notes"]
        self.history_table.setColumnCount(len(headers))
        self.history_table.setHorizontalHeaderLabels(headers)
        # Set column widths
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Time
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Species
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Count
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # Location
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Weather
        header.setSectionResizeMode(7, QHeaderView.Stretch)  # Notes
        layout.addWidget(self.history_table)
        return tab
    def _create_statistics_tab(self) -> QWidget:
        """Create the statistics tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # Summary cards
        self.create_summary_cards(layout)
        # Charts area
        charts_splitter = QSplitter(Qt.Horizontal)
        # Species chart
        self.species_chart_view = QChartView()
        self.species_chart_view.setMinimumHeight(300)
        charts_splitter.addWidget(self.species_chart_view)
        # Monthly activity chart
        self.activity_chart_view = QChartView()
        self.activity_chart_view.setMinimumHeight(300)
        charts_splitter.addWidget(self.activity_chart_view)
        layout.addWidget(charts_splitter)
        return tab
    def _create_export_tab(self) -> QWidget:
        """Create the export tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # Export options
        export_group = QGroupBox("ðŸ’¾ Export Options")
        export_layout = QFormLayout()
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(["JSON", "CSV", "KML", "HTML"])
        self.export_format_combo.setMinimumHeight(50)
        export_layout.addRow("Format:", self.export_format_combo)
        # Date range
        date_range_layout = QHBoxLayout()
        self.export_start_date = QDateEdit()
        self.export_start_date.setDate(QDate.currentDate().addDays(-30))
        self.export_start_date.setMinimumHeight(50)
        date_range_layout.addWidget(self.export_start_date)
        date_range_layout.addWidget(QLabel("to"))
        self.export_end_date = QDateEdit()
        self.export_end_date.setDate(QDate.currentDate())
        self.export_end_date.setMinimumHeight(50)
        date_range_layout.addWidget(self.export_end_date)
        export_layout.addRow("Date Range:", date_range_layout)
        # Filter by type
        self.export_type_combo = QComboBox()
        self.export_type_combo.addItem("All Entry Types", None)
        for entry_type in EntryType:
            self.export_type_combo.addItem(entry_type.value, entry_type)
        self.export_type_combo.setMinimumHeight(50)
        export_layout.addRow("Entry Type:", self.export_type_combo)
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        # Export button
        self.export_btn = QPushButton("ðŸ’¾ Export Data")
        self.export_btn.setObjectName("primary")
        self.export_btn.setMinimumHeight(60)
        self.export_btn.clicked.connect(self.export_data)
        layout.addWidget(self.export_btn)
        # Export progress
        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        layout.addWidget(self.export_progress)
        # Export status
        self.export_status_label = QLabel("")
        layout.addWidget(self.export_status_label)
        layout.addStretch()
        return tab
    def create_summary_cards(self, layout):
        """Create summary statistic cards."""
        cards_frame = QFrame()
        cards_layout = QHBoxLayout(cards_frame)
        # Total entries card
        total_card = self.create_stat_card("Total Entries", str(len(self.entries)), "ðŸ“Š")
        cards_layout.addWidget(total_card)
        # Harvests card
        harvests = [e for e in self.entries if e.entry_type == EntryType.HARVEST]
        harvest_card = self.create_stat_card("Harvests", str(len(harvests)), "ðŸŽ¯")
        cards_layout.addWidget(harvest_card)
        # Sightings card
        sightings = [e for e in self.entries if e.entry_type == EntryType.SIGHTING]
        sighting_card = self.create_stat_card("Sightings", str(len(sightings)), "ðŸ‘ï¸")
        cards_layout.addWidget(sighting_card)
        # Species count card
        species_count = len(set(e.species for e in self.entries))
        species_card = self.create_stat_card("Species", str(species_count), "ðŸ¦Œ")
        cards_layout.addWidget(species_card)
        layout.addWidget(cards_frame)
    def create_stat_card(self, title: str, value: str, icon: str) -> QFrame:
        """Create a statistics card widget."""
        card = QFrame()
        card.setObjectName("statCard")
        card_layout = QVBoxLayout(card)
        # Icon and value
        header_layout = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Arial", 24))
        header_layout.addWidget(icon_label)
        value_label = QLabel(value)
        value_label.setFont(QFont("Arial", 32, QFont.Bold))
        value_label.setObjectName("statValue")
        header_layout.addWidget(value_label)
        header_layout.addStretch()
        card_layout.addLayout(header_layout)
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 14))
        title_label.setObjectName("statTitle")
        card_layout.addWidget(title_label)
        return card
    def apply_styling(self):
        """Apply styling to the game log module."""
        style = """
        QGroupBox {
            font-size: 16px;
            font-weight: bold;
            margin-top: 20px;
            padding-top: 10px;
            border: 2px solid #3d5a8c;
            border-radius: 8px;
            background-color: #f8f9fa;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            padding: 0 8px;
            color: #2c5aa0;
        }
        QPushButton#primary {
            background-color: #2c5aa0;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            padding: 15px;
        }
        QPushButton#primary:hover {
            background-color: #3d6bb0;
        }
        QPushButton#secondary {
            background-color: #6c757d;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            padding: 15px;
        }
        QPushButton#secondary:hover {
            background-color: #5a6268;
        }
        QPushButton#danger {
            background-color: #dc3545;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            padding: 10px;
        }
        QPushButton#danger:hover {
            background-color: #c82333;
        }
        QFrame#statCard {
            background-color: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 20px;
            margin: 5px;
        }
        QLabel#statValue {
            color: #2c5aa0;
        }
        QLabel#statTitle {
            color: #6c757d;
        }
        QTableWidget {
            gridline-color: #dee2e6;
            background-color: white;
            alternate-background-color: #f8f9fa;
        }
        QHeaderView::section {
            background-color: #e9ecef;
            padding: 10px;
            border: none;
            font-weight: bold;
        }
        """
        self.setStyleSheet(style)
    def on_entry_type_changed(self):
        """Handle entry type change to show/hide harvest details."""
        entry_type = self.entry_type_combo.currentData()
        is_harvest = entry_type == EntryType.HARVEST
        self.harvest_group.setVisible(is_harvest)
    def save_entry(self):
        """Save the current entry form to the log."""
        try:
            # Create entry from form data
            entry = GameEntry(
                entry_type=self.entry_type_combo.currentData(),
                species=self.species_combo.currentData(),
                count=self.count_spin.value(),
                notes=self.notes_edit.toPlainText()
            )
            # Set timestamp from date/time inputs
            date = self.date_edit.date().toPython()
            time = self.time_edit.time().toPython()
            dt = datetime.combine(date, time)
            entry.timestamp = dt.timestamp()
            # Location information
            entry.location = Location(
                name=self.location_name_edit.text(),
                description=self.location_desc_edit.toPlainText(),
                latitude=self.latitude_spin.value() if self.latitude_spin.value() != 0 else None,
                longitude=self.longitude_spin.value() if self.longitude_spin.value() != 0 else None
            )
            # Weather information
            entry.weather = Weather(
                condition=self.weather_condition_combo.currentData(),
                temperature=self.temperature_spin.value(),
                wind_speed=self.wind_speed_spin.value(),
                wind_direction=self.wind_direction_combo.currentData()
            )
            # Harvest-specific data
            if entry.entry_type == EntryType.HARVEST:
                if self.weight_spin.value() > 0:
                    entry.weight = self.weight_spin.value()
                if self.antler_points_spin.value() > 0:
                    entry.antler_points = self.antler_points_spin.value()
                entry.weapon = self.weapon_edit.text()
                entry.ammunition = self.ammunition_edit.text()
                if self.shot_distance_spin.value() > 0:
                    entry.shot_distance = self.shot_distance_spin.value()
                entry.field_dressed = self.field_dressed_check.isChecked()
            # Add to entries list
            self.entries.append(entry)
            # Update displays
            self.update_history_display()
            self.update_statistics()
            # Save to file
            self.save_data()
            # Clear form and show success
            self.clear_form()
            self.status_message.emit(f"Added {entry.entry_type.value}: {entry.species.value}")
            # Switch to history view to show new entry
            self.tab_widget.setCurrentIndex(1)
            self.log_field_event("Game log entry added", 
                               entry_type=entry.entry_type.value,
                               species=entry.species.value,
                               count=entry.count)
        except Exception as e:
            self.log_error("Failed to save entry", exception=e)
            self.error_occurred.emit("Save Error", f"Failed to save entry: {str(e)}")
    def clear_form(self):
        """Clear the entry form."""
        self.entry_type_combo.setCurrentIndex(0)
        self.species_combo.setCurrentIndex(0)
        self.count_spin.setValue(1)
        self.date_edit.setDate(QDate.currentDate())
        self.time_edit.setTime(QTime.currentTime())
        self.location_name_edit.clear()
        self.location_desc_edit.clear()
        self.latitude_spin.setValue(0)
        self.longitude_spin.setValue(0)
        self.weather_condition_combo.setCurrentIndex(0)
        self.temperature_spin.setValue(20)
        self.wind_speed_spin.setValue(0)
        self.wind_direction_combo.setCurrentIndex(0)
        self.weight_spin.setValue(0)
        self.antler_points_spin.setValue(0)
        self.weapon_edit.clear()
        self.ammunition_edit.clear()
        self.shot_distance_spin.setValue(0)
        self.field_dressed_check.setChecked(False)
        self.notes_edit.clear()
    def update_history_display(self):
        """Update the history table with filtered entries."""
        # Get filter values
        species_filter = self.filter_species_combo.currentData()
        type_filter = self.filter_type_combo.currentData()
        # Filter entries
        filtered_entries = []
        for entry in self.entries:
            if species_filter and entry.species != species_filter:
                continue
            if type_filter and entry.entry_type != type_filter:
                continue
            filtered_entries.append(entry)
        # Sort by timestamp (newest first)
        filtered_entries.sort(key=lambda x: x.timestamp, reverse=True)
        # Update table
        self.history_table.setRowCount(len(filtered_entries))
        for row, entry in enumerate(filtered_entries):
            items = [
                QTableWidgetItem(entry.date_string),
                QTableWidgetItem(entry.time_string),
                QTableWidgetItem(entry.entry_type.value),
                QTableWidgetItem(entry.species.value),
                QTableWidgetItem(str(entry.count)),
                QTableWidgetItem(entry.location.name),
                QTableWidgetItem(f"{entry.weather.condition.value}, {entry.weather.temperature}Â°C"),
                QTableWidgetItem(entry.notes[:100] + "..." if len(entry.notes) > 100 else entry.notes)
            ]
            for col, item in enumerate(items):
                # Color code by entry type
                if entry.entry_type == EntryType.HARVEST:
                    item.setBackground(QColor("#e8f5e8"))
                elif entry.entry_type == EntryType.SIGHTING:
                    item.setBackground(QColor("#e3f2fd"))
                # Store entry ID for reference
                item.setData(Qt.UserRole, entry.id)
                self.history_table.setItem(row, col, item)
    def delete_selected_entries(self):
        """Delete selected entries from the log."""
        selected_rows = set()
        for item in self.history_table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select entries to delete.")
            return
        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete {len(selected_rows)} selected entries?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Get entry IDs to delete
            entry_ids_to_delete = set()
            for row in selected_rows:
                item = self.history_table.item(row, 0)  # Get first item in row
                if item:
                    entry_id = item.data(Qt.UserRole)
                    if entry_id:
                        entry_ids_to_delete.add(entry_id)
            # Remove entries
            self.entries = [e for e in self.entries if e.id not in entry_ids_to_delete]
            # Save and update displays
            self.save_data()
            self.update_history_display()
            self.update_statistics()
            self.status_message.emit(f"Deleted {len(selected_rows)} entries")
            self.log_user_action("game_log_entries_deleted", {"count": len(selected_rows)})
    def update_statistics(self):
        """Update statistics displays and charts."""
        # Update summary cards
        if hasattr(self, 'tab_widget'):
            stats_tab = self.tab_widget.widget(2)  # Statistics tab
            if stats_tab:
                # Remove old cards and create new ones
                layout = stats_tab.layout()
                if layout.count() > 0:
                    cards_frame = layout.itemAt(0).widget()
                    if cards_frame:
                        layout.removeWidget(cards_frame)
                        cards_frame.deleteLater()
                self.create_summary_cards(layout)
        # Update charts
        self.update_species_chart()
        self.update_activity_chart()
    def update_species_chart(self):
        """Update the species distribution pie chart."""
        try:
            # Count entries by species
            species_counts = {}
            for entry in self.entries:
                species = entry.species.value
                species_counts[species] = species_counts.get(species, 0) + entry.count
            if not species_counts:
                return
            # Create pie series
            series = QPieSeries()
            for species, count in species_counts.items():
                series.append(f"{species} ({count})", count)
            # Create chart
            chart = QChart()
            chart.addSeries(series)
            chart.setTitle("Species Distribution")
            chart.legend().setAlignment(Qt.AlignRight)
            self.species_chart_view.setChart(chart)
        except Exception as e:
            self.log_error("Failed to update species chart", exception=e)
    def update_activity_chart(self):
        """Update the monthly activity bar chart."""
        try:
            # Count entries by month
            monthly_counts = {}
            for entry in self.entries:
                month_key = datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m")
                monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
            if not monthly_counts:
                return
            # Create bar series
            series = QBarSeries()
            bar_set = QBarSet("Entries")
            # Sort months and add data
            sorted_months = sorted(monthly_counts.keys())
            for month in sorted_months[-12:]:  # Last 12 months
                bar_set.append(monthly_counts.get(month, 0))
            series.append(bar_set)
            # Create chart
            chart = QChart()
            chart.addSeries(series)
            chart.setTitle("Monthly Activity (Last 12 Months)")
            chart.createDefaultAxes()
            self.activity_chart_view.setChart(chart)
        except Exception as e:
            self.log_error("Failed to update activity chart", exception=e)
    def export_data(self):
        """Export game log data to selected format."""
        try:
            # Get export parameters
            format_type = self.export_format_combo.currentText()
            start_date = self.export_start_date.date().toPython()
            end_date = self.export_end_date.date().toPython()
            type_filter = self.export_type_combo.currentData()
            # Filter entries for export
            entries_to_export = []
            for entry in self.entries:
                entry_date = datetime.fromtimestamp(entry.timestamp).date()
                # Date range filter
                if not (start_date <= entry_date <= end_date):
                    continue
                # Type filter
                if type_filter and entry.entry_type != type_filter:
                    continue
                entries_to_export.append(entry)
            if not entries_to_export:
                QMessageBox.information(self, "No Data", "No entries match the export criteria.")
                return
            # Get file path
            default_name = f"hunt_log_{datetime.now().strftime('%Y%m%d')}.{format_type.lower()}"
            file_path, _ = QFileDialog.getSaveFileName(
                self, f"Export as {format_type}", default_name,
                f"{format_type} Files (*.{format_type.lower()})"
            )
            if not file_path:
                return
            # Start export thread
            self.export_thread = ExportThread(entries_to_export, file_path, format_type)
            self.export_thread.export_complete.connect(self.on_export_complete)
            self.export_thread.export_error.connect(self.on_export_error)
            self.export_thread.export_progress.connect(self.on_export_progress)
            self.export_btn.setEnabled(False)
            self.export_progress.setVisible(True)
            self.export_progress.setValue(0)
            self.export_status_label.setText("Exporting...")
            self.export_thread.start()
            self.log_user_action("game_log_export_started", {
                "format": format_type,
                "entries_count": len(entries_to_export),
                "file_path": file_path
            })
        except Exception as e:
            self.log_error("Failed to start export", exception=e)
            self.error_occurred.emit("Export Error", f"Failed to start export: {str(e)}")
    def on_export_complete(self, file_path: str):
        """Handle export completion."""
        self.export_btn.setEnabled(True)
        self.export_progress.setVisible(False)
        self.export_status_label.setText(f"âœ… Export completed: {Path(file_path).name}")
        self.status_message.emit(f"Data exported to {Path(file_path).name}")
        if self.export_thread:
            self.export_thread.quit()
            self.export_thread.wait()
            self.export_thread = None
        self.log_user_action("game_log_export_completed", {"file_path": file_path})
    def on_export_error(self, error_message: str):
        """Handle export error."""
        self.export_btn.setEnabled(True)
        self.export_progress.setVisible(False)
        self.export_status_label.setText("âŒ Export failed")
        self.error_occurred.emit("Export Error", error_message)
        if self.export_thread:
            self.export_thread.quit()
            self.export_thread.wait()
            self.export_thread = None
    def on_export_progress(self, progress: int):
        """Handle export progress updates."""
        self.export_progress.setValue(progress)
    def save_data(self):
        """Save entries to JSON file."""
        try:
            document = {
                "schema_version": GameLogValidator.CURRENT_VERSION,
                "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
                "entries": [entry.to_dict() for entry in self.entries],
            }
            # Create backup of existing file
            if self.data_file.exists():
                backup_file = self.data_file.with_suffix('.json.backup')
                self.data_file.rename(backup_file)
            # Save new data
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(document, f, indent=2, ensure_ascii=False, default=str)
            self.log_debug(f"Saved {len(self.entries)} entries to {self.data_file}")
        except Exception as e:
            self.log_error("Failed to save game log data", exception=e)
            # Try to restore backup
            backup_file = self.data_file.with_suffix('.json.backup')
            if backup_file.exists():
                backup_file.rename(self.data_file)
            raise
    def load_data(self):
        """Load entries from JSON file."""
        try:
            if not self.data_file.exists():
                self.log_info("No existing game log data file found")
                return
            try:
                outcome = migrate_game_log_store(
                    self.data_file,
                    validator=GameLogValidator,
                    target_version=GameLogValidator.CURRENT_VERSION,
                    logger=self._logger,
                )
            except MigrationError as exc:
                self.log_error("Failed to migrate game log data", exception=exc)
                self.error_occurred.emit(
                    "Migration Error",
                    f"Could not migrate game log data: {exc}",
                )
                return
            if outcome:
                self.log_info(
                    "Migrated game log data file",
                    category="DATA",
                    previous_version=outcome.previous_version,
                    new_version=outcome.new_version,
                    backup=str(outcome.backup_path) if outcome.backup_path else None,
                )
            with open(self.data_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            try:
                schema_version, validated_entries = GameLogValidator.validate_document(raw_data)
            except GameLogValidationError as e:
                self.log_error("Game log validation failed", exception=e)
                self.error_occurred.emit(
                    "Validation Error",
                    f"Game log file failed validation: {str(e)}",
                )
                return
            if schema_version < GameLogValidator.CURRENT_VERSION:
                self.log_info(
                    f"Loaded game log with legacy schema version {schema_version}"
                )
            self.entries = []
            for entry_dict in validated_entries:
                try:
                    entry = GameEntry.from_dict(entry_dict)
                    self.entries.append(entry)
                except Exception as e:
                    self.log_warning(
                        f"Failed to load entry: {e}", entry_data=entry_dict
                    )
            self.log_info(f"Loaded {len(self.entries)} entries from {self.data_file}")
            # Update displays
            QTimer.singleShot(100, self.update_history_display)
            QTimer.singleShot(100, self.update_statistics)
        except Exception as e:
            self.log_error("Failed to load game log data", exception=e)
            self.error_occurred.emit("Load Error", f"Failed to load game log data: {str(e)}")
    def get_statistics_summary(self) -> Dict[str, Any]:
        """Get comprehensive statistics summary."""
        if not self.entries:
            return {}
        # Basic counts
        total_entries = len(self.entries)
        harvests = [e for e in self.entries if e.entry_type == EntryType.HARVEST]
        sightings = [e for e in self.entries if e.entry_type == EntryType.SIGHTING]
        # Species breakdown
        species_counts = {}
        harvest_species_counts = {}
        for entry in self.entries:
            species = entry.species.value
            species_counts[species] = species_counts.get(species, 0) + entry.count
            if entry.entry_type == EntryType.HARVEST:
                harvest_species_counts[species] = harvest_species_counts.get(species, 0) + entry.count
        # Time-based analysis
        entries_by_month = {}
        entries_by_hour = {}
        for entry in self.entries:
            dt = datetime.fromtimestamp(entry.timestamp)
            month_key = dt.strftime("%Y-%m")
            hour_key = dt.hour
            entries_by_month[month_key] = entries_by_month.get(month_key, 0) + 1
            entries_by_hour[hour_key] = entries_by_hour.get(hour_key, 0) + 1
        # Success rate
        success_rate = (len(harvests) / len(sightings)) * 100 if sightings else 0
        # Average harvest weight (for entries that have weight)
        weights = [h.weight for h in harvests if h.weight is not None]
        avg_weight = sum(weights) / len(weights) if weights else 0
        return {
            'total_entries': total_entries,
            'harvests': len(harvests),
            'sightings': len(sightings),
            'species_count': len(species_counts),
            'species_breakdown': species_counts,
            'harvest_species_breakdown': harvest_species_counts,
            'success_rate': round(success_rate, 1),
            'avg_harvest_weight': round(avg_weight, 1) if avg_weight else None,
            'entries_by_month': entries_by_month,
            'entries_by_hour': entries_by_hour,
            'date_range': {
                'start': min(e.date_string for e in self.entries) if self.entries else None,
                'end': max(e.date_string for e in self.entries) if self.entries else None
            }
        }
    def search_entries(self, query: str, search_fields: List[str] = None) -> List[GameEntry]:
        """Search entries by text query."""
        if not query.strip():
            return self.entries
        if search_fields is None:
            search_fields = ['notes', 'location.name', 'location.description', 'weapon', 'ammunition']
        query_lower = query.lower()
        matching_entries = []
        for entry in self.entries:
            # Check each search field
            for field in search_fields:
                field_value = ""
                if '.' in field:
                    # Nested field (e.g., 'location.name')
                    obj, attr = field.split('.', 1)
                    if hasattr(entry, obj):
                        nested_obj = getattr(entry, obj)
                        if hasattr(nested_obj, attr):
                            field_value = str(getattr(nested_obj, attr) or "")
                else:
                    # Direct field
                    if hasattr(entry, field):
                        field_value = str(getattr(entry, field) or "")
                if query_lower in field_value.lower():
                    matching_entries.append(entry)
                    break  # Found match, no need to check other fields
        return matching_entries
    def cleanup(self):
        """Clean up resources when module is closed."""
        # Stop export thread if running
        if self.export_thread and self.export_thread.isRunning():
            self.export_thread.quit()
            self.export_thread.wait()
        # Save current data
        self.save_data()
        super().cleanup()
        self.log_info("Game log module cleaned up")
    def get_display_name(self) -> str:
        """Return the display name for this module."""
        return "Game Log"
    def get_description(self) -> str:
        """Return a description of this module's functionality."""
        return "Track hunting activities, harvests, and field observations with detailed statistics and export capabilities."
# Utility functions for game log operations
def create_quick_sighting(species: GameSpecies, count: int = 1, notes: str = "") -> GameEntry:
    """Create a quick sighting entry."""
    return GameEntry(
        entry_type=EntryType.SIGHTING,
        species=species,
        count=count,
        notes=notes
    )
def create_quick_harvest(species: GameSpecies, weight: float = None, weapon: str = "", notes: str = "") -> GameEntry:
    """Create a quick harvest entry."""
    entry = GameEntry(
        entry_type=EntryType.HARVEST,
        species=species,
        count=1,
        weapon=weapon,
        notes=notes
    )
    if weight is not None:
        entry.weight = weight
    return entry
def parse_gps_coordinates(coord_string: str) -> tuple[Optional[float], Optional[float]]:
    """Parse GPS coordinates from various string formats."""
    try:
        # Remove extra whitespace and split
        parts = coord_string.replace(',', ' ').split()
        if len(parts) >= 2:
            lat = float(parts[0])
            lon = float(parts[1])
            return lat, lon
    except (ValueError, IndexError):
        pass
    return None, None
def format_coordinates(latitude: Optional[float], longitude: Optional[float]) -> str:
    """Format GPS coordinates for display."""
    if latitude is None or longitude is None:
        return "No GPS data"
    lat_dir = "N" if latitude >= 0 else "S"
    lon_dir = "E" if longitude >= 0 else "W"
    return f"{abs(latitude):.6f}Â°{lat_dir}, {abs(longitude):.6f}Â°{lon_dir}"
def calculate_distance_between_entries(entry1: GameEntry, entry2: GameEntry) -> Optional[float]:
    """Calculate distance in kilometers between two entries with GPS coordinates."""
    if (entry1.location.latitude is None or entry1.location.longitude is None or
        entry2.location.latitude is None or entry2.location.longitude is None):
        return None
    # Haversine formula
    import math
    lat1, lon1 = math.radians(entry1.location.latitude), math.radians(entry1.location.longitude)
    lat2, lon2 = math.radians(entry2.location.latitude), math.radians(entry2.location.longitude)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    # Earth radius in kilometers
    r = 6371
    return r * c
