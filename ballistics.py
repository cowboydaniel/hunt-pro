"""

Ballistics Calculator Module for Hunt Pro.



Advanced ballistics calculations with environmental corrections, trajectory modeling,

and comprehensive ammunition database for precision shooting applications.

"""



import math
import shutil

from typing import Any, Dict, Iterable, List, Optional, Tuple, NamedTuple

from dataclasses import dataclass, field

from enum import Enum

import json

from pathlib import Path

from datetime import datetime, timezone



from PySide6.QtWidgets import (

    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,

    QTabWidget, QPushButton, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,

    QComboBox, QTextEdit, QTableWidget, QTableWidgetItem, QGroupBox,

    QScrollArea, QFrame, QSlider, QCheckBox, QProgressBar, QSplitter,

    QHeaderView, QMessageBox

)

from PySide6.QtCore import (

    Qt, Signal, QTimer, QThread, QObject, QSettings

)

from PySide6.QtGui import QFont, QColor, QPainter, QPen

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis



from main import BaseModule

from logger import get_logger, LoggableMixin
from migrations import migrate_ballistic_profile_store, MigrationError


BALLISTIC_PROFILE_SCHEMA_VERSION = 1



class DragModel(Enum):

    """Drag model types for ballistics calculations."""

    G1 = "G1"

    G7 = "G7"

    CUSTOM = "Custom"



class WeatherCondition(Enum):

    """Weather conditions for environmental corrections."""

    STANDARD = "Standard"

    COLD = "Cold"

    HOT = "Hot"

    HUMID = "Humid"

    DRY = "Dry"

    CUSTOM = "Custom"



@dataclass

class EnvironmentalData:

    """Environmental conditions for ballistics calculations."""

    temperature: float = 15.0  # Celsius

    pressure: float = 1013.25  # hPa

    humidity: float = 50.0  # %

    altitude: float = 0.0  # meters above sea level

    wind_speed: float = 0.0  # m/s

    wind_direction: float = 0.0  # degrees (0 = headwind, 90 = right crosswind)


    def to_dict(self) -> Dict[str, float]:
        """Serialize the environmental data to a dictionary."""
        return {
            "temperature": float(self.temperature),
            "pressure": float(self.pressure),
            "humidity": float(self.humidity),
            "altitude": float(self.altitude),
            "wind_speed": float(self.wind_speed),
            "wind_direction": float(self.wind_direction),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentalData":
        """Create an :class:`EnvironmentalData` instance from a dictionary."""
        if data is None:
            raise ValueError("Environmental data payload is required")

        return cls(
            temperature=float(data.get("temperature", 15.0)),
            pressure=float(data.get("pressure", 1013.25)),
            humidity=float(data.get("humidity", 50.0)),
            altitude=float(data.get("altitude", 0.0)),
            wind_speed=float(data.get("wind_speed", 0.0)),
            wind_direction=float(data.get("wind_direction", 0.0)),
        )


    @property

    def air_density_ratio(self) -> float:

        """Calculate air density ratio compared to standard conditions."""

        # Standard conditions: 15Â°C, 1013.25 hPa, 0% humidity

        temp_kelvin = self.temperature + 273.15

        standard_temp = 288.15  # 15Â°C in Kelvin

        

        # Simplified air density calculation

        pressure_ratio = self.pressure / 1013.25

        temp_ratio = standard_temp / temp_kelvin

        humidity_factor = 1 - (0.0065 * self.humidity / 100)  # Simplified

        altitude_factor = math.exp(-self.altitude / 8400)  # Scale height approximation

        

        return pressure_ratio * temp_ratio * humidity_factor * altitude_factor



@dataclass

class Ammunition:

    """Ammunition data for ballistics calculations."""

    name: str = ""

    caliber: str = ""

    bullet_weight: float = 150.0  # grains

    muzzle_velocity: float = 800.0  # m/s

    ballistic_coefficient: float = 0.400

    drag_model: DragModel = DragModel.G1

    bullet_diameter: float = 7.62  # mm

    case_length: float = 51.0  # mm

    overall_length: float = 78.0  # mm

    

    def __post_init__(self):

        if not self.name:

            self.name = f"{self.caliber} {self.bullet_weight}gr"


    def to_dict(self) -> Dict[str, Any]:

        """Serialize the ammunition to a dictionary suitable for JSON storage."""

        return {

            "name": self.name,

            "caliber": self.caliber,

            "bullet_weight": float(self.bullet_weight),

            "muzzle_velocity": float(self.muzzle_velocity),

            "ballistic_coefficient": float(self.ballistic_coefficient),

            "drag_model": self.drag_model.value,

            "bullet_diameter": float(self.bullet_diameter),

            "case_length": float(self.case_length),

            "overall_length": float(self.overall_length),

        }


    @classmethod

    def from_dict(cls, data: Dict[str, Any]) -> "Ammunition":

        """Construct an :class:`Ammunition` instance from a dictionary."""

        if data is None:

            raise ValueError("Ammunition payload is required")


        drag_value = data.get("drag_model", DragModel.G1.value)

        try:

            drag_model = DragModel(drag_value)

        except ValueError as exc:

            raise ValueError(f"Unsupported drag model: {drag_value}") from exc


        return cls(

            name=data.get("name", ""),

            caliber=data.get("caliber", ""),

            bullet_weight=float(data.get("bullet_weight", 0.0)),

            muzzle_velocity=float(data.get("muzzle_velocity", 0.0)),

            ballistic_coefficient=float(data.get("ballistic_coefficient", 0.0)),

            drag_model=drag_model,

            bullet_diameter=float(data.get("bullet_diameter", 0.0)),

            case_length=float(data.get("case_length", 0.0)),

            overall_length=float(data.get("overall_length", 0.0)),

        )



class TrajectoryPoint(NamedTuple):

    """Single point on trajectory path."""

    distance: float  # meters

    drop: float  # meters (negative = below line of sight)

    velocity: float  # m/s

    energy: float  # joules

    time: float  # seconds

    windage: float  # meters (positive = right drift)



@dataclass

class BallisticsResult:

    """Complete ballistics calculation result."""

    ammunition: Ammunition

    environment: EnvironmentalData

    zero_distance: float

    trajectory: List[TrajectoryPoint]

    max_point_blank_range: float

    vital_zone_diameter: float

    

    @property

    def muzzle_energy(self) -> float:

        """Calculate muzzle energy in joules."""

        # Convert grains to kg and calculate kinetic energy

        mass_kg = self.ammunition.bullet_weight * 0.00006479891  # grains to kg

        return 0.5 * mass_kg * (self.ammunition.muzzle_velocity ** 2)


@dataclass

class BallisticProfile:

    """Serialized snapshot capturing a complete ballistic setup."""

    name: str

    ammunition: Ammunition

    environment: EnvironmentalData

    zero_distance: float

    max_range: float

    vital_zone_diameter: float

    notes: str = ""

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


    def to_dict(self) -> Dict[str, Any]:

        """Serialize the profile to a JSON-friendly dictionary."""

        return {

            "name": self.name,

            "ammunition": self.ammunition.to_dict(),

            "environment": self.environment.to_dict(),

            "zero_distance": float(self.zero_distance),

            "max_range": float(self.max_range),

            "vital_zone_diameter": float(self.vital_zone_diameter),

            "notes": self.notes,

            "created_at": self.created_at,

            "updated_at": self.updated_at,

        }


    @classmethod

    def from_dict(cls, data: Dict[str, Any]) -> "BallisticProfile":

        """Create a profile from a dictionary payload."""

        if data is None:

            raise ValueError("Ballistic profile payload is required")


        ammunition_payload = data.get("ammunition")

        environment_payload = data.get("environment")


        profile = cls(

            name=data.get("name", "Unnamed Profile"),

            ammunition=Ammunition.from_dict(ammunition_payload),

            environment=EnvironmentalData.from_dict(environment_payload),

            zero_distance=float(data.get("zero_distance", 100.0)),

            max_range=float(data.get("max_range", 800.0)),

            vital_zone_diameter=float(data.get("vital_zone_diameter", 0.2)),

            notes=data.get("notes", ""),

            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),

            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),

        )

        return profile


    def touch(self) -> None:

        """Update the modification timestamp."""

        self.updated_at = datetime.now(timezone.utc).isoformat()


@dataclass

class BallisticProfileImportReport:

    """Summary of an import operation for ballistic profiles."""

    imported: List[str]

    skipped: List[str]

    overwritten: List[str]


    @property

    def total_imported(self) -> int:

        """Return the total count of profiles applied to storage."""

        return len(self.imported) + len(self.overwritten)



class BallisticsCalculator(LoggableMixin):

    """Advanced ballistics calculator with environmental corrections."""

    

    def __init__(self):

        super().__init__()

        self.drag_tables = self._load_drag_tables()

        

    def _load_drag_tables(self) -> Dict[str, List[Tuple[float, float]]]:

        """Load standard drag tables for G1 and G7 models."""

        # Simplified drag tables - in a real implementation, these would be loaded from files

        g1_table = [

            (0.0, 0.2629), (0.05, 0.2558), (0.10, 0.2487), (0.15, 0.2413),

            (0.20, 0.2344), (0.25, 0.2278), (0.30, 0.2214), (0.35, 0.2155),

            (0.40, 0.2104), (0.45, 0.2061), (0.50, 0.2032), (0.55, 0.2020),

            (0.60, 0.2034), (0.65, 0.2165), (0.70, 0.2230), (0.75, 0.2313),

            (0.80, 0.2417), (0.85, 0.2546), (0.90, 0.2706), (0.95, 0.2901),

            (1.00, 0.3136), (1.05, 0.3415), (1.10, 0.3734), (1.15, 0.4084),

            (1.20, 0.4448), (1.25, 0.4805), (1.30, 0.5136), (1.35, 0.5427),

            (1.40, 0.5677), (1.45, 0.5883), (1.50, 0.6053), (1.55, 0.6191),

            (1.60, 0.6393), (1.65, 0.6518), (1.70, 0.6589), (1.75, 0.6621),

            (1.80, 0.6625), (1.85, 0.6607), (1.90, 0.6573), (1.95, 0.6528),

            (2.00, 0.6474), (2.05, 0.6413), (2.10, 0.6347), (2.15, 0.6280),

            (2.20, 0.6210), (2.25, 0.6141), (2.30, 0.6072), (2.35, 0.6003),

            (2.40, 0.5934), (2.45, 0.5867), (2.50, 0.5804), (2.60, 0.5680),

            (2.70, 0.5571), (2.80, 0.5479), (2.90, 0.5402), (3.00, 0.5337),

            (3.20, 0.5240), (3.40, 0.5178), (3.60, 0.5135), (3.80, 0.5101),

            (4.00, 0.5076), (4.20, 0.5055), (4.40, 0.5040), (4.60, 0.5030),

            (4.80, 0.5022), (5.00, 0.5016)

        ]

        

        g7_table = [

            (0.0, 0.1198), (0.05, 0.1197), (0.10, 0.1196), (0.15, 0.1194),

            (0.20, 0.1193), (0.25, 0.1194), (0.30, 0.1194), (0.35, 0.1194),

            (0.40, 0.1193), (0.45, 0.1193), (0.50, 0.1194), (0.55, 0.1193),

            (0.60, 0.1196), (0.65, 0.1197), (0.70, 0.1205), (0.75, 0.1230),

            (0.80, 0.1290), (0.85, 0.1380), (0.90, 0.1510), (0.95, 0.1705),

            (1.00, 0.2000), (1.05, 0.2380), (1.10, 0.2830), (1.15, 0.3315),

            (1.20, 0.3803), (1.25, 0.4262), (1.30, 0.4680), (1.35, 0.5050),

            (1.40, 0.5365), (1.45, 0.5620), (1.50, 0.5820), (1.55, 0.5980),

            (1.60, 0.6110), (1.65, 0.6210), (1.70, 0.6290), (1.75, 0.6350),

            (1.80, 0.6390), (1.85, 0.6420), (1.90, 0.6440), (1.95, 0.6450),

            (2.00, 0.6450), (2.05, 0.6447), (2.10, 0.6440), (2.15, 0.6430),

            (2.20, 0.6420), (2.25, 0.6410), (2.30, 0.6395), (2.35, 0.6380),

            (2.40, 0.6360), (2.45, 0.6340), (2.50, 0.6315), (2.60, 0.6265),

            (2.70, 0.6210), (2.80, 0.6155), (2.90, 0.6095), (3.00, 0.6035),

            (3.20, 0.5910), (3.40, 0.5790), (3.60, 0.5680), (3.80, 0.5570),

            (4.00, 0.5470), (4.20, 0.5375), (4.40, 0.5285), (4.60, 0.5200),

            (4.80, 0.5120), (5.00, 0.5040)

        ]

        

        return {"G1": g1_table, "G7": g7_table}

    

    def get_drag_coefficient(self, mach: float, drag_model: DragModel) -> float:

        """Get drag coefficient for given Mach number and drag model."""

        if drag_model == DragModel.CUSTOM:

            return 0.5  # Default value for custom

        

        table = self.drag_tables.get(drag_model.value, self.drag_tables["G1"])

        

        # Linear interpolation

        if mach <= table[0][0]:

            return table[0][1]

        if mach >= table[-1][0]:

            return table[-1][1]

        

        for i in range(len(table) - 1):

            if table[i][0] <= mach <= table[i + 1][0]:

                x0, y0 = table[i]

                x1, y1 = table[i + 1]

                return y0 + (y1 - y0) * (mach - x0) / (x1 - x0)

        

        return 0.5  # Fallback

    

    def calculate_trajectory(self, ammo: Ammunition, environment: EnvironmentalData,

                           zero_distance: float, max_range: float = 1000.0,

                           step_size: float = 25.0, vital_zone_diameter: float = 0.2) -> BallisticsResult:

        """Calculate complete trajectory with environmental corrections."""

        

        self.log_debug(f"Calculating trajectory for {ammo.name}")

        

        # Constants

        GRAVITY = 9.80665  # m/sÂ²

        

        # Convert units and setup initial conditions

        mass_kg = ammo.bullet_weight * 0.00006479891  # grains to kg

        diameter_m = ammo.bullet_diameter / 1000.0  # mm to m

        cross_section = math.pi * (diameter_m / 2) ** 2

        

        # Environmental corrections

        air_density = environment.air_density_ratio * 1.225  # kg/mÂ³ at sea level

        sound_speed = 331.3 * math.sqrt(1 + environment.temperature / 273.15)

        

        # Zero the rifle (find launch angle for zero at specified distance)

        zero_angle = self._find_zero_angle(ammo, environment, zero_distance)

        

        # Calculate trajectory points

        trajectory = []

        x = 0.0

        while x <= max_range:

            point = self._calculate_point(x, ammo, environment, zero_angle, 

                                        mass_kg, cross_section, air_density, sound_speed)

            trajectory.append(point)

            x += step_size

        

        # Calculate maximum point blank range

        mpbr = self._calculate_mpbr(trajectory, vital_zone_diameter)

        

        result = BallisticsResult(

            ammunition=ammo,

            environment=environment,

            zero_distance=zero_distance,

            trajectory=trajectory,

            max_point_blank_range=mpbr,

            vital_zone_diameter=vital_zone_diameter

        )

        

        self.log_ballistics_calculation("trajectory", {

            "ammunition": ammo.name,

            "zero_distance": zero_distance,

            "max_range": max_range,

            "environment": f"{environment.temperature}Â°C, {environment.pressure}hPa"

        }, {

            "muzzle_energy": result.muzzle_energy,

            "mpbr": mpbr,

            "trajectory_points": len(trajectory)

        })

        

        return result

    

    def _find_zero_angle(self, ammo: Ammunition, environment: EnvironmentalData, 

                        zero_distance: float) -> float:

        """Find launch angle needed to zero at specified distance."""

        # Simplified zero calculation - in practice this would use iteration

        # For now, using a basic approximation

        drop_at_zero = self._calculate_basic_drop(zero_distance, ammo.muzzle_velocity)

        return math.atan(drop_at_zero / zero_distance)

    

    def _calculate_basic_drop(self, distance: float, velocity: float) -> float:

        """Calculate basic bullet drop without air resistance."""

        time_of_flight = distance / velocity

        return 0.5 * 9.80665 * time_of_flight ** 2

    

    def _calculate_point(self, distance: float, ammo: Ammunition, environment: EnvironmentalData,

                        launch_angle: float, mass_kg: float, cross_section: float,

                        air_density: float, sound_speed: float) -> TrajectoryPoint:

        """Calculate trajectory point at given distance."""

        

        # Simplified ballistics calculation

        # In a real implementation, this would use numerical integration

        

        initial_velocity = ammo.muzzle_velocity

        time_of_flight = distance / (initial_velocity * math.cos(launch_angle))

        

        # Velocity degradation due to air resistance (simplified)

        velocity_loss_factor = 1.0 - (distance / 1000.0) * 0.3 * environment.air_density_ratio

        velocity = initial_velocity * max(0.3, velocity_loss_factor)

        

        # Drop calculation with launch angle compensation

        gravity_drop = 0.5 * 9.80665 * time_of_flight ** 2

        launch_compensation = distance * math.tan(launch_angle)

        drop = gravity_drop - launch_compensation

        

        # Energy calculation

        energy = 0.5 * mass_kg * velocity ** 2

        

        # Wind drift calculation

        wind_effect = self._calculate_wind_drift(distance, time_of_flight, environment)

        

        return TrajectoryPoint(

            distance=distance,

            drop=-drop,  # Negative for drop below line of sight

            velocity=velocity,

            energy=energy,

            time=time_of_flight,

            windage=wind_effect

        )

    

    def _calculate_wind_drift(self, distance: float, time_of_flight: float, 

                             environment: EnvironmentalData) -> float:

        """Calculate wind drift effect."""

        # Simplified wind drift calculation

        crosswind_component = environment.wind_speed * math.sin(math.radians(environment.wind_direction))

        

        # Wind drift is approximately proportional to time of flight squared

        drift = crosswind_component * time_of_flight * 0.5

        return drift

    

    def _calculate_mpbr(self, trajectory: List[TrajectoryPoint], vital_zone_diameter: float) -> float:

        """Calculate Maximum Point Blank Range."""

        vital_zone_radius = vital_zone_diameter / 2

        

        # Find the farthest point where trajectory stays within vital zone

        for point in reversed(trajectory):

            if abs(point.drop) <= vital_zone_radius:

                return point.distance

        

        return 0.0

    

    def calculate_come_ups(self, result: BallisticsResult, distances: List[float]) -> Dict[float, Dict[str, float]]:

        """Calculate scope adjustments (come-ups) for specific distances."""

        come_ups = {}

        

        for distance in distances:

            # Find closest trajectory point

            closest_point = min(result.trajectory, key=lambda p: abs(p.distance - distance))

            

            # Calculate adjustments (simplified)

            # In practice, this would account for scope height, click values, etc.

            elevation_moa = (closest_point.drop / distance) * 3437.75  # Convert to MOA

            windage_moa = (closest_point.windage / distance) * 3437.75

            

            come_ups[distance] = {

                'elevation_moa': round(elevation_moa, 2),

                'windage_moa': round(windage_moa, 2),

                'elevation_clicks': round(elevation_moa / 0.25),  # Assuming 1/4 MOA clicks

                'windage_clicks': round(windage_moa / 0.25),

                'velocity': round(closest_point.velocity, 1),

                'energy': round(closest_point.energy, 0),

                'time_of_flight': round(closest_point.time, 3)

            }

        

        return come_ups





class AmmunitionDatabase:

    """Database of common ammunition types."""

    

    def __init__(self):

        self.ammo_data = self._load_default_ammunition()

    

    def _load_default_ammunition(self) -> List[Ammunition]:

        """Load default ammunition database."""

        return [

            # .308 Winchester / 7.62x51mm NATO

            Ammunition("Federal Gold Medal Match", ".308 Win", 175.0, 792.0, 0.496, DragModel.G7, 7.82, 51.18),

            Ammunition("Winchester Super-X", ".308 Win", 150.0, 823.0, 0.411, DragModel.G1, 7.82, 51.18),

            Ammunition("Hornady Precision Hunter", ".308 Win", 178.0, 777.0, 0.530, DragModel.G7, 7.82, 51.18),

            

            # .30-06 Springfield

            Ammunition("Federal Power-Shok", ".30-06", 150.0, 853.0, 0.435, DragModel.G1, 7.82, 63.35),

            Ammunition("Remington Core-Lokt", ".30-06", 180.0, 792.0, 0.481, DragModel.G1, 7.82, 63.35),

            

            # .223 Remington / 5.56x45mm NATO

            Ammunition("Federal American Eagle", ".223 Rem", 55.0, 990.0, 0.243, DragModel.G1, 5.70, 44.70),

            Ammunition("Hornady V-MAX", ".223 Rem", 55.0, 1006.0, 0.255, DragModel.G1, 5.70, 44.70),

            Ammunition("Black Hills Match", ".223 Rem", 77.0, 838.0, 0.372, DragModel.G1, 5.70, 44.70),

            

            # .270 Winchester

            Ammunition("Winchester Power-Point", ".270 Win", 130.0, 960.0, 0.408, DragModel.G1, 6.98, 64.51),

            Ammunition("Federal Premium", ".270 Win", 150.0, 914.0, 0.465, DragModel.G1, 6.98, 64.51),

            

            # .300 Winchester Magnum

            Ammunition("Federal Premium", ".300 Win Mag", 180.0, 945.0, 0.507, DragModel.G1, 7.82, 67.00),

            Ammunition("Nosler AccuBond", ".300 Win Mag", 200.0, 914.0, 0.588, DragModel.G1, 7.82, 67.00),

            

            # 6.5 Creedmoor

            Ammunition("Hornady Precision Hunter", "6.5 Creedmoor", 143.0, 823.0, 0.623, DragModel.G7, 6.71, 48.77),

            Ammunition("Federal Gold Medal Match", "6.5 Creedmoor", 140.0, 838.0, 0.596, DragModel.G7, 6.71, 48.77),

        ]

    

    def get_by_caliber(self, caliber: str) -> List[Ammunition]:

        """Get ammunition by caliber."""

        return [ammo for ammo in self.ammo_data if ammo.caliber == caliber]

    

    def get_all_calibers(self) -> List[str]:

        """Get list of all available calibers."""

        return sorted(list(set(ammo.caliber for ammo in self.ammo_data)))

    

    def search(self, query: str) -> List[Ammunition]:

        """Search ammunition by name or caliber."""

        query_lower = query.lower()

        return [ammo for ammo in self.ammo_data 

                if query_lower in ammo.name.lower() or query_lower in ammo.caliber.lower()]

    

    def add_custom_ammunition(self, ammo: Ammunition):

        """Add custom ammunition to database."""

        self.ammo_data.append(ammo)



class BallisticProfileStorage(LoggableMixin):

    """Manage persistence for ballistic profiles with automated backups."""


    SCHEMA_VERSION = BALLISTIC_PROFILE_SCHEMA_VERSION


    def __init__(self, storage_dir: Optional[Path] = None, max_backups: int = 5):

        super().__init__()

        if storage_dir is None:

            storage_dir = Path.home() / "HuntPro" / "ballistics"

        self.storage_dir = Path(storage_dir)

        self.storage_file = self.storage_dir / "profiles.json"

        self.backup_dir = self.storage_dir / "backups"

        self.max_backups = max(1, int(max_backups))

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._apply_migrations()


    def _apply_migrations(self) -> None:

        try:

            outcome = migrate_ballistic_profile_store(

                self.storage_file,

                loader=BallisticProfile.from_dict,

                dumper=lambda profile: profile.to_dict(),

                target_version=self.SCHEMA_VERSION,

                backup_dir=self.backup_dir,

                logger=self._logger,

            )

        except MigrationError as exc:

            self.log_error("Failed to migrate ballistic profile store", exception=exc)

            raise

        if outcome:

            self.log_info(

                "Migrated ballistic profile store",

                category="DATA",

                previous_version=outcome.previous_version,

                new_version=outcome.new_version,

                backup=str(outcome.backup_path) if outcome.backup_path else None,

            )


    def load_profiles(self) -> Dict[str, BallisticProfile]:

        """Load all saved ballistic profiles from disk."""

        if not self.storage_file.exists():

            return {}


        try:

            with self.storage_file.open("r", encoding="utf-8") as handle:

                payload = json.load(handle)

        except json.JSONDecodeError as exc:

            self.log_warning("Failed to decode ballistic profile storage; preserving corrupted copy.", exception=exc)

            self._preserve_corrupted_store()

            return {}

        except OSError as exc:

            self.log_error("Unable to read ballistic profile storage", exception=exc)

            return {}


        profiles: Dict[str, BallisticProfile] = {}

        for entry in payload.get("profiles", []):

            try:

                profile = BallisticProfile.from_dict(entry)

            except Exception as exc:  # pragma: no cover - defensive logging

                self.log_warning("Skipping malformed ballistic profile entry", exception=exc)

                continue

            profiles[profile.name] = profile


        return profiles


    def save_profile(self, profile: BallisticProfile) -> None:

        """Persist a single profile and ensure a backup of the previous state."""

        profiles = self.load_profiles()

        profile.touch()

        profiles[profile.name] = profile

        self._write_profiles(profiles)

        self.log_info(

            "Saved ballistic profile",

            category="DATA",

            profile=profile.name,

        )


    def delete_profile(self, profile_name: str) -> bool:

        """Delete a profile by name. Returns ``True`` if it existed."""

        profiles = self.load_profiles()

        if profile_name not in profiles:

            return False

        del profiles[profile_name]

        self._write_profiles(profiles)

        self.log_info("Deleted ballistic profile", category="DATA", profile=profile_name)

        return True


    def export_profiles(self, destination: Path, profile_names: Optional[Iterable[str]] = None) -> List[str]:

        """Export selected profiles to a JSON file."""

        destination = Path(destination)

        destination.parent.mkdir(parents=True, exist_ok=True)

        profiles = self.load_profiles()

        if profile_names is not None:

            selection = []

            missing = []

            for name in profile_names:

                if name in profiles:

                    selection.append(profiles[name])

                else:

                    missing.append(name)

            if missing:

                raise KeyError(f"Unknown ballistic profiles requested for export: {', '.join(missing)}")

        else:

            selection = list(profiles.values())

        export_payload = {

            "version": 1,

            "exported_at": datetime.now(timezone.utc).isoformat(),

            "profiles": [profile.to_dict() for profile in selection],

        }

        with destination.open("w", encoding="utf-8") as handle:

            json.dump(export_payload, handle, indent=2, sort_keys=True)

        self.log_info(

            "Exported ballistic profiles",

            category="DATA",

            profile_count=len(selection),

            destination=str(destination),

        )

        return [profile.name for profile in selection]


    def import_profiles(self, source: Path, overwrite: bool = False) -> BallisticProfileImportReport:

        """Import profiles from a JSON export."""

        source = Path(source)

        with source.open("r", encoding="utf-8") as handle:

            payload = json.load(handle)

        existing = self.load_profiles()

        imported: List[str] = []

        skipped: List[str] = []

        overwritten: List[str] = []

        for entry in payload.get("profiles", []):

            profile = BallisticProfile.from_dict(entry)

            if profile.name in existing:

                if overwrite:

                    overwritten.append(profile.name)

                else:

                    skipped.append(profile.name)

                    continue

            else:

                imported.append(profile.name)

            profile.touch()

            existing[profile.name] = profile

        if imported or overwritten:

            self._write_profiles(existing)

        report = BallisticProfileImportReport(imported=imported, skipped=skipped, overwritten=overwritten)

        self.log_info(

            "Imported ballistic profiles",

            category="DATA",

            imported=report.total_imported,

            skipped=len(report.skipped),

            source=str(source),

        )

        return report


    def create_backup(self) -> Optional[Path]:

        """Create a manual backup of the current profile store."""

        return self._create_backup()


    def list_backups(self) -> List[Path]:

        """Return available backup files sorted by newest first."""

        backups = sorted(self.backup_dir.glob("profiles-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)

        return backups


    def _write_profiles(self, profiles: Dict[str, BallisticProfile]) -> None:

        payload = {

            "version": self.SCHEMA_VERSION,

            "updated_at": datetime.now(timezone.utc).isoformat(),

            "profiles": [profiles[name].to_dict() for name in sorted(profiles.keys())],

        }

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        if self.storage_file.exists():

            self._create_backup()

        with self.storage_file.open("w", encoding="utf-8") as handle:

            json.dump(payload, handle, indent=2, sort_keys=True)


    def _create_backup(self, suffix: str = "") -> Optional[Path]:

        if not self.storage_file.exists():

            return None

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        suffix_segment = f"-{suffix}" if suffix else ""

        backup_path = self.backup_dir / f"profiles{suffix_segment}-{timestamp}.json"

        try:

            shutil.copy2(self.storage_file, backup_path)

        except OSError as exc:

            self.log_warning("Failed to create ballistic profile backup", exception=exc)

            return None

        self._prune_backups()

        return backup_path


    def _prune_backups(self) -> None:

        backups = sorted(self.backup_dir.glob("profiles-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)

        for stale_backup in backups[self.max_backups:]:

            try:

                stale_backup.unlink()

            except OSError as exc:  # pragma: no cover - best effort cleanup

                self.log_warning("Failed to remove old ballistic profile backup", exception=exc)


    def _preserve_corrupted_store(self) -> None:

        if not self.storage_file.exists():

            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        corrupted_path = self.backup_dir / f"profiles-corrupted-{timestamp}.json"

        try:

            shutil.copy2(self.storage_file, corrupted_path)

        except OSError as exc:

            self.log_warning("Failed to preserve corrupted ballistic profile store", exception=exc)





class BallisticsModule(BaseModule):

    """Main ballistics calculator module for Hunt Pro."""

    

    def __init__(self, parent=None):

        super().__init__(parent)

        self.calculator = BallisticsCalculator()

        self.ammo_db = AmmunitionDatabase()

        self.profile_storage = BallisticProfileStorage()

        self.current_result: Optional[BallisticsResult] = None

        

        self.setup_ui()

        self.load_settings()

        

        self.log_info("Ballistics module initialized")

    

    def setup_ui(self):

        """Setup the ballistics calculator interface."""

        layout = QVBoxLayout(self)

        layout.setContentsMargins(10, 10, 10, 10)

        

        # Create main splitter

        splitter = QSplitter(Qt.Horizontal)

        layout.addWidget(splitter)

        

        # Left panel - inputs

        left_panel = self.create_input_panel()

        splitter.addWidget(left_panel)

        

        # Right panel - results

        right_panel = self.create_results_panel()

        splitter.addWidget(right_panel)

        

        # Set splitter proportions

        splitter.setStretchFactor(0, 1)

        splitter.setStretchFactor(1, 2)

        

        # Apply styling

        self.apply_styling()

    

    def create_input_panel(self) -> QWidget:

        """Create the input panel with ammunition and environmental settings."""

        panel = QWidget()

        layout = QVBoxLayout(panel)

        

        # Create scroll area

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        

        scroll_widget = QWidget()

        scroll_layout = QVBoxLayout(scroll_widget)

        

        # Ammunition selection group

        ammo_group = QGroupBox("ðŸŽ¯ Ammunition Selection")

        ammo_layout = QFormLayout()

        

        self.caliber_combo = QComboBox()

        self.caliber_combo.addItems(["Custom"] + self.ammo_db.get_all_calibers())

        self.caliber_combo.currentTextChanged.connect(self.on_caliber_changed)

        ammo_layout.addRow("Caliber:", self.caliber_combo)

        

        self.ammo_combo = QComboBox()

        self.ammo_combo.currentIndexChanged.connect(self.on_ammunition_changed)

        ammo_layout.addRow("Ammunition:", self.ammo_combo)

        

        ammo_group.setLayout(ammo_layout)

        scroll_layout.addWidget(ammo_group)

        

        # Custom ammunition group

        self.custom_ammo_group = QGroupBox("âš™ï¸ Custom Ammunition")

        custom_layout = QFormLayout()

        

        self.bullet_weight_spin = QDoubleSpinBox()

        self.bullet_weight_spin.setRange(20, 1000)

        self.bullet_weight_spin.setValue(150)

        self.bullet_weight_spin.setSuffix(" gr")

        custom_layout.addRow("Bullet Weight:", self.bullet_weight_spin)

        

        self.muzzle_velocity_spin = QDoubleSpinBox()

        self.muzzle_velocity_spin.setRange(200, 1500)

        self.muzzle_velocity_spin.setValue(800)

        self.muzzle_velocity_spin.setSuffix(" m/s")

        custom_layout.addRow("Muzzle Velocity:", self.muzzle_velocity_spin)

        

        self.ballistic_coefficient_spin = QDoubleSpinBox()

        self.ballistic_coefficient_spin.setRange(0.1, 1.0)

        self.ballistic_coefficient_spin.setValue(0.4)

        self.ballistic_coefficient_spin.setDecimals(3)

        custom_layout.addRow("Ballistic Coefficient:", self.ballistic_coefficient_spin)

        

        self.drag_model_combo = QComboBox()

        for model in DragModel:

            self.drag_model_combo.addItem(model.value, model)

        custom_layout.addRow("Drag Model:", self.drag_model_combo)

        

        self.custom_ammo_group.setLayout(custom_layout)

        scroll_layout.addWidget(self.custom_ammo_group)

        

        # Environmental conditions group

        env_group = QGroupBox("ðŸŒ¤ï¸ Environmental Conditions")

        env_layout = QFormLayout()

        

        self.temperature_spin = QSpinBox()

        self.temperature_spin.setRange(-40, 60)

        self.temperature_spin.setValue(15)

        self.temperature_spin.setSuffix("Â°C")

        env_layout.addRow("Temperature:", self.temperature_spin)

        

        self.pressure_spin = QDoubleSpinBox()

        self.pressure_spin.setRange(800, 1100)

        self.pressure_spin.setValue(1013.25)

        self.pressure_spin.setSuffix(" hPa")

        env_layout.addRow("Barometric Pressure:", self.pressure_spin)

        

        self.humidity_spin = QSpinBox()

        self.humidity_spin.setRange(0, 100)

        self.humidity_spin.setValue(50)

        self.humidity_spin.setSuffix("%")

        env_layout.addRow("Humidity:", self.humidity_spin)

        

        self.altitude_spin = QSpinBox()

        self.altitude_spin.setRange(0, 8000)

        self.altitude_spin.setValue(0)

        self.altitude_spin.setSuffix(" m")

        env_layout.addRow("Altitude:", self.altitude_spin)

        

        # Wind conditions

        wind_layout = QHBoxLayout()

        self.wind_speed_spin = QDoubleSpinBox()

        self.wind_speed_spin.setRange(0, 50)

        self.wind_speed_spin.setValue(0)

        self.wind_speed_spin.setSuffix(" m/s")

        wind_layout.addWidget(self.wind_speed_spin)

        

        self.wind_direction_spin = QSpinBox()

        self.wind_direction_spin.setRange(0, 360)

        self.wind_direction_spin.setValue(90)

        self.wind_direction_spin.setSuffix("Â°")

        wind_layout.addWidget(QLabel("@"))

        wind_layout.addWidget(self.wind_direction_spin)

        

        env_layout.addRow("Wind Speed:", wind_layout)

        

        env_group.setLayout(env_layout)

        scroll_layout.addWidget(env_group)

        

        # Calculation parameters group

        calc_group = QGroupBox("ðŸ“ Calculation Parameters")

        calc_layout = QFormLayout()

        

        self.zero_distance_spin = QSpinBox()

        self.zero_distance_spin.setRange(25, 500)

        self.zero_distance_spin.setValue(100)

        self.zero_distance_spin.setSuffix(" m")

        calc_layout.addRow("Zero Distance:", self.zero_distance_spin)

        

        self.max_range_spin = QSpinBox()

        self.max_range_spin.setRange(100, 2000)

        self.max_range_spin.setValue(800)

        self.max_range_spin.setSuffix(" m")

        calc_layout.addRow("Maximum Range:", self.max_range_spin)

        

        self.vital_zone_spin = QDoubleSpinBox()

        self.vital_zone_spin.setRange(0.1, 0.5)

        self.vital_zone_spin.setValue(0.2)

        self.vital_zone_spin.setSuffix(" m")

        self.vital_zone_spin.setDecimals(2)

        calc_layout.addRow("Vital Zone Diameter:", self.vital_zone_spin)

        

        calc_group.setLayout(calc_layout)

        scroll_layout.addWidget(calc_group)

        

        # Calculate button

        self.calculate_btn = QPushButton("ðŸ§® Calculate Trajectory")

        self.calculate_btn.setObjectName("primary")

        self.calculate_btn.setMinimumHeight(50)

        self.calculate_btn.clicked.connect(self.calculate_ballistics)

        scroll_layout.addWidget(self.calculate_btn)

        

        scroll_layout.addStretch()

        

        scroll.setWidget(scroll_widget)

        layout.addWidget(scroll)

        

        return panel

    

    def create_results_panel(self) -> QWidget:

        """Create the results panel with charts and tables."""

        panel = QWidget()

        layout = QVBoxLayout(panel)

        

        # Results tab widget

        self.results_tabs = QTabWidget()

        layout.addWidget(self.results_tabs)

        

        # Trajectory chart tab

        self.chart_view = QChartView()

        self.results_tabs.addTab(self.chart_view, "ðŸ“ˆ Trajectory Chart")

        

        # Data table tab

        self.create_data_table_tab()

        

        # Come-ups tab

        self.create_comeups_tab()

        

        # Summary tab

        self.create_summary_tab()

        

        return panel

    

    def create_data_table_tab(self):

        """Create trajectory data table tab."""

        tab = QWidget()

        layout = QVBoxLayout(tab)

        

        self.data_table = QTableWidget()

        headers = ["Distance (m)", "Drop (cm)", "Velocity (m/s)", "Energy (J)", "Time (s)", "Wind Drift (cm)"]

        self.data_table.setColumnCount(len(headers))

        self.data_table.setHorizontalHeaderLabels(headers)

        

        # Set column properties

        header = self.data_table.horizontalHeader()

        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        

        layout.addWidget(self.data_table)

        self.results_tabs.addTab(tab, "ðŸ“Š Data Table")

    

    def create_comeups_tab(self):

        """Create scope adjustments (come-ups) tab."""

        tab = QWidget()

        layout = QVBoxLayout(tab)

        

        # Distance selection

        distances_layout = QHBoxLayout()

        distances_layout.addWidget(QLabel("Calculate come-ups for distances:"))

        

        self.comeup_distances_edit = QLineEdit("100, 200, 300, 400, 500")

        self.comeup_distances_edit.setPlaceholderText("Enter distances separated by commas")

        distances_layout.addWidget(self.comeup_distances_edit)

        

        calc_comeups_btn = QPushButton("Calculate")

        calc_comeups_btn.clicked.connect(self.calculate_comeups)

        distances_layout.addWidget(calc_comeups_btn)

        

        layout.addLayout(distances_layout)

        

        # Come-ups table

        self.comeups_table = QTableWidget()

        comeup_headers = ["Distance (m)", "Elevation (MOA)", "Windage (MOA)", 

                         "Elev. Clicks", "Wind Clicks", "Velocity (m/s)", "Energy (J)", "Time (s)"]

        self.comeups_table.setColumnCount(len(comeup_headers))

        self.comeups_table.setHorizontalHeaderLabels(comeup_headers)

        

        header = self.comeups_table.horizontalHeader()

        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        

        layout.addWidget(self.comeups_table)

        self.results_tabs.addTab(tab, "ðŸŽ¯ Come-Ups")

    

    def create_summary_tab(self):

        """Create ballistics summary tab."""

        tab = QWidget()

        layout = QVBoxLayout(tab)

        

        self.summary_text = QTextEdit()

        self.summary_text.setReadOnly(True)

        self.summary_text.setFont(QFont("monospace", 10))

        

        layout.addWidget(self.summary_text)

        self.results_tabs.addTab(tab, "ðŸ“‹ Summary")

    

    def apply_styling(self):

        """Apply styling to the ballistics module."""

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

            font-size: 16px;

            font-weight: bold;

            padding: 15px;

        }

        

        QPushButton#primary:hover {

            background-color: #3d6bb0;

        }

        

        QSpinBox, QDoubleSpinBox, QComboBox {

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

    

    def on_caliber_changed(self, caliber: str):

        """Handle caliber selection change."""

        self.ammo_combo.clear()

        

        if caliber == "Custom":

            self.custom_ammo_group.setVisible(True)

            self.ammo_combo.addItem("Custom Ammunition")

        else:

            self.custom_ammo_group.setVisible(False)

            ammo_list = self.ammo_db.get_by_caliber(caliber)

            for ammo in ammo_list:

                self.ammo_combo.addItem(ammo.name, ammo)

    

    def on_ammunition_changed(self, index: int):

        """Handle ammunition selection change."""

        if self.caliber_combo.currentText() != "Custom" and index >= 0:

            ammo = self.ammo_combo.itemData(index)

            if ammo:

                self.bullet_weight_spin.setValue(ammo.bullet_weight)

                self.muzzle_velocity_spin.setValue(ammo.muzzle_velocity)

                self.ballistic_coefficient_spin.setValue(ammo.ballistic_coefficient)



                # Set drag model

                for i in range(self.drag_model_combo.count()):

                    if self.drag_model_combo.itemData(i) == ammo.drag_model:

                        self.drag_model_combo.setCurrentIndex(i)

                        break


    def _get_active_ammunition(self) -> Ammunition:

        """Return a copy of the currently configured ammunition."""

        if self.caliber_combo.currentText() == "Custom":

            drag_model = self.drag_model_combo.currentData()

            if not isinstance(drag_model, DragModel):

                drag_model = DragModel.G1

            return Ammunition(

                name="Custom",

                caliber="Custom",

                bullet_weight=self.bullet_weight_spin.value(),

                muzzle_velocity=self.muzzle_velocity_spin.value(),

                ballistic_coefficient=self.ballistic_coefficient_spin.value(),

                drag_model=drag_model,

            )

        ammo = self.ammo_combo.currentData()

        if not isinstance(ammo, Ammunition):

            raise ValueError("No ammunition selected for ballistic profile")

        return Ammunition.from_dict(ammo.to_dict())


    def _apply_custom_ammunition(self, ammo: Ammunition) -> None:

        """Apply a custom ammunition configuration to the UI."""

        if self.caliber_combo.findText("Custom") >= 0:

            self.caliber_combo.setCurrentText("Custom")

        self.custom_ammo_group.setVisible(True)

        self.bullet_weight_spin.setValue(ammo.bullet_weight)

        self.muzzle_velocity_spin.setValue(ammo.muzzle_velocity)

        self.ballistic_coefficient_spin.setValue(ammo.ballistic_coefficient)

        drag_index = self.drag_model_combo.findData(ammo.drag_model)

        if drag_index >= 0:

            self.drag_model_combo.setCurrentIndex(drag_index)


    def _apply_ammunition_to_ui(self, ammo: Ammunition) -> None:

        """Populate UI widgets with the provided ammunition selection."""

        caliber_index = self.caliber_combo.findText(ammo.caliber)

        if caliber_index == -1 or ammo.caliber == "Custom":

            self._apply_custom_ammunition(ammo)

            return

        self.caliber_combo.setCurrentIndex(caliber_index)

        # Ensure ammunition list reflects the caliber before selection

        self.on_caliber_changed(ammo.caliber)

        for idx in range(self.ammo_combo.count()):

            item_data = self.ammo_combo.itemData(idx)

            if isinstance(item_data, Ammunition) and item_data.name == ammo.name:

                self.ammo_combo.setCurrentIndex(idx)

                break

        else:

            self._apply_custom_ammunition(ammo)

    

    def calculate_ballistics(self):

        """Calculate ballistics trajectory."""

        try:

            # Create ammunition object

            if self.caliber_combo.currentText() == "Custom":

                ammo = Ammunition(

                    name="Custom",

                    caliber="Custom",

                    bullet_weight=self.bullet_weight_spin.value(),

                    muzzle_velocity=self.muzzle_velocity_spin.value(),

                    ballistic_coefficient=self.ballistic_coefficient_spin.value(),

                    drag_model=self.drag_model_combo.currentData()

                )

            else:

                ammo = self.ammo_combo.currentData()

                if not ammo:

                    QMessageBox.warning(self, "No Ammunition", "Please select ammunition.")

                    return

            

            # Create environmental conditions

            environment = EnvironmentalData(

                temperature=self.temperature_spin.value(),

                pressure=self.pressure_spin.value(),

                humidity=self.humidity_spin.value(),

                altitude=self.altitude_spin.value(),

                wind_speed=self.wind_speed_spin.value(),

                wind_direction=self.wind_direction_spin.value()

            )

            

            # Calculate trajectory

            self.current_result = self.calculator.calculate_trajectory(

                ammo=ammo,

                environment=environment,

                zero_distance=self.zero_distance_spin.value(),

                max_range=self.max_range_spin.value(),

                vital_zone_diameter=self.vital_zone_spin.value()

            )

            

            # Update displays

            self.update_trajectory_chart()

            self.update_data_table()

            self.update_summary()

            

            self.status_message.emit(f"Calculated trajectory for {ammo.name}")

            self.log_user_action("ballistics_calculated", {

                "ammunition": ammo.name,

                "zero_distance": self.zero_distance_spin.value()

            })

            

        except Exception as e:

            self.log_error("Ballistics calculation failed", exception=e)

            self.error_occurred.emit("Calculation Error", f"Failed to calculate trajectory: {str(e)}")

    

    def update_trajectory_chart(self):

        """Update the trajectory chart."""

        if not self.current_result:

            return

        

        try:

            chart = QChart()

            chart.setTitle("Bullet Trajectory")

            

            # Trajectory series

            trajectory_series = QLineSeries()

            trajectory_series.setName("Trajectory")

            

            for point in self.current_result.trajectory:

                trajectory_series.append(point.distance, point.drop * 100)  # Convert to cm

            

            chart.addSeries(trajectory_series)

            

            # Axes

            axis_x = QValueAxis()

            axis_x.setTitleText("Distance (m)")

            axis_x.setLabelFormat("%d")

            

            axis_y = QValueAxis()

            axis_y.setTitleText("Drop (cm)")

            axis_y.setLabelFormat("%.1f")

            

            chart.addAxis(axis_x, Qt.AlignBottom)

            chart.addAxis(axis_y, Qt.AlignLeft)

            

            trajectory_series.attachAxis(axis_x)

            trajectory_series.attachAxis(axis_y)

            

            self.chart_view.setChart(chart)

            

        except Exception as e:

            self.log_error("Failed to update trajectory chart", exception=e)

    

    def update_data_table(self):

        """Update the trajectory data table."""

        if not self.current_result:

            return

        

        try:

            trajectory = self.current_result.trajectory

            self.data_table.setRowCount(len(trajectory))

            

            for row, point in enumerate(trajectory):

                items = [

                    QTableWidgetItem(f"{point.distance:.0f}"),

                    QTableWidgetItem(f"{point.drop * 100:.1f}"),  # Convert to cm

                    QTableWidgetItem(f"{point.velocity:.1f}"),

                    QTableWidgetItem(f"{point.energy:.0f}"),

                    QTableWidgetItem(f"{point.time:.3f}"),

                    QTableWidgetItem(f"{point.windage * 100:.1f}")  # Convert to cm

                ]

                

                for col, item in enumerate(items):

                    item.setTextAlignment(Qt.AlignCenter)

                    self.data_table.setItem(row, col, item)

            

        except Exception as e:

            self.log_error("Failed to update data table", exception=e)

    

    def calculate_comeups(self):

        """Calculate scope adjustments for specified distances."""

        if not self.current_result:

            QMessageBox.information(self, "No Data", "Please calculate trajectory first.")

            return

        

        try:

            # Parse distances

            distance_text = self.comeup_distances_edit.text()

            distances = [float(d.strip()) for d in distance_text.split(',') if d.strip()]

            

            if not distances:

                QMessageBox.warning(self, "Invalid Input", "Please enter valid distances.")

                return

            

            # Calculate come-ups

            come_ups = self.calculator.calculate_come_ups(self.current_result, distances)

            

            # Update table

            self.comeups_table.setRowCount(len(distances))

            

            for row, distance in enumerate(distances):

                if distance in come_ups:

                    data = come_ups[distance]

                    items = [

                        QTableWidgetItem(f"{distance:.0f}"),

                        QTableWidgetItem(f"{data['elevation_moa']:.2f}"),

                        QTableWidgetItem(f"{data['windage_moa']:.2f}"),

                        QTableWidgetItem(f"{data['elevation_clicks']:.0f}"),

                        QTableWidgetItem(f"{data['windage_clicks']:.0f}"),

                        QTableWidgetItem(f"{data['velocity']:.1f}"),

                        QTableWidgetItem(f"{data['energy']:.0f}"),

                        QTableWidgetItem(f"{data['time_of_flight']:.3f}")

                    ]

                    

                    for col, item in enumerate(items):

                        item.setTextAlignment(Qt.AlignCenter)

                        self.comeups_table.setItem(row, col, item)

            

            self.log_user_action("comeups_calculated", {"distances": distances})

            

        except Exception as e:

            self.log_error("Failed to calculate come-ups", exception=e)

            self.error_occurred.emit("Come-Up Error", f"Failed to calculate come-ups: {str(e)}")

    

    def update_summary(self):

        """Update the ballistics summary."""

        if not self.current_result:

            return

        

        try:

            result = self.current_result

            ammo = result.ammunition

            env = result.environment

            

            summary = f"""

BALLISTICS SUMMARY

==================



Ammunition: {ammo.name}

Caliber: {ammo.caliber}

Bullet Weight: {ammo.bullet_weight} gr

Muzzle Velocity: {ammo.muzzle_velocity} m/s

Ballistic Coefficient: {ammo.ballistic_coefficient} ({ammo.drag_model.value})

Muzzle Energy: {result.muzzle_energy:.0f} J



Environmental Conditions:

Temperature: {env.temperature}Â°C

Pressure: {env.pressure} hPa

Humidity: {env.humidity}%

Altitude: {env.altitude} m

Wind: {env.wind_speed} m/s @ {env.wind_direction}Â°



Zero Distance: {result.zero_distance} m

Maximum Point Blank Range: {result.max_point_blank_range:.0f} m

Vital Zone Diameter: {result.vital_zone_diameter} m



TRAJECTORY DATA (Every 100m):

Distance    Drop      Velocity   Energy    Time     Wind Drift

  (m)       (cm)      (m/s)      (J)       (s)       (cm)

--------------------------------------------------------------

"""

            

            # Add trajectory data every 100m

            for point in result.trajectory:

                if point.distance % 100 == 0:

                    summary += f"{point.distance:6.0f}    {point.drop*100:6.1f}    {point.velocity:8.1f}   {point.energy:7.0f}   {point.time:6.3f}    {point.windage*100:6.1f}\n"

            

            self.summary_text.setPlainText(summary)

            

        except Exception as e:

            self.log_error("Failed to update summary", exception=e)

    

    def load_settings(self):

        """Load saved settings."""

        try:

            # Load last used values

            self.temperature_spin.setValue(self.settings.value("temperature", 15, int))

            self.pressure_spin.setValue(self.settings.value("pressure", 1013.25, float))

            self.humidity_spin.setValue(self.settings.value("humidity", 50, int))

            self.altitude_spin.setValue(self.settings.value("altitude", 0, int))

            self.zero_distance_spin.setValue(self.settings.value("zero_distance", 100, int))

            self.max_range_spin.setValue(self.settings.value("max_range", 800, int))

            

            # Initial caliber and ammo selection

            QTimer.singleShot(100, lambda: self.on_caliber_changed(self.caliber_combo.currentText()))

            

        except Exception as e:

            self.log_warning("Failed to load settings", exception=e)

    

    def save_settings(self):

        """Save current settings."""

        try:

            self.settings.setValue("temperature", self.temperature_spin.value())

            self.settings.setValue("pressure", self.pressure_spin.value())

            self.settings.setValue("humidity", self.humidity_spin.value())

            self.settings.setValue("altitude", self.altitude_spin.value())

            self.settings.setValue("zero_distance", self.zero_distance_spin.value())

            self.settings.setValue("max_range", self.max_range_spin.value())

            

        except Exception as e:

            self.log_warning("Failed to save settings", exception=e)

    

    def export_results(self, file_path: str, format_type: str = "CSV"):

        """Export ballistics results to file."""

        if not self.current_result:

            raise ValueError("No calculation results to export")

        

        try:

            if format_type.upper() == "CSV":

                self._export_csv(file_path)

            elif format_type.upper() == "JSON":

                self._export_json(file_path)

            else:

                raise ValueError(f"Unsupported export format: {format_type}")

            

            self.log_user_action("ballistics_export", {

                "format": format_type,

                "file_path": file_path,

                "ammunition": self.current_result.ammunition.name

            })

            

        except Exception as e:

            self.log_error("Failed to export ballistics results", exception=e)

            raise

    

    def _export_csv(self, file_path: str):

        """Export results to CSV format."""

        import csv

        

        with open(file_path, 'w', newline='', encoding='utf-8') as f:

            writer = csv.writer(f)

            

            # Header information

            writer.writerow(["Hunt Pro Ballistics Calculation"])

            writer.writerow([f"Ammunition: {self.current_result.ammunition.name}"])

            writer.writerow([f"Zero Distance: {self.current_result.zero_distance} m"])

            writer.writerow([f"Environment: {self.current_result.environment.temperature}Â°C, {self.current_result.environment.pressure} hPa"])

            writer.writerow([])

            

            # Column headers

            writer.writerow(["Distance (m)", "Drop (cm)", "Velocity (m/s)", "Energy (J)", "Time (s)", "Wind Drift (cm)"])

            

            # Data rows

            for point in self.current_result.trajectory:

                writer.writerow([

                    f"{point.distance:.0f}",

                    f"{point.drop * 100:.1f}",

                    f"{point.velocity:.1f}",

                    f"{point.energy:.0f}",

                    f"{point.time:.3f}",

                    f"{point.windage * 100:.1f}"

                ])

    

    def _export_json(self, file_path: str):

        """Export results to JSON format."""

        data = {

            "ammunition": {

                "name": self.current_result.ammunition.name,

                "caliber": self.current_result.ammunition.caliber,

                "bullet_weight": self.current_result.ammunition.bullet_weight,

                "muzzle_velocity": self.current_result.ammunition.muzzle_velocity,

                "ballistic_coefficient": self.current_result.ammunition.ballistic_coefficient,

                "drag_model": self.current_result.ammunition.drag_model.value

            },

            "environment": {

                "temperature": self.current_result.environment.temperature,

                "pressure": self.current_result.environment.pressure,

                "humidity": self.current_result.environment.humidity,

                "altitude": self.current_result.environment.altitude,

                "wind_speed": self.current_result.environment.wind_speed,

                "wind_direction": self.current_result.environment.wind_direction

            },

            "zero_distance": self.current_result.zero_distance,

            "max_point_blank_range": self.current_result.max_point_blank_range,

            "muzzle_energy": self.current_result.muzzle_energy,

            "trajectory": [

                {

                    "distance": point.distance,

                    "drop": point.drop,

                    "velocity": point.velocity,

                    "energy": point.energy,

                    "time": point.time,

                    "windage": point.windage

                }

                for point in self.current_result.trajectory

            ]

        }

        

        with open(file_path, 'w', encoding='utf-8') as f:

            json.dump(data, f, indent=2, ensure_ascii=False)

    

    def cleanup(self):

        """Clean up resources when module is closed."""

        self.save_settings()

        super().cleanup()

        self.log_info("Ballistics module cleaned up")

    

    def get_display_name(self) -> str:

        """Return the display name for this module."""

        return "Ballistics Calculator"

    

    def create_profile_snapshot(self, name: str, notes: str = "") -> BallisticProfile:

        """Capture the current module configuration as a ballistic profile."""

        normalized_name = name.strip()

        if not normalized_name:

            raise ValueError("Profile name is required")

        ammunition = self._get_active_ammunition()

        environment = EnvironmentalData(

            temperature=float(self.temperature_spin.value()),

            pressure=float(self.pressure_spin.value()),

            humidity=float(self.humidity_spin.value()),

            altitude=float(self.altitude_spin.value()),

            wind_speed=float(self.wind_speed_spin.value()),

            wind_direction=float(self.wind_direction_spin.value()),

        )

        profile = BallisticProfile(

            name=normalized_name,

            ammunition=ammunition,

            environment=environment,

            zero_distance=float(self.zero_distance_spin.value()),

            max_range=float(self.max_range_spin.value()),

            vital_zone_diameter=float(self.vital_zone_spin.value()),

            notes=notes.strip(),

        )

        return profile


    def save_ballistic_profile(self, name: str, notes: str = "") -> BallisticProfile:

        """Persist a ballistic profile snapshot to disk."""

        profile = self.create_profile_snapshot(name, notes)

        self.profile_storage.save_profile(profile)

        self.status_message.emit(f"Saved ballistic profile '{profile.name}'")

        self.log_user_action("ballistic_profile_saved", {"profile": profile.name})

        return profile


    def load_ballistic_profile(self, name: str) -> BallisticProfile:

        """Load a saved ballistic profile and apply it to the UI."""

        profiles = self.profile_storage.load_profiles()

        if name not in profiles:

            raise KeyError(f"Ballistic profile '{name}' not found")

        profile = profiles[name]

        self._apply_ammunition_to_ui(profile.ammunition)

        environment = profile.environment

        def apply_spin(spin, value):

            minimum = spin.minimum()

            maximum = spin.maximum()

            coerced = max(minimum, min(maximum, value))

            if isinstance(spin, QSpinBox):

                spin.setValue(int(round(coerced)))

            else:

                spin.setValue(float(coerced))

        apply_spin(self.temperature_spin, environment.temperature)

        apply_spin(self.pressure_spin, environment.pressure)

        apply_spin(self.humidity_spin, environment.humidity)

        apply_spin(self.altitude_spin, environment.altitude)

        apply_spin(self.wind_speed_spin, environment.wind_speed)

        apply_spin(self.wind_direction_spin, environment.wind_direction)

        apply_spin(self.zero_distance_spin, profile.zero_distance)

        apply_spin(self.max_range_spin, profile.max_range)

        apply_spin(self.vital_zone_spin, profile.vital_zone_diameter)

        self.status_message.emit(f"Loaded ballistic profile '{profile.name}'")

        self.log_user_action("ballistic_profile_loaded", {"profile": profile.name})

        return profile


    def list_ballistic_profiles(self) -> List[str]:

        """Return the names of saved ballistic profiles."""

        return sorted(self.profile_storage.load_profiles().keys())


    def export_ballistic_profiles(self, file_path: str, profile_names: Optional[List[str]] = None) -> List[str]:

        """Export selected ballistic profiles to a JSON file."""

        exported = self.profile_storage.export_profiles(file_path, profile_names)

        self.status_message.emit(f"Exported {len(exported)} ballistic profile(s)")

        self.log_user_action(

            "ballistic_profiles_exported",

            {"count": len(exported), "file_path": str(file_path)},

        )

        return exported


    def import_ballistic_profiles(self, file_path: str, overwrite: bool = False) -> BallisticProfileImportReport:

        """Import ballistic profiles from disk."""

        report = self.profile_storage.import_profiles(file_path, overwrite=overwrite)

        if report.total_imported:

            message = f"Imported {report.total_imported} ballistic profile(s)"

        else:

            message = "No ballistic profiles were imported"

        self.status_message.emit(message)

        self.log_user_action(

            "ballistic_profiles_imported",

            {

                "count": report.total_imported,

                "skipped": len(report.skipped),

                "file_path": str(file_path),

                "overwrite": overwrite,

            },

        )

        return report


    def get_description(self) -> str:

        """Return a description of this module's functionality."""

        return "Advanced ballistics calculator with environmental corrections, trajectory modeling, and comprehensive ammunition database."





# Utility functions for ballistics calculations

def meters_to_yards(meters: float) -> float:

    """Convert meters to yards."""

    return meters * 1.09361



def yards_to_meters(yards: float) -> float:

    """Convert yards to meters."""

    return yards * 0.9144



def mps_to_fps(mps: float) -> float:

    """Convert meters per second to feet per second."""

    return mps * 3.28084



def fps_to_mps(fps: float) -> float:

    """Convert feet per second to meters per second."""

    return fps * 0.3048



def joules_to_ft_lbs(joules: float) -> float:

    """Convert joules to foot-pounds."""

    return joules * 0.737562



def ft_lbs_to_joules(ft_lbs: float) -> float:

    """Convert foot-pounds to joules."""

    return ft_lbs * 1.35582



def grains_to_grams(grains: float) -> float:

    """Convert grains to grams."""

    return grains * 0.0647989



def grams_to_grains(grams: float) -> float:

    """Convert grams to grains."""

    return grams * 15.4324



def celsius_to_fahrenheit(celsius: float) -> float:

    """Convert Celsius to Fahrenheit."""

    return (celsius * 9/5) + 32



def fahrenheit_to_celsius(fahrenheit: float) -> float:

    """Convert Fahrenheit to Celsius."""

    return (fahrenheit - 32) * 5/9



def hpa_to_inhg(hpa: float) -> float:

    """Convert hectopascals to inches of mercury."""

    return hpa * 0.02953



def inhg_to_hpa(inhg: float) -> float:

    """Convert inches of mercury to hectopascals."""

    return inhg * 33.8639



def calculate_sectional_density(bullet_weight_grains: float, diameter_inches: float) -> float:

    """Calculate sectional density."""

    return bullet_weight_grains / (7000 * diameter_inches ** 2)



def estimate_bc_from_sd(sectional_density: float, bullet_type: str = "spitzer") -> float:

    """Estimate ballistic coefficient from sectional density."""

    # Very rough estimation - actual BC depends on bullet shape

    base_multiplier = {

        "spitzer": 0.5,

        "boat_tail": 0.55,

        "flat_base": 0.45,

        "round_nose": 0.35

    }.get(bullet_type.lower(), 0.5)

    

    return sectional_density * base_multiplier



def calculate_kinetic_energy(mass_kg: float, velocity_mps: float) -> float:

    """Calculate kinetic energy in joules."""

    return 0.5 * mass_kg * velocity_mps ** 2



def calculate_momentum(mass_kg: float, velocity_mps: float) -> float:

    """Calculate momentum in kgâ‹…m/s."""

    return mass_kg * velocity_mps



def calculate_taylor_ko_factor(bullet_weight_grains: float, velocity_fps: float, diameter_inches: float) -> float:

    """Calculate Taylor Knock-Out factor."""

    return (bullet_weight_grains * velocity_fps * diameter_inches) / 7000



def estimate_recoil_energy(bullet_weight_grains: float, powder_weight_grains: float, 

                          muzzle_velocity_fps: float, rifle_weight_lbs: float) -> float:

    """Estimate recoil energy in foot-pounds."""

    # Simplified recoil calculation

    bullet_momentum = bullet_weight_grains * muzzle_velocity_fps

    powder_momentum = powder_weight_grains * 4000  # Approximate gas velocity

    total_momentum = (bullet_momentum + powder_momentum) / 7000  # Convert to lbâ‹…ft/s

    

    rifle_weight_slugs = rifle_weight_lbs / 32.174

    recoil_velocity = total_momentum / rifle_weight_slugs

    

    return 0.5 * rifle_weight_slugs * recoil_velocity ** 2



def atmospheric_correction_factor(temperature_f: float, pressure_inhg: float, 

                                humidity_percent: float) -> float:

    """Calculate atmospheric correction factor for ballistic coefficient."""

    # Standard conditions: 59Â°F, 29.92 inHg, 78% humidity

    temp_factor = (459.4 + temperature_f) / 518.4  # Rankine scale

    pressure_factor = pressure_inhg / 29.92

    humidity_factor = (100 - humidity_percent) / 22  # Simplified

    

    return (pressure_factor / temp_factor) * humidity_factor



# Ballistics formulas and constants

GRAVITY_METRIC = 9.80665  # m/sÂ²

GRAVITY_IMPERIAL = 32.174  # ft/sÂ²

STANDARD_TEMPERATURE_C = 15.0  # Â°C

STANDARD_TEMPERATURE_F = 59.0  # Â°F

STANDARD_PRESSURE_HPA = 1013.25  # hPa

STANDARD_PRESSURE_INHG = 29.92  # inHg

SPEED_OF_SOUND_STP = 331.3  # m/s at standard temperature and pressure

