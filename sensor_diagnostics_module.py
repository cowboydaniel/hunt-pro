"""Qt user interface for the sensor diagnostics workflows."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Deque, Dict, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from device_manager import DeviceManager, DeviceType, PairedDevice
from logger import get_logger
from main import BaseModule
from sensor_diagnostics import (
    SensorDiagnosticSnapshot,
    SensorDiagnosticsEngine,
)
from simulated_devices import ensure_simulated_diagnostics_devices


class SensorDiagnosticsModule(BaseModule):
    """Qt module that surfaces sensor diagnostics and calibration workflows."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.logger = get_logger()
        self.device_manager = DeviceManager(auto_load_plugins=True)
        self.engine = SensorDiagnosticsEngine()
        self._snapshots: Dict[str, SensorDiagnosticSnapshot] = {}
        self._calibration_queue: Deque[str] = deque()
        self._active_calibration_device: Optional[str] = None
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(2500)
        self._update_timer.timeout.connect(self._refresh_diagnostics)
        self._calibration_timer = QTimer(self)
        self._calibration_timer.setInterval(1800)
        self._calibration_timer.timeout.connect(self._advance_calibration)
        self._build_ui()

    def initialize(self) -> bool:
        try:
            self._bootstrap_simulated_devices()
            self._populate_device_list()
            success = super().initialize()
            if success:
                self._update_timer.start()
            return success
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.exception("Failed to initialise sensor diagnostics", exc_info=exc)
            self.error_occurred.emit("Diagnostics", str(exc))
            return False

    def cleanup(self):  # pragma: no cover - UI cleanup only
        self._update_timer.stop()
        self._calibration_timer.stop()
        super().cleanup()

    # ------------------------------------------------------------------ UI setup
    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        self.device_list = QListWidget()
        self.device_list.setObjectName("sensorDeviceList")
        self.device_list.currentRowChanged.connect(self._on_device_selected)
        layout.addWidget(self.device_list, 1)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)
        layout.addLayout(right_panel, 2)

        self.header_label = QLabel("Select a device to view diagnostics")
        self.header_label.setObjectName("sensorHeader")
        self.header_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        right_panel.addWidget(self.header_label)

        status_group = QGroupBox("Live Status")
        status_layout = QGridLayout(status_group)
        status_layout.setColumnStretch(1, 1)

        status_layout.addWidget(QLabel("Health state:"), 0, 0)
        self.status_value_label = QLabel("-")
        self.status_value_label.setObjectName("sensorStatusValue")
        status_layout.addWidget(self.status_value_label, 0, 1)

        status_layout.addWidget(QLabel("Signal quality:"), 1, 0)
        self.signal_bar = QProgressBar()
        self.signal_bar.setRange(0, 100)
        status_layout.addWidget(self.signal_bar, 1, 1)

        status_layout.addWidget(QLabel("Battery level:"), 2, 0)
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        status_layout.addWidget(self.battery_bar, 2, 1)

        status_layout.addWidget(QLabel("Last calibration:"), 3, 0)
        self.last_calibration_label = QLabel("Unknown")
        status_layout.addWidget(self.last_calibration_label, 3, 1)

        right_panel.addWidget(status_group)

        metrics_group = QGroupBox("Sensor Metrics")
        metrics_layout = QVBoxLayout(metrics_group)
        self.metrics_table = QTableWidget(0, 3)
        self.metrics_table.setHorizontalHeaderLabels(["Metric", "Value", "Status"])
        self.metrics_table.horizontalHeader().setStretchLastSection(True)
        self.metrics_table.verticalHeader().setVisible(False)
        self.metrics_table.setEditTriggers(QTableWidget.NoEditTriggers)
        metrics_layout.addWidget(self.metrics_table)
        right_panel.addWidget(metrics_group)

        alerts_group = QGroupBox("Alerts")
        alerts_layout = QVBoxLayout(alerts_group)
        self.alerts_list = QListWidget()
        self.alerts_list.setObjectName("sensorAlerts")
        alerts_layout.addWidget(self.alerts_list)
        right_panel.addWidget(alerts_group)

        calibration_group = QGroupBox("Calibration Workflow")
        calibration_layout = QVBoxLayout(calibration_group)
        self.calibration_status_label = QLabel("No calibration active")
        calibration_layout.addWidget(self.calibration_status_label)
        self.calibration_steps_list = QListWidget()
        calibration_layout.addWidget(self.calibration_steps_list)
        button_row = QHBoxLayout()
        self.calibrate_button = QPushButton("Start Calibration")
        self.calibrate_button.clicked.connect(self._begin_calibration)
        button_row.addStretch(1)
        button_row.addWidget(self.calibrate_button)
        calibration_layout.addLayout(button_row)
        right_panel.addWidget(calibration_group)

        right_panel.addStretch(1)

    # ---------------------------------------------------------------- Diagnostics
    def _bootstrap_simulated_devices(self) -> None:
        self.logger.info("Bootstrapping simulated hardware for diagnostics module")
        ensure_simulated_diagnostics_devices(self.device_manager)

    def _populate_device_list(self) -> None:
        self.device_list.clear()
        for device in self.device_manager.get_paired_devices():
            label = device.label
            if device.metadata.get("simulated"):
                label += " (Simulated)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, device.device_id)
            self.device_list.addItem(item)
        if self.device_list.count():
            self.device_list.setCurrentRow(0)

    def _selected_device(self) -> Optional[PairedDevice]:
        current = self.device_list.currentItem()
        if current is None:
            return None
        device_id = current.data(Qt.UserRole)
        if not device_id:
            return None
        return self.device_manager.get_device(device_id)

    def _on_device_selected(self, index: int) -> None:  # pragma: no cover - UI signal
        if index < 0:
            self._clear_display()
            return
        self._refresh_diagnostics()

    def _refresh_diagnostics(self) -> None:
        device = self._selected_device()
        if device is None:
            self._clear_display()
            return
        snapshot = self.engine.compute_snapshot(device)
        self._snapshots[device.device_id] = snapshot
        self._render_snapshot(device, snapshot)

    def _clear_display(self) -> None:
        self.header_label.setText("Select a device to view diagnostics")
        self.status_value_label.setText("-")
        self.signal_bar.setValue(0)
        self.battery_bar.setValue(0)
        self.alerts_list.clear()
        self.metrics_table.setRowCount(0)
        self.calibration_status_label.setText("No calibration active")
        self.calibration_steps_list.clear()
        self.last_calibration_label.setText("Unknown")

    def _render_snapshot(self, device: PairedDevice, snapshot: SensorDiagnosticSnapshot) -> None:
        self.header_label.setText(device.label)
        self.status_value_label.setText(snapshot.status.title())
        self.signal_bar.setValue(snapshot.signal_quality)
        self.signal_bar.setFormat(f"{snapshot.signal_quality}%")
        self.battery_bar.setValue(snapshot.battery_level)
        self.battery_bar.setFormat(f"{snapshot.battery_level}%")
        if snapshot.last_calibrated:
            self.last_calibration_label.setText(snapshot.last_calibrated)
        else:
            self.last_calibration_label.setText(device.metadata.get("calibration", "Unknown"))

        self.metrics_table.setRowCount(len(snapshot.metrics))
        for row, metric in enumerate(snapshot.metrics):
            for column, value in enumerate([metric.label, metric.value, metric.status]):
                item = QTableWidgetItem(value)
                if column == 2 and metric.status != "nominal":
                    item.setForeground(Qt.yellow if metric.status == "warn" else Qt.red)
                self.metrics_table.setItem(row, column, item)

        self.alerts_list.clear()
        if snapshot.alerts:
            for alert in snapshot.alerts:
                self.alerts_list.addItem(alert)
        else:
            self.alerts_list.addItem("All systems nominal")

        if snapshot.calibration_recommended and not self._calibration_queue:
            self.calibration_status_label.setText("Calibration recommended")
        elif not self._calibration_queue:
            self.calibration_status_label.setText("Calibration up to date")

        self.calibrate_button.setEnabled(not self._calibration_queue)

    # ------------------------------------------------------------ Calibration
    def _begin_calibration(self) -> None:
        device = self._selected_device()
        if device is None:
            return
        steps = self.engine.get_calibration_steps(device)
        self._calibration_queue = deque(steps)
        self._active_calibration_device = device.device_id
        self.calibration_steps_list.clear()
        for step in steps:
            self.calibration_steps_list.addItem(step)
        self.calibration_status_label.setText("Calibration in progress...")
        self.calibrate_button.setEnabled(False)
        self._calibration_timer.start()

    def _advance_calibration(self) -> None:
        if not self._calibration_queue:
            self._finish_calibration()
            return
        current_step = self._calibration_queue.popleft()
        for index in range(self.calibration_steps_list.count()):
            item = self.calibration_steps_list.item(index)
            if item.text() == current_step:
                item.setText(f"[Done] {current_step}")
                break
        if not self._calibration_queue:
            self._finish_calibration()

    def _finish_calibration(self) -> None:
        self._calibration_timer.stop()
        if not self._active_calibration_device:
            return
        device = self.device_manager.get_device(self._active_calibration_device)
        self._active_calibration_device = None
        if device is None:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        device.metadata["calibration"] = "field_verified"
        device.metadata["last_calibrated"] = timestamp
        self.calibration_status_label.setText("Calibration complete")
        self.calibrate_button.setEnabled(True)
        self._refresh_diagnostics()


__all__ = ["SensorDiagnosticsModule"]
