"""
Single-Use, Short-Lived WebSocket Ticket Manager.
Prevents exposure of long-lived session tokens in URL query strings or server access logs.
Tickets expire within 60 seconds and are invalidated immediately upon first use.
"""

import time
import secrets
import threading
from typing import Dict, Optional, Tuple


class WebSocketTicketManager:
    """Thread-safe manager for short-lived, single-use WebSocket authentication tickets."""

    def __init__(self, default_lifetime_seconds: int = 60) -> None:
        self.default_lifetime_seconds = default_lifetime_seconds
        # ticket -> (user_id, session_token, expires_at)
        self._tickets: Dict[str, Tuple[str, str, float]] = {}
        self._lock = threading.Lock()

    def create_ticket(self, user_id: str, session_token: str, lifetime_seconds: Optional[int] = None) -> str:
        """Issues a new cryptographic single-use ticket."""
        lifetime = lifetime_seconds or self.default_lifetime_seconds
        ticket = secrets.token_urlsafe(32)
        expires_at = time.time() + lifetime

        with self._lock:
            self._cleanup_expired()
            self._tickets[ticket] = (user_id, session_token, expires_at)

        return ticket

    def consume_ticket(self, ticket: str) -> Optional[Tuple[str, str]]:
        """
        Validates and immediately consumes a ticket (single-use guarantee).
        Returns (user_id, session_token) if valid and not expired, else None.
        """
        if not ticket:
            return None

        now = time.time()
        with self._lock:
            record = self._tickets.pop(ticket, None)
            if not record:
                return None

            user_id, session_token, expires_at = record
            if expires_at < now:
                return None

            return user_id, session_token

    def _cleanup_expired(self) -> None:
        """Removes expired tickets from memory."""
        now = time.time()
        expired = [t for t, (_, _, exp) in self._tickets.items() if exp < now]
        for t in expired:
            self._tickets.pop(t, None)


# Global singleton ticket manager
ws_ticket_manager = WebSocketTicketManager()
