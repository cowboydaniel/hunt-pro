"""Tests for the map tile caching utility."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from map_tile_cache import MapTileCache, TileFetchError, TileSource


def test_get_tile_downloads_and_caches(tmp_path):
    """Tiles should be saved locally so future requests use the cache."""

    payload = b"tile-bytes"
    calls = []

    def fake_fetcher(zoom: int, x: int, y: int, mode: str):
        calls.append((zoom, x, y, mode))
        return payload

    cache = MapTileCache(cache_dir=tmp_path, tile_fetcher=fake_fetcher)

    tile = cache.get_tile(12, 1234, 5678, "map")
    assert tile.source is TileSource.NETWORK
    assert tile.path.read_bytes() == payload
    assert calls == [(12, 1234, 5678, "map")]

    # Manifest should record the download timestamp.
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest[tile.key]
    assert entry["source"] == TileSource.NETWORK.value

    # A subsequent call should not hit the fetcher and should report the cache.
    calls.clear()
    cached_tile = cache.get_tile(12, 1234, 5678, "map")
    assert cached_tile.source is TileSource.CACHE
    assert not calls
    # Ensure the cached timestamp remains recent.
    assert cached_tile.last_updated <= datetime.now() + timedelta(seconds=1)


def test_get_tile_falls_back_when_fetch_fails(tmp_path):
    """If fetching a tile fails we should persist the fallback image."""

    def failing_fetcher(*_args, **_kwargs):  # pragma: no cover - intentionally raises
        raise TileFetchError("no network")

    fallback_bytes = b"fallback"
    cache = MapTileCache(
        cache_dir=tmp_path,
        tile_fetcher=failing_fetcher,
        fallback_bytes=fallback_bytes,
    )

    tile = cache.get_tile(10, 100, 200, "map")
    assert tile.source is TileSource.FALLBACK
    assert tile.path.read_bytes() == fallback_bytes

    # Subsequent loads should continue to report the fallback source.
    second_tile = cache.get_tile(10, 100, 200, "map")
    assert second_tile.source is TileSource.FALLBACK


@pytest.mark.parametrize(
    "latitude,longitude,zoom,expected",
    [
        (0.0, 0.0, 1, (1, 1)),
        (37.7749, -122.4194, 12, (655, 1583)),
        (51.5074, -0.1278, 10, (511, 340)),
    ],
)
def test_coordinate_to_tile(latitude, longitude, zoom, expected, tmp_path):
    cache = MapTileCache(tile_fetcher=lambda *args: b"x", cache_dir=tmp_path / "tiles")
    x, y = cache.coordinate_to_tile(latitude, longitude, zoom)
    assert (x, y) == expected

