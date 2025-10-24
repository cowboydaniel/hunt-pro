"""
Navigation and Mapping Module for Hunt Pro.
GPS navigation, waypoint management, offline mapping, and location tracking
for hunting and outdoor activities.
"""
import json
import math
from pathlib import Path
from typing import List, Dict, Optional, Tuple, NamedTuple
from dataclasses import dataclass, asdict
from enum import Enum, auto
from datetime import datetime
import uuid
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
from PySide6.QtCharts import QChart, QChartView, QScatterSeries
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
        return f"{degrees}Â° {minutes}' {seconds:.2f}\" {direction}"
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
    symbol: str = "ðŸš©"
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
class MockGPSProvider(QObject, LoggableMixin):
    """Mock GPS provider for testing and simulation."""
    position_updated = Signal(float, float, float, float)  # lat, lon, altitude, accuracy
    def __init__(self):
        QObject.__init__(self)
        LoggableMixin.__init__(self)
        self.is_active = False
        self.current_position = GPSCoordinate(40.7128, -74.0060, 10.0, 5.0)  # New York City
        self.timer = QTimer()
        self.timer.timeout.connect(self._simulate_movement)
    def start(self):
        """Start GPS updates."""
        if not self.is_active:
            self.is_active = True
            self.timer.start(1000)  # Update every second
            self.log_info("Mock GPS provider started")
    def stop(self):
        """Stop GPS updates."""
        if self.is_active:
            self.is_active = False
            self.timer.stop()
            self.log_info("Mock GPS provider stopped")
    def _simulate_movement(self):
        """Simulate GPS movement for testing."""
        # Add small random variations to position
        import random
        lat_delta = (random.random() - 0.5) * 0.0001  # ~10m variation
        lon_delta = (random.random() - 0.5) * 0.0001
        alt_delta = (random.random() - 0.5) * 2.0  # Â±1m altitude variation
        self.current_position.latitude += lat_delta
        self.current_position.longitude += lon_delta
        self.current_position.altitude += alt_delta
        self.current_position.accuracy = 3.0 + random.random() * 5.0  # 3-8m accuracy
        self.current_position.timestamp = datetime.now().timestamp()
        self.position_updated.emit(
            self.current_position.latitude,
            self.current_position.longitude,
            self.current_position.altitude,
            self.current_position.accuracy
        )
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
        self.gps_provider = MockGPSProvider()
        self.waypoints: List[Waypoint] = []
        self.tracks: List[GPSTrack] = []
        self.current_position: Optional[GPSCoordinate] = None
        self.current_track: Optional[GPSTrack] = None
        self.is_tracking = False
        self.tile_cache = MapTileCache()
        # Data files
        self.data_dir = Path.home() / "HuntPro" / "navigation"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.waypoints_file = self.data_dir / "waypoints.json"
        self.tracks_file = self.data_dir / "tracks.json"
        self.setup_ui()
        self.load_data()
        # Connect GPS signals
        self.gps_provider.position_updated.connect(self.on_position_updated)
        self.log_info("Navigation module initialized")
    def setup_ui(self):
        """Setup the navigation user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        # Create tabs
        self.tab_widget.addTab(self._create_navigation_tab(), "ðŸ§­ Navigation")
        self.tab_widget.addTab(self._create_waypoints_tab(), "ðŸ“ Waypoints")
        self.tab_widget.addTab(self._create_tracking_tab(), "ðŸ“± Tracking")
        self.tab_widget.addTab(self._create_map_tab(), "ðŸ—ºï¸ Map")
        # Apply styling
        self.apply_styling()
    def _create_navigation_tab(self) -> QWidget:
        """Create the main navigation tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        # GPS status group
        gps_group = QGroupBox("ðŸ“¡ GPS Status")
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
        self.start_gps_btn = QPushButton("ðŸ›°ï¸ Start GPS")
        self.start_gps_btn.setObjectName("primary")
        self.start_gps_btn.clicked.connect(self.start_gps)
        gps_buttons_layout.addWidget(self.start_gps_btn)
        self.stop_gps_btn = QPushButton("â¹ï¸ Stop GPS")
        self.stop_gps_btn.setObjectName("secondary")
        self.stop_gps_btn.setEnabled(False)
        self.stop_gps_btn.clicked.connect(self.stop_gps)
        gps_buttons_layout.addWidget(self.stop_gps_btn)
        gps_layout.addRow(gps_buttons_layout)
        gps_group.setLayout(gps_layout)
        layout.addWidget(gps_group)
        # Compass widget
        compass_group = QGroupBox("ðŸ§­ Compass")
        compass_layout = QVBoxLayout()
        self.compass_widget = CompassWidget()
        compass_layout.addWidget(self.compass_widget)
        compass_group.setLayout(compass_layout)
        layout.addWidget(compass_group)
        # Navigation to waypoint
        nav_group = QGroupBox("ðŸŽ¯ Navigate to Waypoint")
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
        create_group = QGroupBox("âž• Create Waypoint")
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
        self.use_current_pos_btn = QPushButton("ðŸ“ Use Current Position")
        self.use_current_pos_btn.clicked.connect(self.use_current_position)
        waypoint_buttons_layout.addWidget(self.use_current_pos_btn)
        self.create_waypoint_btn = QPushButton("âœ… Create Waypoint")
        self.create_waypoint_btn.setObjectName("primary")
        self.create_waypoint_btn.clicked.connect(self.create_waypoint)
        waypoint_buttons_layout.addWidget(self.create_waypoint_btn)
        create_layout.addRow(waypoint_buttons_layout)
        create_group.setLayout(create_layout)
        layout.addWidget(create_group)
        # Waypoints list
        waypoints_group = QGroupBox("ðŸ“‹ Saved Waypoints")
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
        record_group = QGroupBox("ðŸŽ¥ Track Recording")
        record_layout = QFormLayout()
        self.track_name_edit = QLineEdit()
        self.track_name_edit.setPlaceholderText("Enter track name")
        record_layout.addRow("Track Name:", self.track_name_edit)
        # Recording buttons
        track_buttons_layout = QHBoxLayout()
        self.start_tracking_btn = QPushButton("â–¶ï¸ Start Recording")
        self.start_tracking_btn.setObjectName("primary")
        self.start_tracking_btn.clicked.connect(self.start_tracking)
        track_buttons_layout.addWidget(self.start_tracking_btn)
        self.stop_tracking_btn = QPushButton("â¹ï¸ Stop Recording")
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
        tracks_group = QGroupBox("ðŸ“Š Saved Tracks")
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
        self.center_on_position_btn = QPushButton("ðŸ“ Center on Position")
        self.center_on_position_btn.clicked.connect(self.center_map_on_position)
        controls_layout.addWidget(self.center_on_position_btn)
        layout.addLayout(controls_layout)
        # Map view (placeholder - in a real implementation this would be a proper map widget)
        self.map_chart_view = QChartView()
        self.map_chart_view.setMinimumHeight(400)
        layout.addWidget(self.map_chart_view)
        self.map_status_label = QLabel("Map tiles will be cached for offline use once loaded.")
        self.map_status_label.setObjectName("statusLabel")
        layout.addWidget(self.map_status_label)
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
        self.gps_provider.start()
        self.start_gps_btn.setEnabled(False)
        self.stop_gps_btn.setEnabled(True)
        self.gps_status_label.setText("GPS Active")
        self.gps_status_label.setStyleSheet("background-color: #d4edda; color: #155724;")
        self.status_message.emit("GPS tracking started")
        self.log_user_action("gps_started")
    def stop_gps(self):
        """Stop GPS tracking."""
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
        self.latitude_label.setText(f"{latitude:.6f}Â° ({self.current_position.latitude_dms})")
        self.longitude_label.setText(f"{longitude:.6f}Â° ({self.current_position.longitude_dms})")
        self.altitude_label.setText(f"{altitude:.1f} m")
        self.accuracy_label.setText(f"Â±{accuracy:.1f} m")
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
            self.bearing_label.setText(f"{bearing:.0f}Â°")
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
    def update_waypoint_combo(self):
        """Update the target waypoint combo box."""
        self.target_waypoint_combo.clear()
        for waypoint in self.waypoints:
            self.target_waypoint_combo.addItem(f"{waypoint.name} ({waypoint.waypoint_type.value})", waypoint)
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
        """Update the map display with waypoints, tracks, and cached tiles."""
        try:
            chart = QChart()
            chart.setTitle("Navigation Map")
            # Create scatter series for waypoints
            waypoint_series = QScatterSeries()
            waypoint_series.setName("Waypoints")
            waypoint_series.setMarkerSize(10)
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
            chart.createDefaultAxes()
            chart.axes(Qt.Horizontal)[0].setTitleText("Longitude")
            chart.axes(Qt.Vertical)[0].setTitleText("Latitude")
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
            self.map_chart_view.setChart(chart)
        except Exception as e:
            self.log_error("Failed to update map display", exception=e)
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
        # Update UI
        QTimer.singleShot(100, self.update_waypoints_display)
        QTimer.singleShot(100, self.update_tracks_display)
        QTimer.singleShot(100, self.update_waypoint_combo)
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
