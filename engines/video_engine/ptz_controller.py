"""
Universal PTZ Controller Engine.
Provides a unified, thread-safe, non-blocking interface for Pan-Tilt-Zoom operations
across ONVIF Profile S/T cameras, Hikvision ISAPI, Dahua CGI, and simulated test streams.
"""

import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from integrations.onvif.client import (
    ONVIFClient, PTZCapabilities, PTZPreset, PTZDirection, PTZUnsupportedError
)
from core.events.event_bus import bus
from core.logging.logger import get_logger

logger = get_logger("ptz_controller")


@dataclass
class PTZCameraBinding:
    channel_id: str
    channel_number: int = 1
    onvif_client: Optional[ONVIFClient] = None
    vendor_adapter: Optional[Any] = None
    profile_token: str = "Profile_1"
    is_simulated: bool = False
    cached_capabilities: Optional[PTZCapabilities] = None
    cached_presets: List[PTZPreset] = field(default_factory=list)
    simulated_pan: float = 0.0
    simulated_tilt: float = 0.0
    simulated_zoom: float = 0.0


class PTZController:
    """
    Universal PTZ Controller orchestrating PTZ commands across multiple camera channels.
    All operations are non-blocking or can be dispatched asynchronously.
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, PTZCameraBinding] = {}
        self._lock = threading.RLock()

    def register_camera(
        self,
        channel_id: str,
        channel_number: int = 1,
        onvif_client: Optional[ONVIFClient] = None,
        vendor_adapter: Optional[Any] = None,
        profile_token: str = "Profile_1",
        is_simulated: bool = False,
    ) -> PTZCameraBinding:
        """Registers a camera channel with its PTZ transport client."""
        with self._lock:
            binding = PTZCameraBinding(
                channel_id=channel_id,
                channel_number=channel_number,
                onvif_client=onvif_client,
                vendor_adapter=vendor_adapter,
                profile_token=profile_token,
                is_simulated=is_simulated or (onvif_client is None and vendor_adapter is None),
            )
            self._bindings[channel_id] = binding
            logger.info("Registered PTZ binding for [%s] (simulated=%s)", channel_id, binding.is_simulated)
            return binding

    def unregister_camera(self, channel_id: str) -> None:
        """Removes a camera channel binding."""
        with self._lock:
            if channel_id in self._bindings:
                del self._bindings[channel_id]

    def get_capabilities(self, channel_id: str) -> PTZCapabilities:
        """Inspects or returns cached PTZ capabilities for a channel."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return PTZCapabilities(has_ptz=False)

            if binding.cached_capabilities is not None:
                return binding.cached_capabilities

            if binding.is_simulated:
                caps = PTZCapabilities(
                    has_ptz=True,
                    supports_continuous=True,
                    supports_relative=True,
                    supports_absolute=True,
                    supports_presets=True,
                    supports_home=True,
                )
                binding.cached_capabilities = caps
                return caps

            if binding.onvif_client:
                caps = binding.onvif_client.ptz_get_capabilities(binding.profile_token)
                binding.cached_capabilities = caps
                return caps

            if binding.vendor_adapter and hasattr(binding.vendor_adapter, "ptz_supported"):
                has_ptz = binding.vendor_adapter.ptz_supported()
                caps = PTZCapabilities(
                    has_ptz=has_ptz,
                    supports_continuous=has_ptz,
                    supports_presets=has_ptz,
                    supports_home=has_ptz,
                )
                binding.cached_capabilities = caps
                return caps

            return PTZCapabilities(has_ptz=False)

    def continuous_move(
        self,
        channel_id: str,
        pan: float = 0.0,
        tilt: float = 0.0,
        zoom: float = 0.0,
        timeout_sec: Optional[float] = None,
    ) -> bool:
        """Issues continuous movement speed vectors (-1.0 to 1.0)."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                binding.simulated_pan += pan * 0.1
                binding.simulated_tilt += tilt * 0.1
                binding.simulated_zoom += zoom * 0.1
                bus.publish("ptz.moved", {"channel_id": channel_id, "pan": pan, "tilt": tilt, "zoom": zoom})
                return True

            if binding.onvif_client:
                try:
                    binding.onvif_client.ptz_continuous_move(
                        profile_token=binding.profile_token,
                        pan=pan,
                        tilt=tilt,
                        zoom=zoom,
                        timeout_sec=timeout_sec,
                    )
                    bus.publish("ptz.moved", {"channel_id": channel_id, "pan": pan, "tilt": tilt, "zoom": zoom})
                    return True
                except PTZUnsupportedError as e:
                    logger.warning("PTZ continuous move unsupported on [%s]: %s", channel_id, e)
                    return False
                except Exception as e:
                    logger.error("PTZ continuous move failed on [%s]: %s", channel_id, e)
                    return False

            if binding.vendor_adapter and hasattr(binding.vendor_adapter, "ptz_control"):
                direction = "STOP"
                if pan > 0:
                    direction = "RIGHT"
                elif pan < 0:
                    direction = "LEFT"
                elif tilt > 0:
                    direction = "UP"
                elif tilt < 0:
                    direction = "DOWN"
                elif zoom > 0:
                    direction = "ZOOM_IN"
                elif zoom < 0:
                    direction = "ZOOM_OUT"

                speed_int = max(1, min(7, int(max(abs(pan), abs(tilt), abs(zoom)) * 7)))
                success = binding.vendor_adapter.ptz_control(
                    channel=binding.channel_number,
                    command=direction,
                    action="start",
                    speed=speed_int,
                )
                if success:
                    bus.publish("ptz.moved", {"channel_id": channel_id, "direction": direction})
                return success

            return False

    def relative_move(
        self,
        channel_id: str,
        pan: float = 0.0,
        tilt: float = 0.0,
        zoom: float = 0.0,
        speed: float = 1.0,
    ) -> bool:
        """Issues relative translation vector movement."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                binding.simulated_pan += pan
                binding.simulated_tilt += tilt
                binding.simulated_zoom += zoom
                bus.publish("ptz.moved", {"channel_id": channel_id, "type": "relative", "pan": pan, "tilt": tilt, "zoom": zoom})
                return True

            if binding.onvif_client:
                try:
                    binding.onvif_client.ptz_relative_move(
                        profile_token=binding.profile_token,
                        pan=pan,
                        tilt=tilt,
                        zoom=zoom,
                        speed=speed,
                    )
                    bus.publish("ptz.moved", {"channel_id": channel_id, "type": "relative"})
                    return True
                except Exception as e:
                    logger.warning("RelativeMove failed on [%s]: %s", channel_id, e)
                    return False

            return False

    def absolute_move(
        self,
        channel_id: str,
        pan: float = 0.0,
        tilt: float = 0.0,
        zoom: float = 0.0,
        speed: float = 1.0,
    ) -> bool:
        """Issues absolute position coordinate movement."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                binding.simulated_pan = pan
                binding.simulated_tilt = tilt
                binding.simulated_zoom = zoom
                bus.publish("ptz.moved", {"channel_id": channel_id, "type": "absolute", "pan": pan, "tilt": tilt, "zoom": zoom})
                return True

            if binding.onvif_client:
                try:
                    binding.onvif_client.ptz_absolute_move(
                        profile_token=binding.profile_token,
                        pan=pan,
                        tilt=tilt,
                        zoom=zoom,
                        speed=speed,
                    )
                    bus.publish("ptz.moved", {"channel_id": channel_id, "type": "absolute"})
                    return True
                except Exception as e:
                    logger.warning("AbsoluteMove failed on [%s]: %s", channel_id, e)
                    return False

            return False

    def stop(self, channel_id: str) -> bool:
        """Halts all active PTZ movement on a channel."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                bus.publish("ptz.stopped", {"channel_id": channel_id})
                return True

            if binding.onvif_client:
                binding.onvif_client.ptz_stop(profile_token=binding.profile_token)
                bus.publish("ptz.stopped", {"channel_id": channel_id})
                return True

            if binding.vendor_adapter and hasattr(binding.vendor_adapter, "ptz_control"):
                success = binding.vendor_adapter.ptz_control(
                    channel=binding.channel_number,
                    command="STOP",
                    action="stop",
                )
                bus.publish("ptz.stopped", {"channel_id": channel_id})
                return success

            return False

    def move_direction(
        self,
        channel_id: str,
        direction: PTZDirection,
        speed: float = 0.5,
    ) -> bool:
        """Issues movement in standard 8 directions, zoom, or stop."""
        speed = max(0.1, min(1.0, float(speed)))

        if direction == PTZDirection.STOP:
            return self.stop(channel_id)

        pan_map = {
            PTZDirection.LEFT: -speed,
            PTZDirection.RIGHT: speed,
            PTZDirection.UP_LEFT: -speed * 0.707,
            PTZDirection.UP_RIGHT: speed * 0.707,
            PTZDirection.DOWN_LEFT: -speed * 0.707,
            PTZDirection.DOWN_RIGHT: speed * 0.707,
        }
        tilt_map = {
            PTZDirection.UP: speed,
            PTZDirection.DOWN: -speed,
            PTZDirection.UP_LEFT: speed * 0.707,
            PTZDirection.UP_RIGHT: speed * 0.707,
            PTZDirection.DOWN_LEFT: -speed * 0.707,
            PTZDirection.DOWN_RIGHT: -speed * 0.707,
        }
        zoom_map = {
            PTZDirection.ZOOM_IN: speed,
            PTZDirection.ZOOM_OUT: -speed,
        }

        pan = pan_map.get(direction, 0.0)
        tilt = tilt_map.get(direction, 0.0)
        zoom = zoom_map.get(direction, 0.0)

        return self.continuous_move(channel_id, pan=pan, tilt=tilt, zoom=zoom)

    def get_presets(self, channel_id: str) -> List[PTZPreset]:
        """Queries presets for channel."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return []

            if binding.is_simulated:
                return list(binding.cached_presets)

            if binding.onvif_client:
                presets = binding.onvif_client.ptz_get_presets(profile_token=binding.profile_token)
                binding.cached_presets = presets
                return presets

            return []

    def set_preset(self, channel_id: str, preset_name: str, preset_token: Optional[str] = None) -> Optional[str]:
        """Saves current position as preset."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return None

            if binding.is_simulated:
                token = preset_token or f"pre_{len(binding.cached_presets) + 1}"
                new_preset = PTZPreset(token=token, name=preset_name)
                binding.cached_presets.append(new_preset)
                bus.publish("ptz.preset_saved", {"channel_id": channel_id, "token": token, "name": preset_name})
                return token

            if binding.onvif_client:
                try:
                    token = binding.onvif_client.ptz_set_preset(
                        profile_token=binding.profile_token,
                        preset_name=preset_name,
                        preset_token=preset_token,
                    )
                    self.get_presets(channel_id)
                    bus.publish("ptz.preset_saved", {"channel_id": channel_id, "token": token, "name": preset_name})
                    return token
                except Exception as e:
                    logger.error("SetPreset failed on [%s]: %s", channel_id, e)
                    return None

            return None

    def goto_preset(self, channel_id: str, preset_token: str, speed: float = 1.0) -> bool:
        """Navigates to preset."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                bus.publish("ptz.preset_reached", {"channel_id": channel_id, "token": preset_token})
                return True

            if binding.onvif_client:
                try:
                    binding.onvif_client.ptz_goto_preset(
                        profile_token=binding.profile_token,
                        preset_token=preset_token,
                        speed=speed,
                    )
                    bus.publish("ptz.preset_reached", {"channel_id": channel_id, "token": preset_token})
                    return True
                except Exception as e:
                    logger.error("GotoPreset failed on [%s]: %s", channel_id, e)
                    return False

            return False

    def remove_preset(self, channel_id: str, preset_token: str) -> bool:
        """Deletes preset."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                binding.cached_presets = [p for p in binding.cached_presets if p.token != preset_token]
                return True

            if binding.onvif_client:
                success = binding.onvif_client.ptz_remove_preset(
                    profile_token=binding.profile_token,
                    preset_token=preset_token,
                )
                if success:
                    self.get_presets(channel_id)
                return success

            return False

    def goto_home_position(self, channel_id: str, speed: float = 1.0) -> bool:
        """Navigates to home position."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                binding.simulated_pan = 0.0
                binding.simulated_tilt = 0.0
                binding.simulated_zoom = 0.0
                bus.publish("ptz.home_reached", {"channel_id": channel_id})
                return True

            if binding.onvif_client:
                try:
                    binding.onvif_client.ptz_goto_home_position(
                        profile_token=binding.profile_token,
                        speed=speed,
                    )
                    bus.publish("ptz.home_reached", {"channel_id": channel_id})
                    return True
                except Exception as e:
                    logger.warning("GotoHomePosition failed on [%s]: %s", channel_id, e)
                    return False

            return False

    def set_home_position(self, channel_id: str) -> bool:
        """Sets current position as home position."""
        with self._lock:
            binding = self._bindings.get(channel_id)
            if not binding:
                return False

            if binding.is_simulated:
                return True

            if binding.onvif_client:
                try:
                    binding.onvif_client.ptz_set_home_position(profile_token=binding.profile_token)
                    return True
                except Exception as e:
                    logger.warning("SetHomePosition failed on [%s]: %s", channel_id, e)
                    return False

            return False

    def dispatch_async(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Dispatches any PTZ function call to a background daemon thread."""
        threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


# Global universal PTZ controller singleton
ptz_controller = PTZController()
