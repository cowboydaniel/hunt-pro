import pytest

pytest.importorskip("PySide6")
try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - executed only when Qt bindings incomplete
    pytest.skip("PySide6 QtWidgets bindings unavailable", allow_module_level=True)

from nav_map import (
    GPSCoordinate,
    NavigationModule,
    SimulatedGPSProvider,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_simulated_provider_manual_step():
    samples = [
        GPSCoordinate(35.0, -83.0, altitude=400.0, accuracy=3.0),
        GPSCoordinate(35.0005, -83.0005, altitude=401.0, accuracy=3.5),
        GPSCoordinate(35.001, -83.001, altitude=402.0, accuracy=4.0),
    ]
    provider = SimulatedGPSProvider(samples, interval_ms=None)
    captured = []

    def _capture(lat, lon, alt, acc):
        captured.append((lat, lon, alt, acc))

    provider.position_updated.connect(_capture)
    provider.start()

    for _ in samples:
        provider.manual_step()

    assert captured == [
        (pytest.approx(35.0), pytest.approx(-83.0), pytest.approx(400.0), pytest.approx(3.0)),
        (
            pytest.approx(35.0005),
            pytest.approx(-83.0005),
            pytest.approx(401.0),
            pytest.approx(3.5),
        ),
        (
            pytest.approx(35.001),
            pytest.approx(-83.001),
            pytest.approx(402.0),
            pytest.approx(4.0),
        ),
    ]
    assert not provider.is_active


def test_simulated_feed_from_track_dict():
    track_payload = [
        {
            "name": "Training lap",
            "points": [
                {
                    "coordinate": {
                        "latitude": 44.0,
                        "longitude": -85.0,
                        "altitude": 250.0,
                        "accuracy": 5.0,
                    }
                },
                {
                    "coordinate": {
                        "latitude": 44.0004,
                        "longitude": -85.0004,
                        "altitude": 251.0,
                        "accuracy": 4.5,
                    }
                },
            ],
        }
    ]

    provider = SimulatedGPSProvider.from_feed(track_payload, interval_ms=None)
    captured = []
    provider.position_updated.connect(lambda *args: captured.append(args))

    provider.start()
    provider.manual_step()
    provider.manual_step()

    assert len(captured) == 2
    assert captured[0][0] == pytest.approx(44.0)
    assert captured[1][1] == pytest.approx(-85.0004)


def test_navigation_module_use_simulated_feed(qt_app):
    module = NavigationModule()
    feed = [
        GPSCoordinate(34.1, -82.9, altitude=350.0, accuracy=2.5),
        GPSCoordinate(34.1006, -82.9006, altitude=351.0, accuracy=2.8),
    ]
    provider = module.use_simulated_gps_feed(feed, interval_ms=None)

    assert isinstance(provider, SimulatedGPSProvider)

    module.start_gps()
    provider.manual_step()

    assert module.current_position is not None
    assert module.current_position.latitude == pytest.approx(34.1)
    assert module.current_position.longitude == pytest.approx(-82.9)

    module.stop_gps()
