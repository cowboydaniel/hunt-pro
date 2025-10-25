"""Placeholder Field Tools module for Hunt Pro."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from logger import get_logger
from main import BaseModule


class FieldToolsModule(BaseModule):
    """Provide a lightweight placeholder module so the loader succeeds."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.logger = get_logger()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Field Tools Coming Soon")
        title.setObjectName("fieldToolsTitle")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)

        message = QLabel(
            "The Field Tools suite is under active development. "
            "Future updates will include weather utilities, first aid guidance, "
            "and additional field calculators."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        layout.addStretch(1)

    def initialize(self) -> bool:
        self.logger.info("Field Tools module placeholder initialized")
        return super().initialize()


__all__ = ["FieldToolsModule"]
