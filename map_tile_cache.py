"""Utility for caching map tiles with offline fallback support."""

from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from logger import LoggableMixin


class TileSource(Enum):
    """Origin of a map tile image."""

    CACHE = "cache"
    NETWORK = "network"
    FALLBACK = "fallback"


class TileFetchError(RuntimeError):
    """Raised when a tile cannot be downloaded from the network."""


@dataclass
class CachedTile:
    """Represents the outcome of fetching a tile."""

    key: str
    path: Path
    source: TileSource
    last_updated: datetime


TileFetcher = Callable[[int, int, int, str], Optional[bytes]]

# A tiny 1x1 PNG that we upscale inside the UI when no real tile data exists.
_FALLBACK_TILE_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
)


class MapTileCache(LoggableMixin):
    """Manage map tile downloads and provide offline fallbacks."""

    DEFAULT_TILE_SERVERS: Dict[str, str] = {
        "map": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        # Terrain and satellite fall back to the street map tiles for now.
        "satellite": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "terrain": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "compass": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    }

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        tile_fetcher: Optional[TileFetcher] = None,
        fallback_bytes: bytes = _FALLBACK_TILE_BYTES,
        timeout: float = 3.0,
    ) -> None:
        super().__init__()
        self.cache_dir = cache_dir or Path.home() / "HuntPro" / "map_tiles"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_file = self.cache_dir / "manifest.json"
        self._manifest: Dict[str, Dict[str, str]] = {}
        self._load_manifest()
        self.tile_fetcher: TileFetcher = tile_fetcher or self._default_fetcher
        self._fallback_bytes = fallback_bytes
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Manifest handling
    # ------------------------------------------------------------------
    def _load_manifest(self) -> None:
        if not self._manifest_file.exists():
            self._manifest = {}
            return
        try:
            data = json.loads(self._manifest_file.read_text())
            self._manifest = data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            self.log_warning("Failed to read map tile manifest", exception=exc)
            self._manifest = {}

    def _save_manifest(self) -> None:
        try:
            self._manifest_file.write_text(json.dumps(self._manifest, indent=2))
        except OSError as exc:
            self.log_warning("Failed to persist map tile manifest", exception=exc)

    # ------------------------------------------------------------------
    # Tile operations
    # ------------------------------------------------------------------
    def _tile_key(self, zoom: int, x: int, y: int, mode: str) -> str:
        return f"{mode}_{zoom}_{x}_{y}"

    def _tile_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.png"

    def coordinate_to_tile(self, latitude: float, longitude: float, zoom: int) -> tuple[int, int]:
        """Convert WGS84 coordinates to the XYZ tile space."""

        lat_rad = math.radians(latitude)
        n = 2.0 ** zoom
        x = int((longitude + 180.0) / 360.0 * n)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        return x, y

    def get_tile(self, zoom: int, x: int, y: int, mode: str) -> CachedTile:
        """Return a cached tile, downloading it if necessary."""

        mode_key = mode.lower()
        key = self._tile_key(zoom, x, y, mode_key)
        tile_path = self._tile_path(key)

        if key in self._manifest and tile_path.exists():
            entry = self._manifest[key]
            stored_source = entry.get("source", TileSource.CACHE.value)
            source = TileSource.FALLBACK if stored_source == TileSource.FALLBACK.value else TileSource.CACHE
            timestamp_str = entry.get("last_updated")
            try:
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.fromtimestamp(tile_path.stat().st_mtime)
            except (ValueError, OSError):
                timestamp = datetime.fromtimestamp(tile_path.stat().st_mtime)
            self.log_debug(
                "Loaded tile from cache",
                source=source.value,
                zoom=zoom,
                x=x,
                y=y,
                mode=mode_key,
            )
            return CachedTile(key=key, path=tile_path, source=source, last_updated=timestamp)

        try:
            payload = self.tile_fetcher(zoom, x, y, mode_key)
            if not payload:
                raise TileFetchError("empty tile payload")
            tile_path.write_bytes(payload)
            source = TileSource.NETWORK
            self.log_info(
                "Downloaded tile and cached for offline use",
                zoom=zoom,
                x=x,
                y=y,
                mode=mode_key,
                size=len(payload),
            )
        except (TileFetchError, OSError) as exc:
            self.log_warning(
                "Falling back to offline placeholder tile",
                exception=exc,
                zoom=zoom,
                x=x,
                y=y,
                mode=mode_key,
            )
            tile_path.write_bytes(self._fallback_bytes)
            source = TileSource.FALLBACK

        timestamp = datetime.now()
        self._manifest[key] = {
            "source": source.value,
            "last_updated": timestamp.isoformat(),
        }
        self._save_manifest()
        return CachedTile(key=key, path=tile_path, source=source, last_updated=timestamp)

    # ------------------------------------------------------------------
    # Default network fetcher
    # ------------------------------------------------------------------
    def _default_fetcher(self, zoom: int, x: int, y: int, mode: str) -> Optional[bytes]:
        template = self.DEFAULT_TILE_SERVERS.get(mode) or self.DEFAULT_TILE_SERVERS["map"]
        url = template.format(z=zoom, x=x, y=y, mode=mode)
        try:
            with urlopen(url, timeout=self.timeout) as response:
                if response.status != 200:
                    raise TileFetchError(f"unexpected status code: {response.status}")
                return response.read()
        except (URLError, HTTPError) as exc:
            raise TileFetchError(str(exc)) from exc


__all__ = ["MapTileCache", "TileSource", "CachedTile", "TileFetchError"]

