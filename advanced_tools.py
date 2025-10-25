"""Placeholder Advanced Tools module for Hunt Pro."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from logger import get_logger
from main import BaseModule


class AdvancedToolsModule(BaseModule):
    """Provide a simple placeholder while advanced tools are in development."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.logger = get_logger()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Advanced Tools Coming Soon")
        title.setObjectName("advancedToolsTitle")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)

        message = QLabel(
            "The Advanced Tools workspace is not yet available in this build. "
            "Expect ballistics integrations, environmental overlays, and smart "
            "assistants in a future release."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        layout.addStretch(1)

    def initialize(self) -> bool:
        self.logger.info("Advanced Tools module placeholder initialized")
        return super().initialize()


__all__ = ["AdvancedToolsModule"]
