"""Validation helpers for Hunt Pro configuration workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class ValidationIssue:
    """Represents a configuration validation problem."""

    field: str
    title: str
    message: str


def _coerce_int(value: Any) -> int | None:
    """Best-effort conversion to ``int`` returning ``None`` on failure."""

    if isinstance(value, bool):
        # ``bool`` is a subclass of ``int`` in Python, but we treat it as invalid
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def validate_configuration(
    settings: Dict[str, Any], *, available_modules: Iterable[str]
) -> List[ValidationIssue]:
    """Validate a configuration payload.

    Parameters
    ----------
    settings:
        Mapping of configuration keys to values gathered from the UI.
    available_modules:
        Names of all modules that can be toggled by the user.

    Returns
    -------
    list[ValidationIssue]
        A collection of validation issues. An empty list denotes success.
    """

    issues: List[ValidationIssue] = []

    call_sign = str(settings.get("call_sign", "")).strip()
    if not call_sign:
        issues.append(
            ValidationIssue(
                field="call_sign",
                title="Call Sign Required",
                message=(
                    "Provide an operator call sign. It appears in synced logs, device pairings, "
                    "and shared sessions."
                ),
            )
        )
    else:
        if len(call_sign) < 3:
            issues.append(
                ValidationIssue(
                    field="call_sign",
                    title="Call Sign Too Short",
                    message="Use at least three characters so teammates can quickly recognize you.",
                )
            )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", call_sign):
            issues.append(
                ValidationIssue(
                    field="call_sign",
                    title="Unsupported Characters",
                    message=(
                        "Use letters, numbers, underscores, or hyphens. Spaces and special symbols "
                        "can cause sync mismatches."
                    ),
                )
            )

    retention_value = _coerce_int(settings.get("log_retention"))
    if retention_value is None:
        issues.append(
            ValidationIssue(
                field="log_retention",
                title="Retention Value Invalid",
                message="Log retention must be a number between 7 and 365 days.",
            )
        )
    elif not 7 <= retention_value <= 365:
        issues.append(
            ValidationIssue(
                field="log_retention",
                title="Retention Out of Range",
                message="Choose a retention window between 7 and 365 days to preserve compliance records.",
            )
        )

    font_scale_value = _coerce_int(settings.get("font_scale"))
    if font_scale_value is None:
        issues.append(
            ValidationIssue(
                field="font_scale",
                title="Font Scale Invalid",
                message="Font scaling must be a numeric percentage between 80 and 140.",
            )
        )
    elif not 80 <= font_scale_value <= 140:
        issues.append(
            ValidationIssue(
                field="font_scale",
                title="Font Scale Out of Range",
                message="Choose a font scale between 80% and 140% for optimal readability.",
            )
        )

    modules_state = settings.get("modules", {})
    enabled_modules = [name for name in available_modules if modules_state.get(name, False)]
    if not enabled_modules:
        issues.append(
            ValidationIssue(
                field="modules",
                title="No Modules Enabled",
                message="Enable at least one module so Hunt Pro can provide field capabilities on launch.",
            )
        )

    auto_backup_enabled = bool(settings.get("auto_backup", False))
    prompt_before_sync = bool(settings.get("prompt_before_sync", False))
    if prompt_before_sync and not auto_backup_enabled:
        issues.append(
            ValidationIssue(
                field="prompt_before_sync",
                title="Cellular Prompt Needs Backup",
                message="Enable automatic backups before requiring confirmation over cellular data.",
            )
        )

    return issues

