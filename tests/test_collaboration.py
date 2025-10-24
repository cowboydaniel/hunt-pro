import time

import pytest

from collaboration import (
    CollaborationSession,
    ExpiredToken,
    InvalidToken,
    PermissionDenied,
    TeammateLocation,
)


def test_join_and_presence_tracking():
    session = CollaborationSession(session_id="session-123", secret=b"secret-key")
    token = session.generate_join_token("Falcon", expires_in=120)

    presence = session.join(token, status="On station")

    assert presence.call_sign == "Falcon"
    assert presence.status == "On station"
    # Joining again should refresh last seen but keep state
    earlier = presence.last_seen
    time.sleep(0.01)
    presence = session.join(token)
    assert presence.last_seen >= earlier


def test_location_updates_and_export_state():
    session = CollaborationSession(session_id="session-abc", secret=b"key")
    token = session.generate_join_token("Raven", expires_in=60)
    session.join(token)

    location = TeammateLocation(latitude=45.0, longitude=-111.2, altitude=1500.0)
    session.update_location(token, location, status="Tracking herd")

    exported = session.export_state()
    assert exported["session_id"] == "session-abc"
    assert exported["teammates"][0]["status"] == "Tracking herd"
    assert exported["teammates"][0]["location"]["lat"] == pytest.approx(45.0)
    assert exported["teammates"][0]["role"] == "guide"


def test_event_annotations_capture_context():
    session = CollaborationSession(session_id="session-events", secret=b"events")
    token = session.generate_join_token("Viper", expires_in=30)
    session.join(token)

    location = TeammateLocation(latitude=44.9, longitude=-110.9, heading=87.0)
    event = session.record_event(
        token,
        category="Sighting",
        message="Bull elk spotted moving north",
        location=location,
    )

    assert event.author == "Viper"
    assert event.location.heading == pytest.approx(87.0)
    assert session.events()[-1].identifier == event.identifier


def test_tokens_are_time_bound():
    session = CollaborationSession(secret=b"bounded", allowed_clock_skew=0)
    token = session.generate_join_token("Heron", expires_in=1)

    time.sleep(1.2)
    with pytest.raises(ExpiredToken):
        session.join(token)


def test_invalid_signature_is_rejected():
    session = CollaborationSession(secret=b"integrity")
    token = session.generate_join_token("Osprey")

    tampered = token.replace(token[-2:], "aa")
    with pytest.raises(InvalidToken):
        session.join(tampered)


def test_role_permissions_enforced():
    session = CollaborationSession(session_id="session-role", secret=b"role")
    guide_token = session.generate_join_token("Orion", role="guide", expires_in=60)
    observer_token = session.generate_join_token("Lyra", role="observer", expires_in=60)

    guide_presence = session.join(guide_token)
    assert guide_presence.role == "guide"

    observer_presence = session.join(observer_token, status="Listening")
    assert observer_presence.role == "observer"
    assert observer_presence.status == "Listening"

    location = TeammateLocation(latitude=42.0, longitude=-109.0)
    session.update_location(guide_token, location)
    session.record_event(guide_token, category="Call", message="Move to ridge")

    with pytest.raises(PermissionDenied):
        session.update_location(observer_token, location)

    with pytest.raises(PermissionDenied):
        session.record_event(observer_token, category="Note", message="Saw elk")


def test_unknown_role_rejected():
    session = CollaborationSession(secret=b"role-check")

    with pytest.raises(ValueError):
        session.generate_join_token("Vega", role="commander")

