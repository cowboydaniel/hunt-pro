"""Collaboration and session sharing helpers for Hunt Pro.

This module provides a light-weight collaboration layer that allows Hunt Pro
operators to share an active hunting session with teammates. The implementation
focuses on three guarantees that the roadmap calls out:

* **Secure participation** - Sessions issue time-bound join tokens that are
  validated using an HMAC signature so that only invited operators can
  contribute updates.
* **Real-time locations** - Each teammate can push periodic location updates
  which are tracked with their last seen timestamp and optional status text.
* **Event annotations** - Hunters can drop annotated events that optionally
  include geospatial context for later review or export.

The module intentionally avoids networking concerns; it only models the data
structures and validation so that higher level transports (Bluetooth, mesh,
cellular, etc.) can serialise the resulting payloads.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set


class SessionSecurityError(RuntimeError):
    """Base error raised for authentication or authorisation problems."""


class InvalidToken(SessionSecurityError):
    """Raised when a token fails integrity checks."""


class ExpiredToken(SessionSecurityError):
    """Raised when a token is presented after its expiry window."""


class PermissionDenied(SessionSecurityError):
    """Raised when a teammate attempts an action beyond their role."""


class UnknownTeammateError(KeyError):
    """Raised when an operation references a teammate that has not joined."""


@dataclass
class TeammateLocation:
    """Represents a teammate's reported position."""

    latitude: float
    longitude: float
    altitude: Optional[float] = None
    accuracy: Optional[float] = None
    heading: Optional[float] = None
    speed: Optional[float] = None
    timestamp: float = field(default_factory=lambda: time.time())

    def to_payload(self) -> Dict[str, float]:
        """Serialise the location into a transport friendly dictionary."""

        payload = {
            "lat": self.latitude,
            "lon": self.longitude,
            "ts": self.timestamp,
        }
        if self.altitude is not None:
            payload["alt"] = self.altitude
        if self.accuracy is not None:
            payload["acc"] = self.accuracy
        if self.heading is not None:
            payload["head"] = self.heading
        if self.speed is not None:
            payload["spd"] = self.speed
        return payload


@dataclass
class TeammatePresence:
    """Tracks a teammate currently joined to the shared session."""

    call_sign: str
    last_seen: float = field(default_factory=lambda: time.time())
    status: Optional[str] = None
    location: Optional[TeammateLocation] = None
    role: str = "guide"

    def to_payload(self) -> Dict[str, object]:
        """Return a serialisable representation of the presence."""

        payload: Dict[str, object] = {
            "call_sign": self.call_sign,
            "last_seen": self.last_seen,
        }
        if self.status:
            payload["status"] = self.status
        if self.location:
            payload["location"] = self.location.to_payload()
        payload["role"] = self.role
        return payload


@dataclass
class EventAnnotation:
    """Rich event describing an occurrence during the hunt."""

    author: str
    category: str
    message: str
    created_at: float = field(default_factory=lambda: time.time())
    identifier: str = field(default_factory=lambda: uuid.uuid4().hex)
    location: Optional[TeammateLocation] = None

    def to_payload(self) -> Dict[str, object]:
        """Serialise the event for transmission or storage."""

        payload: Dict[str, object] = {
            "id": self.identifier,
            "author": self.author,
            "category": self.category,
            "message": self.message,
            "created_at": self.created_at,
        }
        if self.location:
            payload["location"] = self.location.to_payload()
        return payload


class CollaborationSession:
    """Manage a secure collaborative hunt session."""

    TOKEN_VERSION = "1"
    DEFAULT_ROLE = "guide"
    VALID_ROLES: Set[str] = {"guide", "observer"}
    ROLE_PERMISSIONS = {
        "guide": {"update_location", "record_event"},
        "observer": set(),
    }

    def __init__(
        self,
        *,
        session_id: Optional[str] = None,
        secret: Optional[bytes] = None,
        allowed_clock_skew: int = 30,
    ) -> None:
        self.session_id = session_id or secrets.token_hex(8)
        self._secret = secret or secrets.token_bytes(32)
        self.allowed_clock_skew = allowed_clock_skew
        self._teammates: Dict[str, TeammatePresence] = {}
        self._events: List[EventAnnotation] = []

    # ------------------------------------------------------------------
    # Token handling
    # ------------------------------------------------------------------
    def generate_join_token(
        self,
        call_sign: str,
        *,
        expires_in: int = 300,
        role: str = DEFAULT_ROLE,
    ) -> str:
        """Create a signed invitation token for a teammate.

        Parameters
        ----------
        call_sign:
            Unique identifier of the teammate being invited.
        expires_in:
            Lifetime of the token in seconds (default five minutes).
        role:
            Permission tier granted to the teammate. ``"guide"`` (default)
            can coordinate the hunt while ``"observer"`` has read-only
            access to session telemetry.
        """

        if expires_in <= 0:
            raise ValueError("expires_in must be positive")
        if role not in self.VALID_ROLES:
            raise ValueError(f"Unknown role '{role}'. Valid roles: {sorted(self.VALID_ROLES)}")
        expiry = int(time.time() + expires_in)
        payload = {
            "v": self.TOKEN_VERSION,
            "sid": self.session_id,
            "cs": call_sign,
            "exp": expiry,
            "role": role,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
        encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"{encoded_payload}.{encoded_signature}"

    def _decode_token(self, token: str) -> Dict[str, object]:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise InvalidToken("Token must contain payload and signature") from exc
        padding = "=" * (-len(encoded_payload) % 4)
        payload_bytes = base64.urlsafe_b64decode(encoded_payload + padding)
        expected_signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        padding = "=" * (-len(encoded_signature) % 4)
        provided_signature = base64.urlsafe_b64decode(encoded_signature + padding)
        if not hmac.compare_digest(expected_signature, provided_signature):
            raise InvalidToken("Token signature mismatch")
        data = json.loads(payload_bytes.decode())
        if data.get("v") != self.TOKEN_VERSION:
            raise InvalidToken("Unsupported token version")
        if data.get("sid") != self.session_id:
            raise InvalidToken("Token issued for a different session")
        expiry = int(data.get("exp", 0))
        now = time.time()
        if now - self.allowed_clock_skew > expiry:
            raise ExpiredToken("Token has expired")
        if expiry - now > 86400 * 7:
            # Guard against obviously incorrect clocks or malicious payloads.
            raise InvalidToken("Token expiry is unreasonably far in the future")
        return data

    def _authorise(self, token: str, *, permission: Optional[str] = None) -> TeammatePresence:
        payload = self._decode_token(token)
        call_sign = str(payload.get("cs"))
        role = str(payload.get("role", self.DEFAULT_ROLE))
        if role not in self.VALID_ROLES:
            raise InvalidToken("Token specifies an unknown role")
        presence = self._teammates.get(call_sign)
        if presence is None:
            presence = TeammatePresence(call_sign=call_sign, role=role)
            self._teammates[call_sign] = presence
        else:
            presence.role = role
        presence.last_seen = time.time()
        if permission is not None:
            allowed = self.ROLE_PERMISSIONS.get(presence.role, set())
            if permission not in allowed:
                raise PermissionDenied(
                    f"Role '{presence.role}' is not permitted to perform '{permission}'"
                )
        return presence

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------
    def join(self, token: str, *, status: Optional[str] = None) -> TeammatePresence:
        """Join the session using a signed token."""

        presence = self._authorise(token)
        if status is not None:
            presence.status = status
        return presence

    def update_location(
        self,
        token: str,
        location: TeammateLocation,
        *,
        status: Optional[str] = None,
    ) -> TeammatePresence:
        """Update the location for an authorised teammate."""

        presence = self._authorise(token, permission="update_location")
        presence.location = location
        if status is not None:
            presence.status = status
        return presence

    def record_event(
        self,
        token: str,
        category: str,
        message: str,
        *,
        location: Optional[TeammateLocation] = None,
    ) -> EventAnnotation:
        """Record a new event annotation from a teammate."""

        presence = self._authorise(token, permission="record_event")
        event = EventAnnotation(
            author=presence.call_sign,
            category=category,
            message=message,
            location=location,
        )
        self._events.append(event)
        return event

    def get_teammate(self, call_sign: str) -> TeammatePresence:
        """Return a teammate by call sign or raise ``UnknownTeammateError``."""

        try:
            return self._teammates[call_sign]
        except KeyError as exc:  # pragma: no cover - thin wrapper
            raise UnknownTeammateError(call_sign) from exc

    def teammates(self) -> Iterable[TeammatePresence]:
        """Iterate over all joined teammates sorted by call sign."""

        for call_sign in sorted(self._teammates):
            yield self._teammates[call_sign]

    def events(self, *, since: Optional[float] = None) -> List[EventAnnotation]:
        """Return a list of recorded events optionally filtered by timestamp."""

        if since is None:
            return list(self._events)
        return [event for event in self._events if event.created_at >= since]

    def export_state(self) -> Dict[str, object]:
        """Export the session state for synchronisation or persistence."""

        return {
            "session_id": self.session_id,
            "teammates": [presence.to_payload() for presence in self.teammates()],
            "events": [event.to_payload() for event in self._events],
        }

