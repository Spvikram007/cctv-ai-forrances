"""
Thread-Safe WebSocket Hub and EventBus Integration Bridge.
Multiplexes real-time surveillance alarms, stream telemetry, and system events
to authenticated browser clients without blocking the PySide6 Qt event loop.
"""

import asyncio
import json
from typing import Set, Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect, status
from core.events.event_bus import bus, Event
from core.security.user_service import user_service
from core.logging.logger import get_logger

logger = get_logger("websocket_hub")


class WebSocketHub:
    """Manages active WebSocket client connections and bridges the EventBus."""

    def __init__(self) -> None:
        self._active_connections: Set[WebSocket] = set()
        self._user_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_subscribed = False

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Sets the ASGI asyncio event loop for thread-safe cross-thread dispatching."""
        self._event_loop = loop
        if not self._is_subscribed:
            # Subscribe to all EventBus topics via wildcard
            bus.subscribe("*", self._on_eventbus_event)
            self._is_subscribed = True
            logger.info("WebSocketHub successfully bridged to central EventBus.")

    def _on_eventbus_event(self, event: Event) -> None:
        """
        Synchronous callback triggered by EventBus from any background thread.
        Dispatches payload into the asyncio event loop safely without blocking.
        """
        if not self._event_loop or not self._event_loop.is_running():
            return

        payload = {
            "topic": event.topic,
            "data": event.data,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source
        }

        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._event_loop)
        except Exception as e:
            logger.debug("Failed to dispatch EventBus message to WebSocket loop: %s", e)

    async def connect(self, websocket: WebSocket, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Authenticates and registers a new WebSocket connection.
        Closes socket with 4401 if token is invalid or expired.
        """
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing session token.")
            return None

        # Ensure event loop is bound for cross-thread EventBus bridging
        if self._event_loop is None or not self._event_loop.is_running():
            try:
                loop = asyncio.get_running_loop()
                self.set_event_loop(loop)
            except RuntimeError:
                pass

        session_data = user_service.validate_session(token)
        if not session_data:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired session.")
            return None

        await websocket.accept()

        user_id = session_data["user_id"]
        async with self._lock:
            self._active_connections.add(websocket)
            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()
            self._user_connections[user_id].add(websocket)

        logger.info("WebSocket client connected: User '%s' (Active Sockets: %d)",
                    session_data["username"], len(self._active_connections))

        # Send initial connected greeting
        await websocket.send_json({
            "event": "connected",
            "user_id": user_id,
            "username": session_data["username"],
            "role": session_data.get("role_name", "Viewer")
        })

        return session_data

    async def disconnect(self, websocket: WebSocket, user_id: Optional[str] = None) -> None:
        """Removes a disconnected client cleanly."""
        async with self._lock:
            if websocket in self._active_connections:
                self._active_connections.remove(websocket)
            if user_id and user_id in self._user_connections:
                if websocket in self._user_connections[user_id]:
                    self._user_connections[user_id].remove(websocket)
                if not self._user_connections[user_id]:
                    del self._user_connections[user_id]

        logger.info("WebSocket client disconnected. (Remaining Sockets: %d)", len(self._active_connections))

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcasts a JSON message to all active authenticated client sockets."""
        if not self._active_connections:
            return

        dead_sockets = []
        async with self._lock:
            sockets_to_send = list(self._active_connections)

        for ws in sockets_to_send:
            try:
                await ws.send_json(message)
            except Exception:
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                for ws in dead_sockets:
                    if ws in self._active_connections:
                        self._active_connections.remove(ws)


# Global WebSocket hub singleton
ws_hub = WebSocketHub()
