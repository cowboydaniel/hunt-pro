"""
Navigation and Mapping Module for Hunt Pro.
GPS navigation, waypoint management, offline mapping, and location tracking
for hunting and outdoor activities.
"""
import json
import math
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from datetime import datetime
import uuid
try:  # pragma: no cover - optional Qt dependency
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
        QTabWidget, QPushButton, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
        QComboBox, QTextEdit, QTableWidget, QTableWidgetItem, QGroupBox,
        QScrollArea, QFrame, QSlider, QCheckBox, QProgressBar, QListWidget,
        QListWidgetItem, QHeaderView, QMessageBox, QSplitter
    )
    from PySide6.QtCore import (
        Qt, Signal, QTimer, QThread, QObject, QSettings, QPointF
    )
    from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPixmap
    from main import BaseModule
    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - executed when Qt bindings unavailable
    class _QtStub:
        def __init__(self, *_, **__):
            pass

        def __call__(self, *_, **__):
            return _QtStub()

        def __getattr__(self, _):
            return _QtStub()

        def __bool__(self):
            return False

    class _SignalStub:
        def connect(self, *_, **__):
            pass

        def emit(self, *_, **__):
            pass

    def Signal(*_, **__):  # type: ignore[override]
        return _SignalStub()

    class _TimerStub(_QtStub):
        def __init__(self, *_, **__):
            super().__init__()
            self.timeout = _SignalStub()

        def setInterval(self, *_, **__):
            pass

        def start(self, *_, **__):
            pass

        def stop(self, *_, **__):
            pass

    class _ThreadStub(_QtStub):
        def start(self, *_, **__):
            pass

        def quit(self, *_, **__):
            pass

        def wait(self, *_, **__):
            pass

    class _SettingsStub(dict):
        def value(self, key, default=None, type=None):  # type: ignore[override]
            return super().get(key, default)

        def setValue(self, key, value):  # type: ignore[override]
            self[key] = value

    class _QtNamespace:
        Horizontal = 1
        Vertical = 2
        AlignRight = 0
        AlignLeft = 0
        AlignBottom = 0
        AlignCenter = 0
        KeepAspectRatio = 0
        SmoothTransformation = 0

    QWidget = QVBoxLayout = QHBoxLayout = QFormLayout = QGridLayout = _QtStub
    QTabWidget = QPushButton = QLabel = QLineEdit = QSpinBox = QDoubleSpinBox = _QtStub
    QComboBox = QTextEdit = QTableWidget = QTableWidgetItem = QGroupBox = _QtStub
    QScrollArea = QFrame = QSlider = QCheckBox = QProgressBar = _QtStub
    QListWidget = QListWidgetItem = QHeaderView = QMessageBox = QSplitter = _QtStub
    QTimer = _TimerStub
    QThread = _ThreadStub
    QObject = _QtStub
    QSettings = _SettingsStub
    QPointF = _QtStub
    Qt = _QtNamespace()
    QFont = QColor = QPainter = QPen = QBrush = QPixmap = _QtStub
    class _BaseModuleStub:
        def __init__(self, *_, **__):
            pass

    BaseModule = _BaseModuleStub  # type: ignore[assignment]
    _QT_AVAILABLE = False
try:
    from PySide6.QtCharts import QChart, QChartView, QScatterSeries, QLineSeries
    _NAV_QT_CHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - charts optional at runtime
    QChart = QChartView = QScatterSeries = QLineSeries = None  # type: ignore
    _NAV_QT_CHARTS_AVAILABLE = False
if _QT_AVAILABLE:
    from main import BaseModule
from logger import get_logger, LoggableMixin
from map_tile_cache import CachedTile, MapTileCache, TileSource
class WaypointType(Enum):
    """Types of waypoints for navigation."""
    STAND = "Tree Stand"
    BLIND = "Ground Blind"
    CAMP = "Camp"
    VEHICLE = "Vehicle"
    TRACK = "Animal Track"
    WATER = "Water Source"
    FOOD_PLOT = "Food Plot"
    TRAIL = "Trail"
    BOUNDARY = "Property Boundary"
    HAZARD = "Hazard"
    CUSTOM = "Custom"
class NavigationMode(Enum):
    """Navigation display modes."""
    COMPASS = "Compass"
    MAP = "Map"
    SATELLITE = "Satellite"
    TERRAIN = "Terrain"


class TerrainOverlayType(Enum):
    """Supported terrain overlay modes for the navigation map."""

    NONE = "None"
    VEGETATION = "Vegetation Density"
    WATER = "Water Saturation"
    SLOPE = "Slope Exposure"


class POICategory(Enum):
    """Categories for points of interest rendered on the map."""

    WATER = "Water"
    FEED = "Feeding Area"
    SIGN = "Fresh Sign"
    ACCESS = "Access Point"
    CAMP = "Camp"
    OTHER = "Other"
@dataclass
class GPSCoordinate:
    """GPS coordinate with precision and metadata."""
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    accuracy: Optional[float] = None
    timestamp: Optional[float] = None
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()
    @property
    def latitude_dms(self) -> str:
        """Get latitude in degrees, minutes, seconds format."""
        return self._decimal_to_dms(self.latitude, 'NS')
    @property
    def longitude_dms(self) -> str:
        """Get longitude in degrees, minutes, seconds format."""
        return self._decimal_to_dms(self.longitude, 'EW')
    def _decimal_to_dms(self, decimal: float, directions: str) -> str:
        """Convert decimal degrees to DMS format."""
        direction = directions[0] if decimal >= 0 else directions[1]
        decimal = abs(decimal)
        degrees = int(decimal)
        minutes = int((decimal - degrees) * 60)
        seconds = ((decimal - degrees) * 60 - minutes) * 60
        return f"{degrees} deg {minutes}' {seconds:.2f}\" {direction}"
    def distance_to(self, other: 'GPSCoordinate') -> float:
        """Calculate distance to another coordinate in meters using Haversine formula."""
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        # Earth radius in meters
        r = 6371000
        return r * c
    def bearing_to(self, other: 'GPSCoordinate') -> float:
        """Calculate bearing to another coordinate in degrees."""
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.atan2(y, x)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360
        return bearing
@dataclass
class Waypoint:
    """Waypoint for navigation and mapping."""
    id: str = ""
    name: str = ""
    description: str = ""
    waypoint_type: WaypointType = WaypointType.CUSTOM
    coordinate: GPSCoordinate = None
    created_at: float = 0.0
    visited: bool = False
    visit_count: int = 0
    last_visited: Optional[float] = None
    color: str = "#FF0000"
    symbol: str = "Flag"
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.created_at == 0.0:
            self.created_at = datetime.now().timestamp()
        if self.coordinate is None:
            self.coordinate = GPSCoordinate(0.0, 0.0)
    def mark_visited(self):
        """Mark waypoint as visited."""
        self.visited = True
        self.visit_count += 1
        self.last_visited = datetime.now().timestamp()
    @property
    def created_datetime(self) -> datetime:
        """Get creation datetime."""
        return datetime.fromtimestamp(self.created_at)
    @property
    def last_visited_datetime(self) -> Optional[datetime]:
        """Get last visited datetime."""
        if self.last_visited:
            return datetime.fromtimestamp(self.last_visited)
        return None


@dataclass
class PointOfInterest:
    """Tagged point-of-interest rendered on the navigation map."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    category: POICategory = POICategory.OTHER
    coordinate: GPSCoordinate = None
    notes: str = ""
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())

    def __post_init__(self):
        if self.coordinate is None:
            self.coordinate = GPSCoordinate(0.0, 0.0)

    @property
    def created_datetime(self) -> datetime:
        """Return the created timestamp as a datetime instance."""

        return datetime.fromtimestamp(self.created_at)
@dataclass
class TrackPoint:
    """Single point in a GPS track."""
    coordinate: GPSCoordinate
    speed: Optional[float] = None  # m/s
    heading: Optional[float] = None  # degrees
@dataclass
class GPSTrack:
    """GPS track with multiple points."""
    id: str = ""
    name: str = ""
    description: str = ""
    points: List[TrackPoint] = None
    created_at: float = 0.0
    total_distance: float = 0.0
    duration: float = 0.0  # seconds
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.created_at == 0.0:
            self.created_at = datetime.now().timestamp()
        if self.points is None:
            self.points = []
    def add_point(self, point: TrackPoint):
        """Add a point to the track."""
        self.points.append(point)
        # Update statistics
        if len(self.points) > 1:
            last_point = self.points[-2]
            distance = last_point.coordinate.distance_to(point.coordinate)
            self.total_distance += distance
            # Calculate duration
            if point.coordinate.timestamp and last_point.coordinate.timestamp:
                time_diff = point.coordinate.timestamp - last_point.coordinate.timestamp
                self.duration += time_diff
    @property
    def average_speed(self) -> float:
        """Get average speed in m/s."""
        return self.total_distance / self.duration if self.duration > 0 else 0.0
    @property
    def start_coordinate(self) -> Optional[GPSCoordinate]:
        """Get starting coordinate."""
        return self.points[0].coordinate if self.points else None
    @property
    def end_coordinate(self) -> Optional[GPSCoordinate]:
        """Get ending coordinate."""
        return self.points[-1].coordinate if self.points else None
class BaseGPSProvider(QObject, LoggableMixin):
    """Base class for GPS providers with common lifecycle management."""
    position_updated = Signal(float, float, float, float)  # lat, lon, altitude, accuracy
    def __init__(self):
        QObject.__init__(self)
        LoggableMixin.__init__(self)
        self._active = False
    @property
    def is_active(self) -> bool:
        """Return whether the provider is currently emitting updates."""
        return self._active
    def start(self):
        """Start emitting GPS updates."""
        if not self._active:
            self._active = True
            self._on_start()
    def stop(self):
        """Stop emitting GPS updates."""
        if self._active:
            self._active = False
            self._on_stop()
    def _on_start(self):
        raise NotImplementedError
    def _on_stop(self):
        raise NotImplementedError
class RandomWalkGPSProvider(BaseGPSProvider):
    """Pseudo-random GPS provider useful for manual testing."""
    def __init__(self, interval_ms: int = 1000):
        super().__init__()
        self.current_position = GPSCoordinate(40.7128, -74.0060, 10.0, 5.0)  # New York City
        self.timer = QTimer()
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._simulate_movement)
    def _on_start(self):
        self.timer.start()
        self.log_info("Random walk GPS provider started")
    def _on_stop(self):
        self.timer.stop()
        self.log_info("Random walk GPS provider stopped")
    def _simulate_movement(self):
        """Simulate GPS movement for testing."""
        import random
        lat_delta = (random.random() - 0.5) * 0.0001  # ~10m variation
        lon_delta = (random.random() - 0.5) * 0.0001
        alt_delta = (random.random() - 0.5) * 2.0  # +/-1m altitude variation
        self.current_position.latitude += lat_delta
        self.current_position.longitude += lon_delta
        self.current_position.altitude += alt_delta
        self.current_position.accuracy = 3.0 + random.random() * 5.0  # 3-8m accuracy
        self.current_position.timestamp = datetime.now().timestamp()
        self.position_updated.emit(
            self.current_position.latitude,
            self.current_position.longitude,
            self.current_position.altitude,
            self.current_position.accuracy,
        )
class SimulatedGPSProvider(BaseGPSProvider):
    """GPS provider that replays deterministic samples for training scenarios."""
    def __init__(
        self,
        samples: Sequence[GPSCoordinate],
        interval_ms: Optional[int] = 1000,
        loop: bool = False,
    ):
        super().__init__()
        self._samples = list(samples)
        self._interval_ms = interval_ms
        self._loop = loop
        self._index = 0
        self._timer = None if interval_ms is None else QTimer()
        if self._timer is not None:
            self._timer.setInterval(interval_ms)
            self._timer.timeout.connect(self._emit_next)
    def _on_start(self):
        self._index = 0 if self._index >= len(self._samples) else self._index
        if self._timer is not None and self._samples:
            self._timer.start()
            self.log_info(
                "Simulated GPS provider started with %d samples", len(self._samples)
            )
        elif not self._samples:
            self.log_warning("Simulated GPS provider started without samples")
    def _on_stop(self):
        if self._timer is not None:
            self._timer.stop()
        if self._samples:
            self.log_info("Simulated GPS provider stopped after replay")
    def manual_step(self):
        """Emit the next sample immediately (useful for tests)."""
        if self.is_active:
            self._emit_next()
    def _emit_next(self):
        if not self._samples:
            return
        if self._index >= len(self._samples):
            if self._loop:
                self._index = 0
            else:
                self.stop()
                return
        coordinate = self._samples[self._index]
        self._index += 1
        coordinate.timestamp = datetime.now().timestamp()
        self.position_updated.emit(
            coordinate.latitude,
            coordinate.longitude,
            coordinate.altitude or 0.0,
            coordinate.accuracy or 0.0,
        )
        if not self._loop and self._index >= len(self._samples):
            # Stop automatically after the final sample has been emitted.
            self.stop()
    @staticmethod
    def from_feed(
        feed_source: Union[
            Sequence[GPSCoordinate],
            Sequence[TrackPoint],
            GPSTrack,
            Path,
            str,
            Sequence[Dict[str, Any]],
        ],
        interval_ms: Optional[int] = 1000,
        loop: bool = False,
    ) -> "SimulatedGPSProvider":
        """Create a simulated provider from a variety of sources."""
        coordinates = SimulatedGPSProvider._normalize_feed(feed_source)
        return SimulatedGPSProvider(coordinates, interval_ms=interval_ms, loop=loop)
    @staticmethod
    def _normalize_feed(
        feed_source: Union[
            Sequence[GPSCoordinate],
            Sequence[TrackPoint],
            GPSTrack,
            Path,
            str,
            Sequence[Dict[str, Any]],
        ]
    ) -> List[GPSCoordinate]:
        if isinstance(feed_source, GPSTrack):
            return [point.coordinate for point in feed_source.points if point.coordinate]
        if isinstance(feed_source, (str, Path)):
            path = Path(feed_source)
            data = json.loads(path.read_text())
            return SimulatedGPSProvider._normalize_feed(data)
        coordinates: List[GPSCoordinate] = []
        for entry in feed_source:
            if isinstance(entry, GPSCoordinate):
                coordinates.append(entry)
            elif isinstance(entry, TrackPoint):
                coordinates.append(entry.coordinate)
            elif isinstance(entry, dict):
                if 'latitude' in entry and 'longitude' in entry:
                    coordinates.append(GPSCoordinate(**entry))
                elif 'coordinate' in entry:
                    coordinates.append(GPSCoordinate(**entry['coordinate']))
                elif 'points' in entry:
                    for point_dict in entry['points']:
                        coord_dict = point_dict.get('coordinate')
                        if coord_dict:
                            coordinates.append(GPSCoordinate(**coord_dict))
                else:
                    raise TypeError(
                        "Unsupported dictionary structure in simulated GPS feed"
                    )
            else:
                raise TypeError(
                    "Unsupported feed entry type for simulated GPS provider: "
                    f"{type(entry)!r}"
                )
        return coordinates
class CompassWidget(QWidget):
    """Custom compass widget for navigation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.bearing = 0.0
        self.target_bearing = None
        self.distance_to_target = None
    def set_bearing(self, bearing: float):
        """Set current bearing."""
        self.bearing = bearing
        self.update()
    def set_target(self, bearing: float, distance: float):
        """Set target bearing and distance."""
        self.target_bearing = bearing
        self.distance_to_target = distance
        self.update()
    def clear_target(self):
        """Clear target."""
        self.target_bearing = None
        self.distance_to_target = None
        self.update()
    def paintEvent(self, event):
        """Paint the compass."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        center = rect.center()
        radius = min(rect.width(), rect.height()) // 2 - 20
        # Draw compass background
        painter.setPen(QPen(QColor("#3d5a8c"), 2))
        painter.setBrush(QBrush(QColor("#f8f9fa")))
        painter.drawEllipse(center, radius, radius)
        # Draw cardinal directions
        painter.setPen(QPen(QColor("#2c5aa0"), 2))
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        directions = [("N", 0), ("E", 90), ("S", 180), ("W", 270)]
        for direction, angle in directions:
            x = center.x() + radius * 0.8 * math.sin(math.radians(angle))
            y = center.y() - radius * 0.8 * math.cos(math.radians(angle))
            painter.drawText(int(x - 10), int(y + 5), direction)
        # Draw degree markings
        painter.setPen(QPen(QColor("#6c757d"), 1))
        for degree in range(0, 360, 10):
            angle_rad = math.radians(degree)
            inner_radius = radius * 0.9
            outer_radius = radius * 0.95
            x1 = center.x() + inner_radius * math.sin(angle_rad)
            y1 = center.y() - inner_radius * math.cos(angle_rad)
            x2 = center.x() + outer_radius * math.sin(angle_rad)
            y2 = center.y() - outer_radius * math.cos(angle_rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        # Draw current bearing needle
        painter.setPen(QPen(QColor("#dc3545"), 4))
        bearing_rad = math.radians(self.bearing)
        needle_length = radius * 0.7
        needle_x = center.x() + needle_length * math.sin(bearing_rad)
        needle_y = center.y() - needle_length * math.cos(bearing_rad)
        painter.drawLine(center, QPointF(needle_x, needle_y))
        # Draw target bearing if set
        if self.target_bearing is not None:
            painter.setPen(QPen(QColor("#28a745"), 3))
            target_rad = math.radians(self.target_bearing)
            target_length = radius * 0.6
            target_x = center.x() + target_length * math.sin(target_rad)
            target_y = center.y() - target_length * math.cos(target_rad)
            painter.drawLine(center, QPointF(target_x, target_y))
            # Draw distance text
            if self.distance_to_target is not None:
                painter.setPen(QPen(QColor("#2c5aa0"), 2))
                painter.setFont(QFont("Arial", 10))
                distance_text = f"{self.distance_to_target:.0f}m"
                painter.drawText(center.x() - 20, center.y() + radius + 15, distance_text)
class NavigationModule(BaseModule):
    """Main navigation and mapping module for Hunt Pro."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.gps_provider: Optional[BaseGPSProvider] = None
        self.waypoints: List[Waypoint] = []
        self.tracks: List[GPSTrack] = []
        self.current_position: Optional[GPSCoordinate] = None
        self.current_track: Optional[GPSTrack] = None
        self.is_tracking = False
        self.tile_cache = MapTileCache()
        self.points_of_interest: List[PointOfInterest] = []
        self.active_terrain_overlay: TerrainOverlayType = TerrainOverlayType.NONE
        self.show_elevation_contours = False
        # Data files
        self.data_dir = Path.home() / "HuntPro" / "navigation"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.waypoints_file = self.data_dir / "waypoints.json"
        self.tracks_file = self.data_dir / "tracks.json"
        self.pois_file = self.data_dir / "points_of_interest.json"
        self.setup_ui()
        self.load_data()
        # Default to pseudo-random GPS provider for manual operation
        self.set_gps_provider(RandomWalkGPSProvider())
        self.log_info("Navigation module initialized")
    def set_gps_provider(self, provider: BaseGPSProvider):
        """Swap the active GPS provider used by the module."""
        if provider is self.gps_provider:
            return
        if self.gps_provider is not None:
            try:
                self.gps_provider.position_updated.disconnect(self.on_position_updated)
            except (TypeError, RuntimeError):
                pass
            self.gps_provider.stop()
        self.gps_provider = provider
        if self.gps_provider is not None:
            self.gps_provider.position_updated.connect(self.on_position_updated)
            self.log_info(
                "GPS provider set to %s", self.gps_provider.__class__.__name__
            )
    def use_simulated_gps_feed(
        self,
        feed_source: Union[
            Sequence[GPSCoordinate],
            Sequence[TrackPoint],
            GPSTrack,
            Path,
            str,
            Sequence[Dict[str, Any]],
        ],
        interval_ms: Optional[int] = 1000,
        loop: bool = False,
    ) -> SimulatedGPSProvider:
        """Configure the module to use a simulated GPS feed.

        Parameters
        ----------
        feed_source:
            The source of simulated coordinates. This can be a list of
            ``GPSCoordinate`` objects, dictionaries containing coordinate
            fields, a ``GPSTrack`` instance, or a filesystem path to a JSON
            file with serialized coordinates.
        interval_ms:
            Milliseconds between emitted samples. When ``None`` the caller can
            advance the simulation manually via :meth:`SimulatedGPSProvider.manual_step`.
        loop:
            When ``True`` the feed restarts automatically when it reaches the
            final sample. This is handy for repeated training laps.
        """
        provider = SimulatedGPSProvider.from_feed(
            feed_source, interval_ms=interval_ms, loop=loop
        )
        self.set_gps_provider(provider)
        return provider
    def setup_ui(self):
        """Setup the navigation user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        # Create tabs
        self.tab_widget.addTab(self._create_navigation_tab(), "Navigation")
        self.tab_widget.addTab(self._create_waypoints_tab(), "Waypoints")
        self.tab_widget.addTab(self._create_tracking_tab(), "Tracking")
        self.tab_widget.addTab(self._create_map_tab(), "Map")
        # Apply styling
        self.apply_styling()
    def _create_navigation_tab(self) -> QWidget:
        """Create the main navigation tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # GPS status group
        gps_group = QGroupBox("GPS Status")
        gps_layout = QFormLayout()
        self.gps_status_label = QLabel("GPS Inactive")
        self.gps_status_label.setObjectName("statusLabel")
        gps_layout.addRow("Status:", self.gps_status_label)
        self.latitude_label = QLabel("--")
        gps_layout.addRow("Latitude:", self.latitude_label)
        self.longitude_label = QLabel("--")
        gps_layout.addRow("Longitude:", self.longitude_label)
        self.altitude_label = QLabel("--")
        gps_layout.addRow("Altitude:", self.altitude_label)
        self.accuracy_label = QLabel("--")
        gps_layout.addRow("Accuracy:", self.accuracy_label)
        # GPS control buttons
        gps_buttons_layout = QHBoxLayout()
        self.start_gps_btn = QPushButton("Start GPS")
        self.start_gps_btn.setObjectName("primary")
        self.start_gps_btn.clicked.connect(self.start_gps)
        gps_buttons_layout.addWidget(self.start_gps_btn)
        self.stop_gps_btn = QPushButton("Stop GPS")
        self.stop_gps_btn.setObjectName("secondary")
        self.stop_gps_btn.setEnabled(False)
        self.stop_gps_btn.clicked.connect(self.stop_gps)
        gps_buttons_layout.addWidget(self.stop_gps_btn)
        gps_layout.addRow(gps_buttons_layout)
        gps_group.setLayout(gps_layout)
        layout.addWidget(gps_group)
        # Compass widget
        compass_group = QGroupBox("Compass")
        compass_layout = QVBoxLayout()
        self.compass_widget = CompassWidget()
        compass_layout.addWidget(self.compass_widget)
        compass_group.setLayout(compass_layout)
        layout.addWidget(compass_group)
        # Navigation to waypoint
        nav_group = QGroupBox("Navigate to Waypoint")
        nav_layout = QFormLayout()
        self.target_waypoint_combo = QComboBox()
        self.target_waypoint_combo.currentIndexChanged.connect(self.on_target_waypoint_changed)
        nav_layout.addRow("Target:", self.target_waypoint_combo)
        self.distance_label = QLabel("--")
        nav_layout.addRow("Distance:", self.distance_label)
        self.bearing_label = QLabel("--")
        nav_layout.addRow("Bearing:", self.bearing_label)
        nav_group.setLayout(nav_layout)
        layout.addWidget(nav_group)
        layout.addStretch()
        return tab
    def _create_waypoints_tab(self) -> QWidget:
        """Create the waypoints management tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # Waypoint creation group
        create_group = QGroupBox("Create Waypoint")
        create_layout = QFormLayout()
        self.waypoint_name_edit = QLineEdit()
        self.waypoint_name_edit.setPlaceholderText("Enter waypoint name")
        create_layout.addRow("Name:", self.waypoint_name_edit)
        self.waypoint_type_combo = QComboBox()
        for waypoint_type in WaypointType:
            self.waypoint_type_combo.addItem(waypoint_type.value, waypoint_type)
        create_layout.addRow("Type:", self.waypoint_type_combo)
        self.waypoint_description_edit = QTextEdit()
        self.waypoint_description_edit.setMaximumHeight(60)
        self.waypoint_description_edit.setPlaceholderText("Optional description")
        create_layout.addRow("Description:", self.waypoint_description_edit)
        # Coordinate input
        coord_layout = QHBoxLayout()
        self.waypoint_lat_spin = QDoubleSpinBox()
        self.waypoint_lat_spin.setRange(-90, 90)
        self.waypoint_lat_spin.setDecimals(6)
        coord_layout.addWidget(QLabel("Lat:"))
        coord_layout.addWidget(self.waypoint_lat_spin)
        self.waypoint_lon_spin = QDoubleSpinBox()
        self.waypoint_lon_spin.setRange(-180, 180)
        self.waypoint_lon_spin.setDecimals(6)
        coord_layout.addWidget(QLabel("Lon:"))
        coord_layout.addWidget(self.waypoint_lon_spin)
        create_layout.addRow("Coordinates:", coord_layout)
        # Buttons
        waypoint_buttons_layout = QHBoxLayout()
        self.use_current_pos_btn = QPushButton("Use Current Position")
        self.use_current_pos_btn.clicked.connect(self.use_current_position)
        waypoint_buttons_layout.addWidget(self.use_current_pos_btn)
        self.create_waypoint_btn = QPushButton("Create Waypoint")
        self.create_waypoint_btn.setObjectName("primary")
        self.create_waypoint_btn.clicked.connect(self.create_waypoint)
        waypoint_buttons_layout.addWidget(self.create_waypoint_btn)
        create_layout.addRow(waypoint_buttons_layout)
        create_group.setLayout(create_layout)
        layout.addWidget(create_group)
        # Waypoints list
        waypoints_group = QGroupBox("Saved Waypoints")
        waypoints_layout = QVBoxLayout()
        self.waypoints_table = QTableWidget()
        headers = ["Name", "Type", "Coordinates", "Created", "Visited", "Actions"]
        self.waypoints_table.setColumnCount(len(headers))
        self.waypoints_table.setHorizontalHeaderLabels(headers)
        # Set column properties
        header = self.waypoints_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Coordinates
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Created
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Visited
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Actions
        waypoints_layout.addWidget(self.waypoints_table)
        waypoints_group.setLayout(waypoints_layout)
        layout.addWidget(waypoints_group)
        return tab
    def _create_tracking_tab(self) -> QWidget:
        """Create the GPS tracking tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # Track recording controls
        record_group = QGroupBox("Track Recording")
        record_layout = QFormLayout()
        self.track_name_edit = QLineEdit()
        self.track_name_edit.setPlaceholderText("Enter track name")
        record_layout.addRow("Track Name:", self.track_name_edit)
        # Recording buttons
        track_buttons_layout = QHBoxLayout()
        self.start_tracking_btn = QPushButton("Start Recording")
        self.start_tracking_btn.setObjectName("primary")
        self.start_tracking_btn.clicked.connect(self.start_tracking)
        track_buttons_layout.addWidget(self.start_tracking_btn)
        self.stop_tracking_btn = QPushButton("Stop Recording")
        self.stop_tracking_btn.setObjectName("secondary")
        self.stop_tracking_btn.setEnabled(False)
        self.stop_tracking_btn.clicked.connect(self.stop_tracking)
        track_buttons_layout.addWidget(self.stop_tracking_btn)
        record_layout.addRow(track_buttons_layout)
        # Current track info
        self.current_track_info_label = QLabel("No active track")
        record_layout.addRow("Status:", self.current_track_info_label)
        record_group.setLayout(record_layout)
        layout.addWidget(record_group)
        # Saved tracks
        tracks_group = QGroupBox("Saved Tracks")
        tracks_layout = QVBoxLayout()
        self.tracks_table = QTableWidget()
        track_headers = ["Name", "Distance", "Duration", "Points", "Created", "Actions"]
        self.tracks_table.setColumnCount(len(track_headers))
        self.tracks_table.setHorizontalHeaderLabels(track_headers)
        # Set column properties
        track_header = self.tracks_table.horizontalHeader()
        track_header.setSectionResizeMode(0, QHeaderView.Stretch)  # Name
        track_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Distance
        track_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Duration
        track_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Points
        track_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Created
        track_header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Actions
        tracks_layout.addWidget(self.tracks_table)
        tracks_group.setLayout(tracks_layout)
        layout.addWidget(tracks_group)
        return tab
    def _create_map_tab(self) -> QWidget:
        """Create the map display tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # Map controls
        controls_layout = QHBoxLayout()
        self.map_mode_combo = QComboBox()
        for mode in NavigationMode:
            self.map_mode_combo.addItem(mode.value, mode)
        controls_layout.addWidget(QLabel("Mode:"))
        controls_layout.addWidget(self.map_mode_combo)
        controls_layout.addStretch()
        self.center_on_position_btn = QPushButton("Center on Position")
        self.center_on_position_btn.clicked.connect(self.center_map_on_position)
        controls_layout.addWidget(self.center_on_position_btn)
        layout.addLayout(controls_layout)
        overlay_group = QGroupBox("Terrain Overlays")
        overlay_layout = QGridLayout()
        overlay_layout.addWidget(QLabel("Overlay:"), 0, 0)
        self.overlay_combo = QComboBox()
        for overlay in TerrainOverlayType:
            self.overlay_combo.addItem(overlay.value, overlay)
        self.overlay_combo.currentIndexChanged.connect(self.on_overlay_changed)
        overlay_layout.addWidget(self.overlay_combo, 0, 1)
        overlay_layout.addWidget(QLabel("Intensity:"), 1, 0)
        self.overlay_opacity_slider = QSlider(Qt.Horizontal)
        self.overlay_opacity_slider.setRange(10, 100)
        self.overlay_opacity_slider.setValue(70)
        self.overlay_opacity_slider.valueChanged.connect(lambda _: self.update_map_display())
        overlay_layout.addWidget(self.overlay_opacity_slider, 1, 1)
        self.show_contours_checkbox = QCheckBox("Show elevation contours")
        self.show_contours_checkbox.stateChanged.connect(self.on_contours_toggled)
        overlay_layout.addWidget(self.show_contours_checkbox, 2, 0, 1, 2)
        overlay_group.setLayout(overlay_layout)
        layout.addWidget(overlay_group)
        # Map view (placeholder - in a real implementation this would be a proper map widget)
        if _NAV_QT_CHARTS_AVAILABLE and QChartView is not None:
            self.map_chart_view = QChartView()
            self.map_chart_view.setMinimumHeight(400)
            layout.addWidget(self.map_chart_view)
        else:
            self.map_chart_view = None
            placeholder = QLabel(
                "QtCharts is not available. Map visualisation will be shown as textual summaries only."
            )
            placeholder.setWordWrap(True)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setMinimumHeight(200)
            layout.addWidget(placeholder)
        self.map_status_label = QLabel("Map tiles will be cached for offline use once loaded.")
        self.map_status_label.setObjectName("statusLabel")
        layout.addWidget(self.map_status_label)
        poi_group = QGroupBox("Points of Interest")
        poi_layout = QVBoxLayout()
        poi_form_layout = QFormLayout()
        self.poi_name_edit = QLineEdit()
        self.poi_name_edit.setPlaceholderText("Enter POI name")
        poi_form_layout.addRow("Name:", self.poi_name_edit)
        self.poi_category_combo = QComboBox()
        for category in POICategory:
            self.poi_category_combo.addItem(category.value, category)
        poi_form_layout.addRow("Category:", self.poi_category_combo)
        poi_coord_layout = QHBoxLayout()
        self.poi_lat_spin = QDoubleSpinBox()
        self.poi_lat_spin.setRange(-90, 90)
        self.poi_lat_spin.setDecimals(6)
        poi_coord_layout.addWidget(QLabel("Lat:"))
        poi_coord_layout.addWidget(self.poi_lat_spin)
        self.poi_lon_spin = QDoubleSpinBox()
        self.poi_lon_spin.setRange(-180, 180)
        self.poi_lon_spin.setDecimals(6)
        poi_coord_layout.addWidget(QLabel("Lon:"))
        poi_coord_layout.addWidget(self.poi_lon_spin)
        poi_form_layout.addRow("Coordinates:", poi_coord_layout)
        self.poi_notes_edit = QLineEdit()
        self.poi_notes_edit.setPlaceholderText("Optional notes or instructions")
        poi_form_layout.addRow("Notes:", self.poi_notes_edit)
        poi_buttons_layout = QHBoxLayout()
        self.poi_use_current_btn = QPushButton("Use Current Position")
        self.poi_use_current_btn.clicked.connect(self.use_current_position_for_poi)
        poi_buttons_layout.addWidget(self.poi_use_current_btn)
        self.add_poi_btn = QPushButton("Add Point of Interest")
        self.add_poi_btn.setObjectName("primary")
        self.add_poi_btn.clicked.connect(self.add_point_of_interest)
        poi_buttons_layout.addWidget(self.add_poi_btn)
        poi_form_layout.addRow(poi_buttons_layout)
        poi_layout.addLayout(poi_form_layout)
        self.poi_table = QTableWidget()
        poi_headers = ["Name", "Category", "Coordinates", "Created", "Notes"]
        self.poi_table.setColumnCount(len(poi_headers))
        self.poi_table.setHorizontalHeaderLabels(poi_headers)
        poi_header = self.poi_table.horizontalHeader()
        poi_header.setSectionResizeMode(0, QHeaderView.Stretch)
        poi_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        poi_header.setSectionResizeMode(2, QHeaderView.Stretch)
        poi_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        poi_header.setSectionResizeMode(4, QHeaderView.Stretch)
        poi_layout.addWidget(self.poi_table)
        poi_group.setLayout(poi_layout)
        layout.addWidget(poi_group)
        return tab
    def apply_styling(self):
        """Apply styling to the navigation module."""
        style = """
        QGroupBox {
            font-size: 14px;
            font-weight: bold;
            margin-top: 15px;
            padding-top: 8px;
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
            font-size: 14px;
            font-weight: bold;
            padding: 10px;
            min-height: 35px;
        }
        QPushButton#primary:hover {
            background-color: #3d6bb0;
        }
        QPushButton#secondary {
            background-color: #6c757d;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            padding: 10px;
            min-height: 35px;
        }
        QPushButton#secondary:hover {
            background-color: #5a6268;
        }
        QLabel#statusLabel {
            font-weight: bold;
            padding: 5px;
            border-radius: 4px;
        }
        QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
            min-height: 35px;
            font-size: 14px;
        }
        QTableWidget {
            gridline-color: #dee2e6;
            background-color: white;
            alternate-background-color: #f8f9fa;
        }
        QHeaderView::section {
            background-color: #e9ecef;
            padding: 8px;
            border: none;
            font-weight: bold;
        }
        """
        self.setStyleSheet(style)
    def start_gps(self):
        """Start GPS tracking."""
        if self.gps_provider is None:
            self.status_message.emit("No GPS provider configured")
            self.log_warning("Attempted to start GPS without provider")
            return
        self.gps_provider.start()
        self.start_gps_btn.setEnabled(False)
        self.stop_gps_btn.setEnabled(True)
        self.gps_status_label.setText("GPS Active")
        self.gps_status_label.setStyleSheet("background-color: #d4edda; color: #155724;")
        self.status_message.emit("GPS tracking started")
        self.log_user_action("gps_started")
    def stop_gps(self):
        """Stop GPS tracking."""
        if self.gps_provider is None:
            return
        self.gps_provider.stop()
        self.start_gps_btn.setEnabled(True)
        self.stop_gps_btn.setEnabled(False)
        self.gps_status_label.setText("GPS Inactive")
        self.gps_status_label.setStyleSheet("background-color: #f8d7da; color: #721c24;")
        self.status_message.emit("GPS tracking stopped")
        self.log_user_action("gps_stopped")
    def on_position_updated(self, latitude: float, longitude: float, altitude: float, accuracy: float):
        """Handle GPS position updates."""
        self.current_position = GPSCoordinate(latitude, longitude, altitude, accuracy)
        # Update UI
        self.latitude_label.setText(f"{latitude:.6f} deg ({self.current_position.latitude_dms})")
        self.longitude_label.setText(f"{longitude:.6f} deg ({self.current_position.longitude_dms})")
        self.altitude_label.setText(f"{altitude:.1f} m")
        self.accuracy_label.setText(f"+/-{accuracy:.1f} m")
        # Update compass bearing (simulated)
        import random
        bearing = (bearing + random.randint(-5, 5)) % 360 if 'bearing' in locals() else random.randint(0, 360)
        self.compass_widget.set_bearing(bearing)
        # Update navigation if target is set
        self.update_navigation()
        # Add to current track if recording
        if self.is_tracking and self.current_track:
            track_point = TrackPoint(coordinate=self.current_position)
            self.current_track.add_point(track_point)
            self.update_track_info()
        # Log GPS event
        self.log_gps_event("position_update", latitude, longitude, accuracy)
    def update_navigation(self):
        """Update navigation information to target waypoint."""
        current_index = self.target_waypoint_combo.currentIndex()
        if current_index >= 0 and self.current_position:
            waypoint = self.waypoints[current_index]
            distance = self.current_position.distance_to(waypoint.coordinate)
            bearing = self.current_position.bearing_to(waypoint.coordinate)
            self.distance_label.setText(f"{distance:.0f} m")
            self.bearing_label.setText(f"{bearing:.0f} deg")
            # Update compass
            self.compass_widget.set_target(bearing, distance)
    def on_target_waypoint_changed(self):
        """Handle target waypoint selection change."""
        if self.current_position:
            self.update_navigation()
        else:
            self.distance_label.setText("--")
            self.bearing_label.setText("--")
            self.compass_widget.clear_target()
    def use_current_position(self):
        """Use current GPS position for waypoint creation."""
        if self.current_position:
            self.waypoint_lat_spin.setValue(self.current_position.latitude)
            self.waypoint_lon_spin.setValue(self.current_position.longitude)
        else:
            QMessageBox.information(self, "No Position", "No current GPS position available. Start GPS first.")
    def create_waypoint(self):
        """Create a new waypoint."""
        try:
            name = self.waypoint_name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "Missing Name", "Please enter a waypoint name.")
                return
            waypoint = Waypoint(
                name=name,
                description=self.waypoint_description_edit.toPlainText(),
                waypoint_type=self.waypoint_type_combo.currentData(),
                coordinate=GPSCoordinate(
                    self.waypoint_lat_spin.value(),
                    self.waypoint_lon_spin.value()
                )
            )
            self.waypoints.append(waypoint)
            self.save_waypoints()
            self.update_waypoints_display()
            self.update_waypoint_combo()
            # Clear form
            self.waypoint_name_edit.clear()
            self.waypoint_description_edit.clear()
            self.waypoint_lat_spin.setValue(0)
            self.waypoint_lon_spin.setValue(0)
            self.status_message.emit(f"Created waypoint: {name}")
            self.log_field_event("waypoint_created", 
                               waypoint_name=name,
                               waypoint_type=waypoint.waypoint_type.value,
                               latitude=waypoint.coordinate.latitude,
                               longitude=waypoint.coordinate.longitude)
        except Exception as e:
            self.log_error("Failed to create waypoint", exception=e)
            self.error_occurred.emit("Waypoint Error", f"Failed to create waypoint: {str(e)}")
    def start_tracking(self):
        """Start GPS track recording."""
        try:
            name = self.track_name_edit.text().strip()
            if not name:
                name = f"Track_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.current_track = GPSTrack(name=name)
            self.is_tracking = True
            self.start_tracking_btn.setEnabled(False)
            self.stop_tracking_btn.setEnabled(True)
            self.current_track_info_label.setText(f"Recording: {name}")
            self.current_track_info_label.setStyleSheet("color: #155724; font-weight: bold;")
            self.status_message.emit(f"Started recording track: {name}")
            self.log_user_action("track_recording_started", {"track_name": name})
        except Exception as e:
            self.log_error("Failed to start tracking", exception=e)
            self.error_occurred.emit("Tracking Error", f"Failed to start tracking: {str(e)}")
    def stop_tracking(self):
        """Stop GPS track recording."""
        try:
            if self.current_track and self.is_tracking:
                self.tracks.append(self.current_track)
                self.save_tracks()
                self.update_tracks_display()
                track_name = self.current_track.name
                total_distance = self.current_track.total_distance
                self.current_track = None
                self.is_tracking = False
                self.start_tracking_btn.setEnabled(True)
                self.stop_tracking_btn.setEnabled(False)
                self.current_track_info_label.setText("No active track")
                self.current_track_info_label.setStyleSheet("")
                # Clear track name
                self.track_name_edit.clear()
                self.status_message.emit(f"Saved track: {track_name} ({total_distance:.0f}m)")
                self.log_user_action("track_recording_stopped", {
                    "track_name": track_name,
                    "distance": total_distance,
                    "points": len(self.current_track.points) if self.current_track else 0
                })
        except Exception as e:
            self.log_error("Failed to stop tracking", exception=e)
            self.error_occurred.emit("Tracking Error", f"Failed to stop tracking: {str(e)}")
    def update_track_info(self):
        """Update current track information."""
        if self.current_track and self.is_tracking:
            info = f"Recording: {self.current_track.name} - {self.current_track.total_distance:.0f}m, {len(self.current_track.points)} points"
            self.current_track_info_label.setText(info)
    def update_waypoints_display(self):
        """Update the waypoints table display."""
        self.waypoints_table.setRowCount(len(self.waypoints))
        for row, waypoint in enumerate(self.waypoints):
            items = [
                QTableWidgetItem(waypoint.name),
                QTableWidgetItem(waypoint.waypoint_type.value),
                QTableWidgetItem(f"{waypoint.coordinate.latitude:.6f}, {waypoint.coordinate.longitude:.6f}"),
                QTableWidgetItem(waypoint.created_datetime.strftime("%Y-%m-%d %H:%M")),
                QTableWidgetItem("Yes" if waypoint.visited else "No"),
                QTableWidgetItem("Actions")  # Placeholder for action buttons
            ]
            for col, item in enumerate(items):
                if col < 5:  # Don't set alignment for actions column
                    item.setTextAlignment(Qt.AlignCenter if col in [1, 3, 4] else Qt.AlignLeft)
                self.waypoints_table.setItem(row, col, item)
    def update_tracks_display(self):
        """Update the tracks table display."""
        self.tracks_table.setRowCount(len(self.tracks))
        for row, track in enumerate(self.tracks):
            duration_str = f"{track.duration/3600:.1f}h" if track.duration > 3600 else f"{track.duration/60:.1f}m"
            items = [
                QTableWidgetItem(track.name),
                QTableWidgetItem(f"{track.total_distance:.0f} m"),
                QTableWidgetItem(duration_str),
                QTableWidgetItem(str(len(track.points))),
                QTableWidgetItem(datetime.fromtimestamp(track.created_at).strftime("%Y-%m-%d %H:%M")),
                QTableWidgetItem("Actions")  # Placeholder for action buttons
            ]
            for col, item in enumerate(items):
                if col < 5:  # Don't set alignment for actions column
                    item.setTextAlignment(Qt.AlignCenter)
                self.tracks_table.setItem(row, col, item)
    def update_poi_table(self):
        """Render the points-of-interest table."""

        self.poi_table.setRowCount(len(self.points_of_interest))
        for row, poi in enumerate(self.points_of_interest):
            items = [
                QTableWidgetItem(poi.name),
                QTableWidgetItem(poi.category.value),
                QTableWidgetItem(f"{poi.coordinate.latitude:.6f}, {poi.coordinate.longitude:.6f}"),
                QTableWidgetItem(poi.created_datetime.strftime("%Y-%m-%d %H:%M")),
                QTableWidgetItem(poi.notes or "--"),
            ]
            for col, item in enumerate(items):
                if col in (1, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                self.poi_table.setItem(row, col, item)
    def update_waypoint_combo(self):
        """Update the target waypoint combo box."""
        self.target_waypoint_combo.clear()
        for waypoint in self.waypoints:
            self.target_waypoint_combo.addItem(f"{waypoint.name} ({waypoint.waypoint_type.value})", waypoint)
    def on_overlay_changed(self):
        """Handle terrain overlay selection changes."""

        overlay = self.overlay_combo.currentData()
        if isinstance(overlay, TerrainOverlayType):
            self.active_terrain_overlay = overlay
        else:
            self.active_terrain_overlay = TerrainOverlayType.NONE
        self.update_map_display()
    def on_contours_toggled(self, state: int):
        """Toggle elevation contour visibility."""

        self.show_elevation_contours = state == Qt.Checked
        self.update_map_display()
    def use_current_position_for_poi(self):
        """Populate POI fields using the current GPS position."""

        if not self.current_position:
            QMessageBox.information(self, "No Position", "No current GPS position available.")
            return
        self.poi_lat_spin.setValue(self.current_position.latitude)
        self.poi_lon_spin.setValue(self.current_position.longitude)
    def add_point_of_interest(self):
        """Create a new point-of-interest entry."""

        try:
            name = self.poi_name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "Missing Information", "Please provide a name for the point of interest.")
                return
            category = self.poi_category_combo.currentData()
            if not isinstance(category, POICategory):
                category = POICategory.OTHER
            coordinate = GPSCoordinate(
                latitude=self.poi_lat_spin.value(),
                longitude=self.poi_lon_spin.value(),
            )
            poi = PointOfInterest(
                name=name,
                category=category,
                coordinate=coordinate,
                notes=self.poi_notes_edit.text().strip(),
            )
            self.points_of_interest.append(poi)
            self.save_points_of_interest()
            self.update_poi_table()
            self.update_map_display()
            self.poi_name_edit.clear()
            self.poi_notes_edit.clear()
            self.status_message.emit(f"Added point of interest: {name}")
            self.log_user_action("poi_added", {"poi_name": name, "category": category.value})
        except Exception as e:
            self.log_error("Failed to add point of interest", exception=e)
            self.error_occurred.emit("POI Error", f"Failed to add point of interest: {str(e)}")
    def center_map_on_position(self):
        """Center map on current position and fetch a tile."""
        if not self.current_position:
            QMessageBox.information(self, "No Position", "No current GPS position available.")
            return
        zoom = 14
        mode_data = self.map_mode_combo.currentData()
        mode_key = mode_data.name if isinstance(mode_data, Enum) else str(mode_data)
        tile_x, tile_y = self.tile_cache.coordinate_to_tile(
            self.current_position.latitude,
            self.current_position.longitude,
            zoom,
        )
        tile = self.tile_cache.get_tile(zoom, tile_x, tile_y, mode_key)
        self.update_map_display(tile)
        self.status_message.emit("Map centered on current position")

    def update_map_display(self, tile: Optional[CachedTile] = None):
        """Update the map display with waypoints, overlays, tracks, and cached tiles."""

        if not _NAV_QT_CHARTS_AVAILABLE or QChart is None or QScatterSeries is None:
            if tile:
                status_messages = {
                    TileSource.NETWORK: "Live map tile downloaded and cached for offline use.",
                    TileSource.CACHE: "Loaded cached map tile for offline navigation.",
                    TileSource.FALLBACK: "Offline placeholder map tile shown (network unavailable).",
                }
                self.map_status_label.setText(status_messages[tile.source])
            else:
                self.map_status_label.setText(
                    "Map overlay unavailable without QtCharts. Waypoints and tracks remain accessible via tables."
                )
            return

        try:
            chart = QChart()
            chart.setTitle("Navigation Map")
            # Create scatter series for waypoints
            waypoint_series = QScatterSeries()
            waypoint_series.setName("Waypoints")
            waypoint_series.setMarkerSize(10)
            waypoint_series.setColor(QColor("#2c5aa0"))
            for waypoint in self.waypoints:
                waypoint_series.append(waypoint.coordinate.longitude, waypoint.coordinate.latitude)
            chart.addSeries(waypoint_series)
            # Add current position if available
            if self.current_position:
                position_series = QScatterSeries()
                position_series.setName("Current Position")
                position_series.setMarkerSize(15)
                position_series.setColor(QColor("#dc3545"))
                position_series.append(self.current_position.longitude, self.current_position.latitude)
                chart.addSeries(position_series)
            # Add points of interest grouped by category for unique styling
            if self.points_of_interest:
                poi_series_map: Dict[POICategory, QScatterSeries] = {}
                for poi in self.points_of_interest:
                    series = poi_series_map.get(poi.category)
                    if not series:
                        series = QScatterSeries()
                        series.setName(f"POI - {poi.category.value}")
                        series.setMarkerSize(12)
                        color = self._category_color(poi.category)
                        color.setAlpha(220)
                        series.setColor(color)
                        poi_series_map[poi.category] = series
                        chart.addSeries(series)
                    series.append(poi.coordinate.longitude, poi.coordinate.latitude)
            chart.createDefaultAxes()
            x_axis = chart.axes(Qt.Horizontal)[0]
            y_axis = chart.axes(Qt.Vertical)[0]
            x_axis.setTitleText("Longitude")
            y_axis.setTitleText("Latitude")
            # Attach all series to axes (required after createDefaultAxes)
            for series in chart.series():
                series.attachAxis(x_axis)
                series.attachAxis(y_axis)
            # Render requested terrain overlay
            center = self.current_position or (self.waypoints[0].coordinate if self.waypoints else None)
            if center:
                for overlay_series in self._create_overlay_series(center):
                    chart.addSeries(overlay_series)
                    overlay_series.attachAxis(x_axis)
                    overlay_series.attachAxis(y_axis)
                if self.show_elevation_contours:
                    for contour_series in self._generate_elevation_contours(center):
                        chart.addSeries(contour_series)
                        contour_series.attachAxis(x_axis)
                        contour_series.attachAxis(y_axis)
            if tile:
                pixmap = QPixmap(str(tile.path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(512, 512, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    chart.setBackgroundBrush(QBrush(scaled))
                status_messages = {
                    TileSource.NETWORK: "Live map tile downloaded and cached for offline use.",
                    TileSource.CACHE: "Loaded cached map tile for offline navigation.",
                    TileSource.FALLBACK: "Offline placeholder map tile shown (network unavailable).",
                }
                self.map_status_label.setText(status_messages[tile.source])
            else:
                self.map_status_label.setText("Map display updated.")
            if self.map_chart_view is not None:
                self.map_chart_view.setChart(chart)
        except Exception as e:
            self.log_error("Failed to update map display", exception=e)
    def _category_color(self, category: POICategory) -> QColor:
        """Return a distinctive color for a POI category."""

        palette = {
            POICategory.WATER: QColor("#1e88e5"),
            POICategory.FEED: QColor("#43a047"),
            POICategory.SIGN: QColor("#fdd835"),
            POICategory.ACCESS: QColor("#8e24aa"),
            POICategory.CAMP: QColor("#fb8c00"),
            POICategory.OTHER: QColor("#546e7a"),
        }
        return palette.get(category, QColor("#546e7a"))
    def _create_overlay_series(self, center: GPSCoordinate) -> List[QScatterSeries]:
        """Generate scatter series for the active terrain overlay."""

        if self.active_terrain_overlay == TerrainOverlayType.NONE:
            return []
        intensity = self.overlay_opacity_slider.value() if hasattr(self, "overlay_opacity_slider") else 70
        alpha = min(255, max(30, int(255 * (intensity / 100))))
        grid_offsets = [-0.02, -0.01, 0.0, 0.01, 0.02]
        buckets: Dict[str, QScatterSeries] = {}
        bucket_colors = {
            "Low": QColor("#81c784"),
            "Medium": QColor("#43a047"),
            "High": QColor("#1b5e20"),
        }
        if self.active_terrain_overlay == TerrainOverlayType.WATER:
            bucket_colors = {
                "Low": QColor("#bbdefb"),
                "Medium": QColor("#64b5f6"),
                "High": QColor("#1e88e5"),
            }
        elif self.active_terrain_overlay == TerrainOverlayType.SLOPE:
            bucket_colors = {
                "Low": QColor("#ffe082"),
                "Medium": QColor("#ffb300"),
                "High": QColor("#f57c00"),
            }
        for level, color in bucket_colors.items():
            color.setAlpha(alpha)
            series = QScatterSeries()
            series.setName(f"{self.active_terrain_overlay.value} - {level}")
            series.setMarkerSize(18 if level == "High" else 14 if level == "Medium" else 10)
            series.setColor(color)
            buckets[level] = series
        for lat_offset in grid_offsets:
            for lon_offset in grid_offsets:
                lat = center.latitude + lat_offset
                lon = center.longitude + lon_offset
                metric = self._overlay_metric(lat, lon)
                if metric < 0.33:
                    bucket = "Low"
                elif metric < 0.66:
                    bucket = "Medium"
                else:
                    bucket = "High"
                buckets[bucket].append(lon, lat)
        return list(buckets.values())
    def _overlay_metric(self, lat: float, lon: float) -> float:
        """Produce a deterministic metric for overlay classification."""

        if self.active_terrain_overlay == TerrainOverlayType.VEGETATION:
            return (math.sin(lat * 10) + 1) / 2
        if self.active_terrain_overlay == TerrainOverlayType.WATER:
            return (math.cos(lon * 10) + 1) / 2
        if self.active_terrain_overlay == TerrainOverlayType.SLOPE:
            return abs(math.sin((lat + lon) * 5))
        return 0.0
    def _generate_elevation_contours(self, center: GPSCoordinate) -> List[QLineSeries]:
        """Generate concentric contour lines around the provided center coordinate."""

        contours: List[QLineSeries] = []
        radii = [0.005, 0.01, 0.015]
        base_colors = [QColor("#795548"), QColor("#5d4037"), QColor("#3e2723")]
        for radius, color in zip(radii, base_colors):
            series = QLineSeries()
            series.setName(f"Elevation {int(radius * 1000)}m")
            pen = QPen(color, 2)
            pen.setStyle(Qt.DotLine)
            series.setPen(pen)
            for degree in range(0, 361, 5):
                rad = math.radians(degree)
                lat = center.latitude + radius * math.cos(rad)
                lon = center.longitude + radius * math.sin(rad)
                series.append(lon, lat)
            contours.append(series)
        return contours
    def save_waypoints(self):
        """Save waypoints to file."""
        try:
            data = []
            for waypoint in self.waypoints:
                waypoint_dict = asdict(waypoint)
                waypoint_dict['waypoint_type'] = waypoint.waypoint_type.value
                waypoint_dict['coordinate'] = asdict(waypoint.coordinate)
                data.append(waypoint_dict)
            with open(self.waypoints_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            self.log_debug(f"Saved {len(self.waypoints)} waypoints")
        except Exception as e:
            self.log_error("Failed to save waypoints", exception=e)
            raise
    def save_points_of_interest(self):
        """Persist points-of-interest to disk."""

        try:
            data = []
            for poi in self.points_of_interest:
                poi_dict = asdict(poi)
                poi_dict["category"] = poi.category.value
                poi_dict["coordinate"] = asdict(poi.coordinate)
                data.append(poi_dict)
            with open(self.pois_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            self.log_debug(f"Saved {len(self.points_of_interest)} points of interest")
        except Exception as e:
            self.log_error("Failed to save points of interest", exception=e)
            raise
    def load_waypoints(self):
        """Load waypoints from file."""
        try:
            if not self.waypoints_file.exists():
                return
            with open(self.waypoints_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.waypoints = []
            for waypoint_dict in data:
                try:
                    # Convert waypoint type back to enum
                    waypoint_dict['waypoint_type'] = WaypointType(waypoint_dict['waypoint_type'])
                    # Convert coordinate dict back to object
                    coord_dict = waypoint_dict['coordinate']
                    waypoint_dict['coordinate'] = GPSCoordinate(**coord_dict)
                    waypoint = Waypoint(**waypoint_dict)
                    self.waypoints.append(waypoint)
                except Exception as e:
                    self.log_warning(f"Failed to load waypoint: {e}", waypoint_data=waypoint_dict)
            self.log_info(f"Loaded {len(self.waypoints)} waypoints")
        except Exception as e:
            self.log_error("Failed to load waypoints", exception=e)
    def load_points_of_interest(self):
        """Load points-of-interest from disk."""

        try:
            if not self.pois_file.exists():
                return
            with open(self.pois_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.points_of_interest = []
            for poi_dict in data:
                try:
                    poi_dict["category"] = POICategory(poi_dict["category"])
                    coord_dict = poi_dict["coordinate"]
                    poi_dict["coordinate"] = GPSCoordinate(**coord_dict)
                    poi = PointOfInterest(**poi_dict)
                    self.points_of_interest.append(poi)
                except Exception as e:
                    self.log_warning(f"Failed to load point of interest: {e}", poi_data=poi_dict)
            self.log_info(f"Loaded {len(self.points_of_interest)} points of interest")
        except Exception as e:
            self.log_error("Failed to load points of interest", exception=e)
    def save_tracks(self):
        """Save tracks to file."""
        try:
            data = []
            for track in self.tracks:
                track_dict = asdict(track)
                # Convert track points
                track_dict['points'] = [
                    {
                        'coordinate': asdict(point.coordinate),
                        'speed': point.speed,
                        'heading': point.heading
                    }
                    for point in track.points
                ]
                data.append(track_dict)
            with open(self.tracks_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            self.log_debug(f"Saved {len(self.tracks)} tracks")
        except Exception as e:
            self.log_error("Failed to save tracks", exception=e)
            raise
    def load_tracks(self):
        """Load tracks from file."""
        try:
            if not self.tracks_file.exists():
                return
            with open(self.tracks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.tracks = []
            for track_dict in data:
                try:
                    # Convert track points back to objects
                    points = []
                    for point_dict in track_dict['points']:
                        coordinate = GPSCoordinate(**point_dict['coordinate'])
                        point = TrackPoint(
                            coordinate=coordinate,
                            speed=point_dict.get('speed'),
                            heading=point_dict.get('heading')
                        )
                        points.append(point)
                    track_dict['points'] = points
                    track = GPSTrack(**track_dict)
                    self.tracks.append(track)
                except Exception as e:
                    self.log_warning(f"Failed to load track: {e}", track_data=track_dict)
            self.log_info(f"Loaded {len(self.tracks)} tracks")
        except Exception as e:
            self.log_error("Failed to load tracks", exception=e)
    def load_data(self):
        """Load all navigation data."""
        self.load_waypoints()
        self.load_tracks()
        self.load_points_of_interest()
        # Update UI
        QTimer.singleShot(100, self.update_waypoints_display)
        QTimer.singleShot(100, self.update_tracks_display)
        QTimer.singleShot(100, self.update_waypoint_combo)
        QTimer.singleShot(100, self.update_poi_table)
        QTimer.singleShot(100, self.update_map_display)
    def export_gpx(self, file_path: str, include_waypoints: bool = True, include_tracks: bool = True):
        """Export data to GPX format."""
        try:
            gpx_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
            gpx_content += '<gpx version="1.1" creator="Hunt Pro">\n'
            # Export waypoints
            if include_waypoints and self.waypoints:
                for waypoint in self.waypoints:
                    gpx_content += f'  <wpt lat="{waypoint.coordinate.latitude}" lon="{waypoint.coordinate.longitude}">\n'
                    gpx_content += f'    <name>{waypoint.name}</name>\n'
                    gpx_content += f'    <desc>{waypoint.description}</desc>\n'
                    gpx_content += f'    <type>{waypoint.waypoint_type.value}</type>\n'
                    if waypoint.coordinate.altitude is not None:
                        gpx_content += f'    <ele>{waypoint.coordinate.altitude}</ele>\n'
                    gpx_content += '  </wpt>\n'
            # Export tracks
            if include_tracks and self.tracks:
                for track in self.tracks:
                    gpx_content += '  <trk>\n'
                    gpx_content += f'    <name>{track.name}</name>\n'
                    gpx_content += f'    <desc>{track.description}</desc>\n'
                    gpx_content += '    <trkseg>\n'
                    for point in track.points:
                        gpx_content += f'      <trkpt lat="{point.coordinate.latitude}" lon="{point.coordinate.longitude}">\n'
                        if point.coordinate.altitude is not None:
                            gpx_content += f'        <ele>{point.coordinate.altitude}</ele>\n'
                        if point.coordinate.timestamp:
                            timestamp = datetime.fromtimestamp(point.coordinate.timestamp).isoformat() + 'Z'
                            gpx_content += f'        <time>{timestamp}</time>\n'
                        gpx_content += '      </trkpt>\n'
                    gpx_content += '    </trkseg>\n'
                    gpx_content += '  </trk>\n'
            gpx_content += '</gpx>\n'
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(gpx_content)
            self.log_user_action("navigation_data_exported", {
                "format": "GPX",
                "file_path": file_path,
                "waypoints": len(self.waypoints) if include_waypoints else 0,
                "tracks": len(self.tracks) if include_tracks else 0
            })
        except Exception as e:
            self.log_error("Failed to export GPX", exception=e)
            raise
    def get_statistics_summary(self) -> Dict[str, Any]:
        """Get navigation statistics summary."""
        total_waypoints = len(self.waypoints)
        visited_waypoints = sum(1 for w in self.waypoints if w.visited)
        total_tracks = len(self.tracks)
        total_distance = sum(track.total_distance for track in self.tracks)
        total_duration = sum(track.duration for track in self.tracks)
        waypoint_types = {}
        for waypoint in self.waypoints:
            waypoint_type = waypoint.waypoint_type.value
            waypoint_types[waypoint_type] = waypoint_types.get(waypoint_type, 0) + 1
        return {
            'total_waypoints': total_waypoints,
            'visited_waypoints': visited_waypoints,
            'visit_percentage': (visited_waypoints / total_waypoints * 100) if total_waypoints > 0 else 0,
            'total_tracks': total_tracks,
            'total_distance_km': round(total_distance / 1000, 2),
            'total_duration_hours': round(total_duration / 3600, 2),
            'waypoint_types': waypoint_types,
            'average_track_distance': round(total_distance / total_tracks, 0) if total_tracks > 0 else 0,
            'gps_status': 'Active' if self.gps_provider.is_active else 'Inactive',
            'current_position': {
                'latitude': self.current_position.latitude if self.current_position else None,
                'longitude': self.current_position.longitude if self.current_position else None,
                'accuracy': self.current_position.accuracy if self.current_position else None
            } if self.current_position else None
        }
    def cleanup(self):
        """Clean up resources when module is closed."""
        # Stop GPS if active
        if self.gps_provider.is_active:
            self.stop_gps()
        # Stop tracking if active
        if self.is_tracking:
            self.stop_tracking()
        # Save data
        try:
            self.save_waypoints()
            self.save_tracks()
            self.save_points_of_interest()
        except Exception as e:
            self.log_error("Failed to save navigation data during cleanup", exception=e)
        super().cleanup()
        self.log_info("Navigation module cleaned up")
    def get_display_name(self) -> str:
        """Return the display name for this module."""
        return "Navigation & GPS"
    def get_description(self) -> str:
        """Return a description of this module's functionality."""
        return "GPS navigation, waypoint management, track recording, and mapping tools for hunting and outdoor activities."
# Utility functions for navigation and GPS
def degrees_to_radians(degrees: float) -> float:
    """Convert degrees to radians."""
    return degrees * math.pi / 180
def radians_to_degrees(radians: float) -> float:
    """Convert radians to degrees."""
    return radians * 180 / math.pi
def meters_to_feet(meters: float) -> float:
    """Convert meters to feet."""
    return meters * 3.28084
def feet_to_meters(feet: float) -> float:
    """Convert feet to meters."""
    return feet * 0.3048
def knots_to_mps(knots: float) -> float:
    """Convert knots to meters per second."""
    return knots * 0.514444
def mps_to_knots(mps: float) -> float:
    """Convert meters per second to knots."""
    return mps * 1.94384
def calculate_grid_reference(latitude: float, longitude: float, grid_system: str = "UTM") -> str:
    """Calculate grid reference for given coordinates."""
    # Simplified grid reference calculation
    # In a real implementation, this would use proper coordinate transformation libraries
    if grid_system == "UTM":
        # Very simplified UTM approximation
        zone = int((longitude + 180) / 6) + 1
        return f"UTM {zone}N {int(latitude * 111320)} {int(longitude * 111320)}"
    return f"Grid reference calculation not implemented for {grid_system}"
def bearing_to_compass(bearing: float) -> str:
    """Convert bearing degrees to compass direction."""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    # Normalize bearing to 0-360
    bearing = bearing % 360
    # Calculate index (16 directions, so 22.5 degrees each)
    index = int((bearing + 11.25) / 22.5) % 16
    return directions[index]
def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"
def calculate_sun_position(latitude: float, longitude: float, timestamp: Optional[float] = None) -> Tuple[float, float]:
    """Calculate sun azimuth and elevation for given location and time."""
    # Simplified sun position calculation
    # In a real implementation, this would use astronomical libraries
    if timestamp is None:
        timestamp = datetime.now().timestamp()
    dt = datetime.fromtimestamp(timestamp)
    # Very simplified calculation - just for demonstration
    hour_angle = (dt.hour - 12) * 15  # 15 degrees per hour
    # Mock values - replace with proper astronomical calculations
    azimuth = (hour_angle + 180) % 360
    elevation = 45 - abs(hour_angle) / 6  # Simplified elevation
    return azimuth, max(0, elevation)
def magnetic_declination(latitude: float, longitude: float, year: int = None) -> float:
    """Get magnetic declination for location and year."""
    # Simplified magnetic declination lookup
    # In a real implementation, this would use the World Magnetic Model
    if year is None:
        year = datetime.now().year
    # Very rough approximation for demonstration
    # Real implementation would use WMM coefficients
    declination = math.sin(math.radians(longitude / 10)) * 20
    return declination
