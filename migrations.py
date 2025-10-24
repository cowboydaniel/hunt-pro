"""Utilities for migrating persisted Hunt Pro data stores between schema versions."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from logger import get_logger


class MigrationError(Exception):
    """Raised when a migration cannot be completed safely."""


@dataclass
class MigrationOutcome:
    """Result information for a migration operation."""

    previous_version: int
    new_version: int
    backup_path: Optional[Path]


def _write_json_atomic(target: Path, payload: Dict[str, Any]) -> None:
    """Write JSON data to ``target`` using a temporary file for safety."""

    target = Path(target)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
    tmp_path.replace(target)


def _create_backup(
    source: Path,
    *,
    prefix: str,
    version: int,
    backup_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Create a timestamped backup of ``source`` and return the backup path."""

    source = Path(source)
    if not source.exists():
        return None

    if backup_dir is None:
        backup_dir = source.parent

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_name = (
        f"{source.stem}-v{version}-{prefix}-backup-{timestamp}{source.suffix}"
    )
    backup_path = backup_dir / backup_name
    shutil.copy2(source, backup_path)
    return backup_path


def migrate_game_log_store(
    file_path: Path,
    *,
    validator: Any,
    target_version: Optional[int] = None,
    logger=None,
) -> Optional[MigrationOutcome]:
    """Upgrade the game log JSON document to the latest supported schema."""

    file_path = Path(file_path)
    if target_version is None:
        target_version = int(getattr(validator, "CURRENT_VERSION"))

    if logger is None:
        logger = get_logger()

    if not file_path.exists():
        return None

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            raw_data: Any = json.load(handle)
    except json.JSONDecodeError as exc:
        raise MigrationError(
            f"Game log file '{file_path}' contains invalid JSON"
        ) from exc
    except OSError as exc:
        raise MigrationError(
            f"Unable to read game log file '{file_path}': {exc}"
        ) from exc

    try:
        schema_version, normalized_entries = validator.validate_document(raw_data)
    except Exception as exc:  # pragma: no cover - validator raises specific errors
        raise MigrationError(f"Validation failed for '{file_path}': {exc}") from exc

    metadata: Dict[str, Any] = {}
    if isinstance(raw_data, dict):
        metadata = {
            key: value
            for key, value in raw_data.items()
            if key not in {"schema_version", "entries"}
        }

    requires_migration = schema_version != target_version
    requires_rewrite = requires_migration or (
        isinstance(raw_data, dict)
        and raw_data.get("entries") != normalized_entries
    )

    if not requires_rewrite:
        return None

    timestamp = datetime.now(timezone.utc).isoformat()
    document: Dict[str, Any] = {
        **metadata,
        "schema_version": target_version,
        "entries": normalized_entries,
    }
    if requires_migration:
        document["migrated_at"] = timestamp
        document["migrated_from_version"] = schema_version

    backup_path = _create_backup(
        file_path, prefix="game-log", version=schema_version, backup_dir=file_path.parent
    )

    _write_json_atomic(file_path, document)

    logger.info(
        "Migrated game log storage",
        previous_version=schema_version,
        new_version=target_version,
        backup=str(backup_path) if backup_path else None,
    )

    return MigrationOutcome(
        previous_version=schema_version,
        new_version=target_version,
        backup_path=backup_path,
    )


def migrate_ballistic_profile_store(
    file_path: Path,
    *,
    loader: Callable[[Dict[str, Any]], Any],
    dumper: Callable[[Any], Dict[str, Any]],
    target_version: int,
    backup_dir: Optional[Path] = None,
    logger=None,
) -> Optional[MigrationOutcome]:
    """Upgrade the ballistic profile store JSON document."""

    file_path = Path(file_path)
    if logger is None:
        logger = get_logger()

    if not file_path.exists():
        return None

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            raw_data: Any = json.load(handle)
    except json.JSONDecodeError as exc:
        raise MigrationError(
            f"Ballistic profile store '{file_path}' contains invalid JSON"
        ) from exc
    except OSError as exc:
        raise MigrationError(
            f"Unable to read ballistic profile store '{file_path}': {exc}"
        ) from exc

    current_version = 0
    raw_profiles: Iterable[Dict[str, Any]]

    if isinstance(raw_data, dict):
        current_version = int(raw_data.get("version", 0))
        if "profiles" in raw_data and isinstance(raw_data["profiles"], list):
            raw_profiles = raw_data["profiles"]
        elif "entries" in raw_data and isinstance(raw_data["entries"], list):
            raw_profiles = raw_data["entries"]
        else:
            raise MigrationError(
                f"Ballistic profile store '{file_path}' is missing a profiles list"
            )
        metadata = {
            key: value
            for key, value in raw_data.items()
            if key not in {"version", "profiles", "entries"}
        }
    elif isinstance(raw_data, list):
        raw_profiles = raw_data
        metadata = {}
    else:
        raise MigrationError(
            f"Ballistic profile store '{file_path}' has an unsupported structure"
        )

    normalized_profiles = [dumper(loader(entry)) for entry in raw_profiles]

    requires_migration = current_version != target_version
    requires_rewrite = requires_migration or list(raw_profiles) != normalized_profiles

    if not requires_rewrite:
        return None

    payload: Dict[str, Any] = {
        **metadata,
        "version": target_version,
        "profiles": normalized_profiles,
    }
    if requires_migration:
        payload["migrated_at"] = datetime.now(timezone.utc).isoformat()
        payload["migrated_from_version"] = current_version

    backup_path = _create_backup(
        file_path,
        prefix="ballistics",
        version=current_version,
        backup_dir=backup_dir,
    )

    _write_json_atomic(file_path, payload)

    logger.info(
        "Migrated ballistic profile storage",
        previous_version=current_version,
        new_version=target_version,
        backup=str(backup_path) if backup_path else None,
    )

    return MigrationOutcome(
        previous_version=current_version,
        new_version=target_version,
        backup_path=backup_path,
    )

