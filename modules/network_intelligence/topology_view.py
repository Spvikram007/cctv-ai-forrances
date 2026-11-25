"""
Interactive Network Topology Visualizer Canvas.
Phase 11 (F-019).
Renders physical/logical network topologies (Gateways, Switches, NVRs, Cameras, Hosts)
using a responsive dark-surveillance QPainter canvas with zoom, pan, and node inspection.
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QWheelEvent,
    QPaintEvent,
)
from PySide6.QtWidgets import QWidget, QToolTip

from core.logging.logger import get_logger

logger = get_logger("topology_view")


class TopologyNode:
    """Represents a drawable network node in the topology canvas."""

    def __init__(
        self,
        node_id: str,
        label: str,
        ip: str,
        mac: str = "Unknown",
        vendor: str = "Unknown Vendor",
        device_type: str = "UNKNOWN",
        status: str = "ONLINE",
        latency_ms: float = 0.0,
        x: float = 0.0,
        y: float = 0.0,
        parent_id: Optional[str] = None,
    ) -> None:
        self.node_id = node_id
        self.label = label
        self.ip = ip
        self.mac = mac
        self.vendor = vendor
        self.device_type = device_type
        self.status = status
        self.latency_ms = latency_ms
        self.x = x
        self.y = y
        self.parent_id = parent_id
        self.radius = 24.0

    def contains_point(self, pt: QPointF) -> bool:
        dx = pt.x() - self.x
        dy = pt.y() - self.y
        return (dx * dx + dy * dy) <= (self.radius * self.radius)


class InteractiveTopologyCanvas(QWidget):
    """
    Custom QWidget rendering an interactive, zoomable, draggable network topology map.
    """

    node_selected = Signal(dict)
    node_double_clicked = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(400, 300)

        self.nodes: Dict[str, TopologyNode] = {}
        self.links: List[Tuple[str, str, float]] = []  # (source_id, target_id, latency_ms)

        # Pan & Zoom State
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.zoom_factor = 1.0
        self._dragging = False
        self._last_mouse_pos = QPointF(0, 0)
        self.selected_node_id: Optional[str] = None
        self.hovered_node_id: Optional[str] = None

    def reset_view(self) -> None:
        """Centers and resets zoom."""
        self.offset_x = self.width() / 2.0
        self.offset_y = self.height() / 4.0
        self.zoom_factor = 1.0
        self.update()

    def set_devices(
        self,
        devices: List[Any],
        gateway_ip: Optional[str] = None,
        nvr_mappings: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """
        Builds the topology hierarchy from discovered devices and arranges them in tiers.
        """
        self.nodes.clear()
        self.links.clear()

        # 1. Determine or create Gateway Node
        gw_id = gateway_ip or "Gateway"
        self.nodes[gw_id] = TopologyNode(
            node_id=gw_id,
            label="Gateway / Router",
            ip=gw_id,
            device_type="GATEWAY",
            status="ONLINE",
            latency_ms=1.5,
            x=0.0,
            y=0.0,
        )

        # 2. Categorize devices into tiers
        switches_and_nvrs: List[Any] = []
        cameras_and_hosts: List[Any] = []

        for d in devices:
            ip = getattr(d, "ip_address", d.get("ip_address") if isinstance(d, dict) else "")
            if ip == gw_id:
                continue
            dev_type = getattr(d, "device_type", d.get("device_type", "UNKNOWN") if isinstance(d, dict) else "UNKNOWN")
            if isinstance(dev_type, str):
                t_str = dev_type
            else:
                t_str = dev_type.value

            if t_str in ("NVR", "SWITCH"):
                switches_and_nvrs.append(d)
            else:
                cameras_and_hosts.append(d)

        # Tier 1 layout (Switches & NVRs)
        tier1_count = len(switches_and_nvrs)
        spacing_x = 160.0
        start_x_t1 = -((tier1_count - 1) * spacing_x) / 2.0 if tier1_count > 0 else 0.0

        for i, d in enumerate(switches_and_nvrs):
            ip = getattr(d, "ip_address", d.get("ip_address") if isinstance(d, dict) else "")
            vendor = getattr(d, "vendor", d.get("vendor", "Unknown") if isinstance(d, dict) else "Unknown")
            dev_type = getattr(d, "device_type", d.get("device_type", "NVR") if isinstance(d, dict) else "NVR")
            t_str = dev_type.value if hasattr(dev_type, "value") else str(dev_type)
            status = getattr(d, "status", d.get("status", "ONLINE") if isinstance(d, dict) else "ONLINE")
            s_str = status.value if hasattr(status, "value") else str(status)
            lat = float(getattr(d, "latency_ms", d.get("latency_ms", 0.0) if isinstance(d, dict) else 0.0))

            x_pos = start_x_t1 + i * spacing_x
            y_pos = 120.0

            node = TopologyNode(
                node_id=ip,
                label=f"{t_str}\n{ip}",
                ip=ip,
                vendor=vendor,
                device_type=t_str,
                status=s_str,
                latency_ms=lat,
                x=x_pos,
                y=y_pos,
                parent_id=gw_id,
            )
            self.nodes[ip] = node
            self.links.append((gw_id, ip, lat))

        # Tier 2 layout (Cameras & Hosts)
        tier2_count = len(cameras_and_hosts)
        spacing_x2 = 120.0
        start_x_t2 = -((tier2_count - 1) * spacing_x2) / 2.0 if tier2_count > 0 else 0.0

        for i, d in enumerate(cameras_and_hosts):
            ip = getattr(d, "ip_address", d.get("ip_address") if isinstance(d, dict) else "")
            vendor = getattr(d, "vendor", d.get("vendor", "Unknown") if isinstance(d, dict) else "Unknown")
            dev_type = getattr(d, "device_type", d.get("device_type", "IP_CAMERA") if isinstance(d, dict) else "IP_CAMERA")
            t_str = dev_type.value if hasattr(dev_type, "value") else str(dev_type)
            status = getattr(d, "status", d.get("status", "ONLINE") if isinstance(d, dict) else "ONLINE")
            s_str = status.value if hasattr(status, "value") else str(status)
            lat = float(getattr(d, "latency_ms", d.get("latency_ms", 0.0) if isinstance(d, dict) else 0.0))

            # Connect to mapped NVR if designated, otherwise to nearest switch or gateway
            parent = gw_id
            if nvr_mappings:
                for n_ip, c_ips in nvr_mappings.items():
                    if ip in c_ips and n_ip in self.nodes:
                        parent = n_ip
                        break
            elif switches_and_nvrs:
                # Distribute evenly across switches/NVRs
                idx = i % len(switches_and_nvrs)
                target_obj = switches_and_nvrs[idx]
                if isinstance(target_obj, dict):
                    parent = target_obj.get("ip_address", gw_id)
                else:
                    parent = getattr(target_obj, "ip_address", gw_id)

            x_pos = start_x_t2 + i * spacing_x2
            y_pos = 260.0

            node = TopologyNode(
                node_id=ip,
                label=f"{vendor}\n{ip}",
                ip=ip,
                vendor=vendor,
                device_type=t_str,
                status=s_str,
                latency_ms=lat,
                x=x_pos,
                y=y_pos,
                parent_id=parent,
            )
            self.nodes[ip] = node
            self.links.append((parent, ip, lat))

        self.reset_view()

    # Coordinates translation helpers
    def _world_to_screen(self, x: float, y: float) -> QPointF:
        sx = x * self.zoom_factor + self.offset_x
        sy = y * self.zoom_factor + self.offset_y
        return QPointF(sx, sy)

    def _screen_to_world(self, sx: float, sy: float) -> QPointF:
        wx = (sx - self.offset_x) / self.zoom_factor
        wy = (sy - self.offset_y) / self.zoom_factor
        return QPointF(wx, wy)

    def _get_node_at_screen_pos(self, pt: QPointF) -> Optional[TopologyNode]:
        world_pt = self._screen_to_world(pt.x(), pt.y())
        for node in self.nodes.values():
            if node.contains_point(world_pt):
                return node
        return None

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Background Fill (Dark Surveillance Palette)
        painter.fillRect(self.rect(), QColor("#0d1117"))

        # 2. Draw Subtle Grid Pattern
        grid_color = QColor("#161b22")
        painter.setPen(QPen(grid_color, 1, Qt.DotLine))
        grid_spacing = int(40 * self.zoom_factor)
        if grid_spacing >= 15:
            start_x = int(self.offset_x) % grid_spacing
            start_y = int(self.offset_y) % grid_spacing
            w, h = self.width(), self.height()
            for x in range(start_x, w, grid_spacing):
                painter.drawLine(x, 0, x, h)
            for y in range(start_y, h, grid_spacing):
                painter.drawLine(0, y, w, y)

        # 3. Draw Links / Connections
        for src_id, dst_id, latency in self.links:
            src_node = self.nodes.get(src_id)
            dst_node = self.nodes.get(dst_id)
            if not src_node or not dst_node:
                continue

            p1 = self._world_to_screen(src_node.x, src_node.y)
            p2 = self._world_to_screen(dst_node.x, dst_node.y)

            # Link color based on target status
            link_color = QColor("#30363d")
            if dst_node.status == "ONLINE":
                link_color = QColor("#238636") if latency < 50.0 else QColor("#d29922")
            elif dst_node.status == "OFFLINE":
                link_color = QColor("#da3633")

            pen = QPen(link_color, max(1.5, 2.0 * self.zoom_factor))
            painter.setPen(pen)

            # Draw curved or straight connection
            painter.drawLine(p1, p2)

            # Draw Latency Pill Box on Link
            mid_x = (p1.x() + p2.x()) / 2.0
            mid_y = (p1.y() + p2.y()) / 2.0
            if self.zoom_factor >= 0.7:
                badge_text = f"{latency:.0f}ms"
                painter.setFont(QFont("Segoe UI", int(8 * self.zoom_factor)))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor("#161b22")))
                pill_rect = QRectF(mid_x - 18, mid_y - 8, 36, 16)
                painter.drawRoundedRect(pill_rect, 4, 4)
                painter.setPen(QPen(QColor("#8b949e")))
                painter.drawText(pill_rect, Qt.AlignCenter, badge_text)

        # 4. Draw Nodes
        for node in self.nodes.values():
            screen_pt = self._world_to_screen(node.x, node.y)
            r = node.radius * self.zoom_factor

            # Outer ring color based on status
            ring_color = QColor("#3fb950")  # Green
            if node.status == "DEGRADED":
                ring_color = QColor("#d29922")  # Amber
            elif node.status == "OFFLINE":
                ring_color = QColor("#f85149")  # Red

            # Node body color based on device type
            body_color = QColor("#21262d")
            icon_char = "●"
            if node.device_type == "GATEWAY":
                body_color = QColor("#0284c7")
                icon_char = "GW"
            elif node.device_type == "NVR":
                body_color = QColor("#7c3aed")
                icon_char = "NVR"
            elif node.device_type == "SWITCH":
                body_color = QColor("#2563eb")
                icon_char = "SW"
            elif node.device_type == "IP_CAMERA":
                body_color = QColor("#0f766e")
                icon_char = "CAM"
            elif node.device_type == "HOST":
                body_color = QColor("#334155")
                icon_char = "PC"

            # Selection Highlight
            if node.node_id == self.selected_node_id:
                painter.setPen(QPen(QColor("#58a6ff"), 4 * self.zoom_factor))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(screen_pt, r + 6 * self.zoom_factor, r + 6 * self.zoom_factor)

            # Node Circle
            painter.setPen(QPen(ring_color, 2 * self.zoom_factor))
            painter.setBrush(QBrush(body_color))
            painter.drawEllipse(screen_pt, r, r)

            # Node Text / Icon
            painter.setPen(QPen(QColor("#ffffff")))
            painter.setFont(QFont("Segoe UI", int(9 * self.zoom_factor), QFont.Bold))
            text_rect = QRectF(screen_pt.x() - r, screen_pt.y() - r, r * 2, r * 2)
            painter.drawText(text_rect, Qt.AlignCenter, icon_char)

            # Label below Node (IP & Vendor)
            if self.zoom_factor >= 0.6:
                painter.setFont(QFont("Segoe UI", int(8 * self.zoom_factor)))
                painter.setPen(QPen(QColor("#c9d1d9")))
                label_rect = QRectF(screen_pt.x() - 60 * self.zoom_factor, screen_pt.y() + r + 4, 120 * self.zoom_factor, 32)
                painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, f"{node.ip}\n{node.vendor[:14]}")

    # Mouse Interaction Handlers
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            clicked_node = self._get_node_at_screen_pos(event.position())
            if clicked_node:
                self.selected_node_id = clicked_node.node_id
                self.node_selected.emit(
                    {
                        "node_id": clicked_node.node_id,
                        "ip": clicked_node.ip,
                        "mac": clicked_node.mac,
                        "vendor": clicked_node.vendor,
                        "device_type": clicked_node.device_type,
                        "status": clicked_node.status,
                        "latency_ms": clicked_node.latency_ms,
                    }
                )
                self.update()
            else:
                self._dragging = True
                self._last_mouse_pos = event.position()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            delta = event.position() - self._last_mouse_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self._last_mouse_pos = event.position()
            self.update()
        else:
            hovered = self._get_node_at_screen_pos(event.position())
            if hovered and hovered.node_id != self.hovered_node_id:
                self.hovered_node_id = hovered.node_id
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"<b>{hovered.ip}</b><br/>Type: {hovered.device_type}<br/>Vendor: {hovered.vendor}<br/>Latency: {hovered.latency_ms:.1f}ms<br/>Status: {hovered.status}",
                    self,
                )
            elif not hovered:
                self.hovered_node_id = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        clicked_node = self._get_node_at_screen_pos(event.position())
        if clicked_node:
            self.node_double_clicked.emit(
                {
                    "node_id": clicked_node.node_id,
                    "ip": clicked_node.ip,
                    "mac": clicked_node.mac,
                    "vendor": clicked_node.vendor,
                    "device_type": clicked_node.device_type,
                }
            )

    def wheelEvent(self, event: QWheelEvent) -> None:
        zoom_delta = 1.15 if event.angleDelta().y() > 0 else 0.85
        new_zoom = max(0.4, min(3.0, self.zoom_factor * zoom_delta))

        mouse_screen = event.position()
        world_pt = self._screen_to_world(mouse_screen.x(), mouse_screen.y())

        self.zoom_factor = new_zoom
        self.offset_x = mouse_screen.x() - world_pt.x() * self.zoom_factor
        self.offset_y = mouse_screen.y() - world_pt.y() * self.zoom_factor
        self.update()
