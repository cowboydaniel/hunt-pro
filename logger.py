"""
Enhanced Logging System for Hunt Pro.
Provides comprehensive logging capabilities with multiple levels,
structured logging, and field-specific features.
"""
import logging
import logging.handlers
import time
import json
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, Union
from enum import Enum, auto
from contextlib import contextmanager
from datetime import datetime
import uuid
class LogLevel(Enum):
    """Enhanced log levels with field-specific categories."""
    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
class LogCategory(Enum):
    """Categories for field-specific logging."""
    SYSTEM = auto()
    GPS = auto()
    BALLISTICS = auto()
    WEATHER = auto()
    SENSORS = auto()
    USER_ACTION = auto()
    FIELD_EVENT = auto()
    HARDWARE = auto()
    NETWORK = auto()
    DATA = auto()
class StructuredFormatter(logging.Formatter):
    """Custom formatter that supports structured logging with JSON output."""
    def __init__(self, include_json=True):
        super().__init__()
        self.include_json = include_json
    def format(self, record: logging.LogRecord) -> str:
        # Basic formatting
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        level = record.levelname
        logger_name = record.name
        message = record.getMessage()
        # Basic log line
        basic_line = f"[{timestamp}] {level:8} {logger_name}: {message}"
        # Add structured data if available
        structured_data = {}
        # Extract custom fields
        for key, value in record.__dict__.items():
            if key.startswith('field_') or key in ['category', 'session_id', 'user_id']:
                structured_data[key] = value
        # Add exception info if present
        if record.exc_info:
            structured_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        # Add location info
        structured_data['location'] = {
            'filename': record.filename,
            'line': record.lineno,
            'function': record.funcName
        }
        if structured_data and self.include_json:
            json_data = json.dumps(structured_data, default=str, ensure_ascii=False)
            return f"{basic_line} | {json_data}"
        return basic_line
class HuntProLogger:
    """Enhanced logger for Hunt Pro with field-specific features."""
    def __init__(self, name: str = "huntpro", log_dir: Optional[Path] = None):
        self.name = name
        self.session_id = str(uuid.uuid4())[:8]
        # Setup log directory
        if log_dir is None:
            log_dir = Path.home() / "HuntPro" / "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Setup loggers
        self._setup_loggers()
        # Session info
        self.info("Hunt Pro logging system initialized", 
                 session_id=self.session_id,
                 log_dir=str(self.log_dir))
    def _setup_loggers(self):
        """Setup main logger and handlers."""
        # Main logger
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)
        # Clear any existing handlers
        self.logger.handlers.clear()
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = StructuredFormatter(include_json=False)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        # File handler with rotation
        log_file = self.log_dir / f"{self.name}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = StructuredFormatter(include_json=True)
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        # Field events handler (separate file for field-specific events)
        field_log_file = self.log_dir / f"{self.name}_field.log"
        self.field_handler = logging.handlers.RotatingFileHandler(
            field_log_file, maxBytes=5*1024*1024, backupCount=3
        )
        self.field_handler.setLevel(logging.INFO)
        field_formatter = StructuredFormatter(include_json=True)
        self.field_handler.setFormatter(field_formatter)
        # Error handler (separate file for errors and critical issues)
        error_log_file = self.log_dir / f"{self.name}_errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file, maxBytes=5*1024*1024, backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StructuredFormatter(include_json=True))
        self.logger.addHandler(error_handler)
    def _log(self, level: int, message: str, category: Optional[LogCategory] = None, 
             exception: Optional[Exception] = None, **kwargs):
        """Internal logging method with enhanced features."""
        extra = {
            'session_id': self.session_id,
            'category': category.name if category else 'GENERAL'
        }
        # Add custom fields
        for key, value in kwargs.items():
            if not key.startswith('_'):
                extra[f'field_{key}'] = value
        # Create log record
        if exception:
            self.logger.log(level, message, exc_info=(type(exception), exception, exception.__traceback__), extra=extra)
        else:
            self.logger.log(level, message, extra=extra)
    def trace(self, message: str, category: Optional[LogCategory] = None, **kwargs):
        """Log trace message (most detailed debugging info)."""
        self._log(LogLevel.TRACE.value, message, category, **kwargs)
    def debug(self, message: str, category: Optional[LogCategory] = None, **kwargs):
        """Log debug message."""
        self._log(LogLevel.DEBUG.value, message, category, **kwargs)
    def info(self, message: str, category: Optional[LogCategory] = None, **kwargs):
        """Log info message."""
        self._log(LogLevel.INFO.value, message, category, **kwargs)
    def warning(self, message: str, category: Optional[LogCategory] = None, **kwargs):
        """Log warning message."""
        self._log(LogLevel.WARNING.value, message, category, **kwargs)
    def error(self, message: str, exception: Optional[Exception] = None, 
              category: Optional[LogCategory] = None, **kwargs):
        """Log error message."""
        self._log(LogLevel.ERROR.value, message, category, exception, **kwargs)
    def critical(self, message: str, exception: Optional[Exception] = None,
                 category: Optional[LogCategory] = None, **kwargs):
        """Log critical message."""
        self._log(LogLevel.CRITICAL.value, message, category, exception, **kwargs)
    def field_event(self, message: str, **kwargs):
        """Log field-specific event (hunting, navigation, etc.)."""
        self._log(LogLevel.INFO.value, f"FIELD EVENT: {message}", 
                 LogCategory.FIELD_EVENT, **kwargs)
        # Also log to field handler
        extra = {'session_id': self.session_id, 'category': 'FIELD_EVENT'}
        for key, value in kwargs.items():
            if not key.startswith('_'):
                extra[f'field_{key}'] = value
        self.field_handler.handle(
            self.logger.makeRecord(self.name, LogLevel.INFO.value, __file__, 0, 
                                 f"FIELD EVENT: {message}", (), None, extra=extra)
        )
    def log_user_action(self, action: str, details: Optional[Dict[str, Any]] = None):
        """Log user actions for analytics and debugging."""
        log_data = {
            'action': action,
            'timestamp': time.time()
        }
        if details:
            log_data.update(details)
        self._log(LogLevel.INFO.value, f"USER ACTION: {action}", 
                 LogCategory.USER_ACTION, **log_data)
    def log_gps_event(self, event_type: str, latitude: Optional[float] = None, 
                      longitude: Optional[float] = None, accuracy: Optional[float] = None, **kwargs):
        """Log GPS-related events."""
        gps_data = {'event_type': event_type}
        if latitude is not None:
            gps_data['latitude'] = latitude
        if longitude is not None:
            gps_data['longitude'] = longitude
        if accuracy is not None:
            gps_data['accuracy'] = accuracy
        gps_data.update(kwargs)
        self._log(LogLevel.INFO.value, f"GPS: {event_type}", LogCategory.GPS, **gps_data)
    def log_ballistics_calculation(self, calculation_type: str, inputs: Dict[str, Any], 
                                   results: Dict[str, Any]):
        """Log ballistics calculations for audit trail."""
        self._log(LogLevel.INFO.value, f"BALLISTICS: {calculation_type}", 
                 LogCategory.BALLISTICS, inputs=inputs, results=results)
    def log_sensor_reading(self, sensor_type: str, value: Union[float, int, str], 
                           unit: Optional[str] = None, **kwargs):
        """Log sensor readings (compass, accelerometer, etc.)."""
        sensor_data = {
            'sensor_type': sensor_type,
            'value': value,
            'unit': unit,
            'timestamp': time.time()
        }
        sensor_data.update(kwargs)
        self._log(LogLevel.DEBUG.value, f"SENSOR: {sensor_type}={value}{unit or ''}", 
                 LogCategory.SENSORS, **sensor_data)
    def log_weather_data(self, temperature: Optional[float] = None, 
                         humidity: Optional[float] = None, pressure: Optional[float] = None,
                         wind_speed: Optional[float] = None, wind_direction: Optional[float] = None,
                         **kwargs):
        """Log weather data."""
        weather_data = {k: v for k, v in {
            'temperature': temperature,
            'humidity': humidity,
            'pressure': pressure,
            'wind_speed': wind_speed,
            'wind_direction': wind_direction
        }.items() if v is not None}
        weather_data.update(kwargs)
        self._log(LogLevel.INFO.value, "WEATHER DATA", LogCategory.WEATHER, **weather_data)
    @contextmanager
    def timer(self, operation: str, log_result: bool = True):
        """Context manager for timing operations."""
        start_time = time.time()
        operation_id = str(uuid.uuid4())[:8]
        self.debug(f"Starting operation: {operation}", 
                  category=LogCategory.SYSTEM, operation_id=operation_id)
        try:
            yield operation_id
        finally:
            duration = time.time() - start_time
            if log_result:
                self.info(f"Completed operation: {operation} in {duration:.3f}s", 
                         category=LogCategory.SYSTEM, operation_id=operation_id, 
                         duration=duration)
    def log_hardware_event(self, device: str, event: str, status: str = "OK", **kwargs):
        """Log hardware-related events."""
        self._log(LogLevel.INFO.value, f"HARDWARE: {device} - {event} ({status})",
                 LogCategory.HARDWARE, device=device, event=event, status=status, **kwargs)
    def log_network_event(self, event_type: str, url: Optional[str] = None, 
                          status_code: Optional[int] = None, **kwargs):
        """Log network-related events."""
        network_data = {'event_type': event_type}
        if url:
            network_data['url'] = url
        if status_code:
            network_data['status_code'] = status_code
        network_data.update(kwargs)
        self._log(LogLevel.INFO.value, f"NETWORK: {event_type}", 
                 LogCategory.NETWORK, **network_data)
    def get_session_id(self) -> str:
        """Get the current session ID."""
        return self.session_id
    def set_log_level(self, level: Union[str, int, LogLevel]):
        """Set the logging level."""
        if isinstance(level, LogLevel):
            level = level.value
        elif isinstance(level, str):
            level = getattr(logging, level.upper())
        self.logger.setLevel(level)
        self.info(f"Log level set to: {logging.getLevelName(level)}")
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """Clean up log files older than specified days."""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            removed_count = 0
            for log_file in self.log_dir.glob("*.log*"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    removed_count += 1
            self.info(f"Cleaned up {removed_count} old log files", 
                     category=LogCategory.SYSTEM,
                     removed_count=removed_count,
                     days_to_keep=days_to_keep)
        except Exception as e:
            self.error("Failed to cleanup old logs", exception=e)
    def export_logs(self, output_file: Path, start_date: Optional[datetime] = None,
                    end_date: Optional[datetime] = None, categories: Optional[list] = None):
        """Export logs to a file with filtering options."""
        try:
            exported_lines = []
            for log_file in self.log_dir.glob("*.log"):
                with open(log_file, 'r') as f:
                    for line in f:
                        # Basic filtering could be added here
                        exported_lines.append(line.strip())
            with open(output_file, 'w') as f:
                f.write('\n'.join(exported_lines))
            self.info(f"Exported {len(exported_lines)} log entries to {output_file}",
                     category=LogCategory.SYSTEM)
        except Exception as e:
            self.error(f"Failed to export logs to {output_file}", exception=e)
# Global logger instance
_global_logger: Optional[HuntProLogger] = None
def get_logger() -> HuntProLogger:
    """Get the global logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = HuntProLogger()
    return _global_logger
def setup_logger(name: str = "huntpro", log_dir: Optional[Path] = None) -> HuntProLogger:
    """Set up and return the global logger."""
    global _global_logger
    _global_logger = HuntProLogger(name, log_dir)
    return _global_logger
# Convenience functions for global logger
def trace(message: str, **kwargs):
    """Log trace message using global logger."""
    get_logger().trace(message, **kwargs)
def debug(message: str, **kwargs):
    """Log debug message using global logger."""
    get_logger().debug(message, **kwargs)
def info(message: str, **kwargs):
    """Log info message using global logger."""
    get_logger().info(message, **kwargs)
def warning(message: str, **kwargs):
    """Log warning message using global logger."""
    get_logger().warning(message, **kwargs)
def error(message: str, exception: Optional[Exception] = None, **kwargs):
    """Log error message using global logger."""
    get_logger().error(message, exception=exception, **kwargs)
def critical(message: str, exception: Optional[Exception] = None, **kwargs):
    """Log critical message using global logger."""
    get_logger().critical(message, exception=exception, **kwargs)
def field_event(message: str, **kwargs):
    """Log field event using global logger."""
    get_logger().field_event(message, **kwargs)
def log_user_action(action: str, details: Optional[Dict[str, Any]] = None):
    """Log user action using global logger."""
    get_logger().log_user_action(action, details)
def timer(operation: str, log_result: bool = True):
    """Timer context manager using global logger."""
    return get_logger().timer(operation, log_result)
# Mixin class for easy logging integration
class LoggableMixin:
    """Mixin class to add logging capabilities to other classes."""
    def __init__(self):
        self._logger = get_logger()
        self._module_name = self.__class__.__name__
    def log_trace(self, message: str, **kwargs):
        """Log trace message."""
        self._logger.trace(f"[{self._module_name}] {message}", **kwargs)
    def log_debug(self, message: str, **kwargs):
        """Log debug message."""
        self._logger.debug(f"[{self._module_name}] {message}", **kwargs)
    def log_info(self, message: str, **kwargs):
        """Log info message."""
        self._logger.info(f"[{self._module_name}] {message}", **kwargs)
    def log_warning(self, message: str, **kwargs):
        """Log warning message."""
        self._logger.warning(f"[{self._module_name}] {message}", **kwargs)
    def log_error(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log error message."""
        self._logger.error(f"[{self._module_name}] {message}", exception=exception, **kwargs)
    def log_critical(self, message: str, exception: Optional[Exception] = None, **kwargs):
        """Log critical message."""
        self._logger.critical(f"[{self._module_name}] {message}", exception=exception, **kwargs)
    def log_field_event(self, message: str, **kwargs):
        """Log field event."""
        self._logger.field_event(f"[{self._module_name}] {message}", **kwargs)
    def log_user_action(self, action: str, details: Optional[Dict[str, Any]] = None):
        """Log user action."""
        action_details = {'module': self._module_name}
        if details:
            action_details.update(details)
        self._logger.log_user_action(action, action_details)
