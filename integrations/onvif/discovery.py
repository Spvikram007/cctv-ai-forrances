"""
Camera Discovery Engine for CCTV AI Intelligence Platform.
Implements ONVIF WS-Discovery (multicast UDP), local subnet IP range scanning,
MAC address resolution, manufacturer fingerprinting, and duplicate elimination.
"""

import re
import uuid
import time
import socket
import select
import subprocess
import ipaddress
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.logging.logger import get_logger

logger = get_logger("camera_discovery")

# ONVIF WS-Discovery constants
WS_MULTICAST_IP = "239.255.255.250"
WS_MULTICAST_PORT = 3702

WS_DISCOVERY_PROBE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
          xmlns:dn="http://www.onvif.org/ver10/network/wsdl"
          xmlns="http://www.w3.org/2003/05/soap-envelope"
          xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">
  <Header>
    <wsa:MessageID>urn:uuid:{message_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types>dn:NetworkVideoTransmitter</Types>
    </Probe>
  </Body>
</Envelope>"""

# Common CCTV camera ports
COMMON_CAMERA_PORTS = [80, 554, 8000, 8080, 8899, 37777]


@dataclass
class DiscoveredCamera:
    """Represents a discovered surveillance device on the network."""
    ip_address: str
    onvif_port: int = 80
    rtsp_port: int = 554
    mac_address: str = "Unknown"
    manufacturer: str = "Generic ONVIF"
    model: str = "IP Camera"
    firmware_version: str = "Unknown"
    discovery_method: str = "WS_DISCOVERY"  # WS_DISCOVERY, SUBNET_SCAN, MANUAL
    xaddrs: str = ""
    scopes: List[str] = field(default_factory=list)
    has_onvif: bool = False
    has_rtsp: bool = False
    status: str = "Discovered"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CameraDiscoveryEngine:
    """Discovers ONVIF and RTSP cameras across local networks."""

    @staticmethod
    def get_arp_table() -> Dict[str, str]:
        """Reads local ARP cache to map IP addresses to MAC addresses on Windows."""
        arp_map: Dict[str, str] = {}
        try:
            output = subprocess.check_output("arp -a", shell=True, text=True, stderr=subprocess.DEVNULL)
            # Lines format: 192.168.1.100  44-19-b6-aa-bb-cc  dynamic
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    ip = parts[0]
                    mac = parts[1].replace("-", ":").upper()
                    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip) and len(mac) == 17:
                        arp_map[ip] = mac
        except Exception as e:
            logger.debug("Failed reading Windows ARP table: %s", e)
        return arp_map

    @classmethod
    def resolve_mac_address(cls, ip: str, arp_cache: Optional[Dict[str, str]] = None) -> str:
        cache = arp_cache if arp_cache is not None else cls.get_arp_table()
        return cache.get(ip, "Unknown")

    @staticmethod
    def fingerprint_manufacturer(scopes: List[str], xaddrs: str, mac: str = "") -> str:
        """Identifies camera brand from ONVIF scopes, URLs, or MAC address prefixes."""
        combined_text = " ".join(scopes).lower() + " " + xaddrs.lower()

        if "hikvision" in combined_text or mac.upper().startswith(("44:19:B6", "C0:56:E3", "BC:AD:28")):
            return "Hikvision"
        if "dahua" in combined_text or mac.upper().startswith(("3C:EF:8C", "4C:11:BF", "E0:50:8B")):
            return "Dahua"
        if "cpplus" in combined_text or "cp plus" in combined_text or "cp_plus" in combined_text:
            return "CP PLUS"
        if "axis" in combined_text:
            return "Axis"
        if "uniview" in combined_text or "uniview" in xaddrs.lower():
            return "Uniview"
        if "hanwha" in combined_text or "samsung" in combined_text:
            return "Hanwha"
        if "onvif" in combined_text:
            return "Generic ONVIF"
        return "Generic"

    @classmethod
    def parse_ws_discovery_response(cls, xml_data: str) -> Optional[DiscoveredCamera]:
        """Parses ONVIF ProbeMatch SOAP XML message into DiscoveredCamera instance."""
        try:
            clean_xml = re.sub(r'<\/?([a-zA-Z0-9_-]+:)', lambda m: '<' if not m.group(0).startswith('</') else '</', xml_data)
            clean_xml = re.sub(r'\s+xmlns(?::[a-zA-Z0-9_-]+)?="[^"]*"', '', clean_xml)
            root = ET.fromstring(clean_xml)

            # Locate ProbeMatch or ProbeMatches elements
            probe_matches = root.findall(".//ProbeMatch")
            if not probe_matches:
                probe_matches = [root] if "ProbeMatch" in root.tag else []

            for match in probe_matches:
                xaddrs_elem = match.find(".//XAddrs")
                scopes_elem = match.find(".//Scopes")

                xaddrs = xaddrs_elem.text.strip() if xaddrs_elem is not None and xaddrs_elem.text else ""
                scopes_raw = scopes_elem.text.strip() if scopes_elem is not None and scopes_elem.text else ""
                scopes = scopes_raw.split()

                if not xaddrs:
                    continue

                # Extract IP and port from XAddrs (e.g. http://192.168.1.100:80/onvif/device_service)
                url_match = re.search(r"https?://([^:/]+)(?::(\d+))?", xaddrs)
                if not url_match:
                    continue

                ip = url_match.group(1)
                port = int(url_match.group(2)) if url_match.group(2) else 80

                # Extract model from scopes if present (onvif://www.onvif.org/hardware/ModelName)
                model = "IP Camera"
                for s in scopes:
                    if "/hardware/" in s.lower():
                        model = s.split("/")[-1]
                    elif "/name/" in s.lower():
                        model = s.split("/")[-1]

                manufacturer = cls.fingerprint_manufacturer(scopes, xaddrs)

                return DiscoveredCamera(
                    ip_address=ip,
                    onvif_port=port,
                    rtsp_port=554,
                    manufacturer=manufacturer,
                    model=model,
                    discovery_method="WS_DISCOVERY",
                    xaddrs=xaddrs,
                    scopes=scopes,
                    has_onvif=True,
                    has_rtsp=True,
                )
        except Exception as e:
            logger.debug("Error parsing WS-Discovery XML packet: %s", e)
        return None

    @classmethod
    def discover_onvif_ws(cls, timeout_sec: float = 3.0) -> List[DiscoveredCamera]:
        """
        Sends WS-Discovery multicast probe and listens for camera responses.
        """
        discovered: Dict[str, DiscoveredCamera] = {}
        message_id = str(uuid.uuid4())
        probe_packet = WS_DISCOVERY_PROBE_TEMPLATE.format(message_id=message_id).encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout_sec)

        try:
            # Bind to local interface
            sock.bind(("", 0))
            sock.sendto(probe_packet, (WS_MULTICAST_IP, WS_MULTICAST_PORT))

            start_time = time.time()
            arp_cache = cls.get_arp_table()

            while time.time() - start_time < timeout_sec:
                try:
                    ready = select.select([sock], [], [], 0.5)
                    if ready[0]:
                        data, addr = sock.recvfrom(65535)
                        xml_str = data.decode("utf-8", errors="ignore")
                        cam = cls.parse_ws_discovery_response(xml_str)
                        if cam and cam.ip_address not in discovered:
                            cam.mac_address = arp_cache.get(cam.ip_address, "Unknown")
                            if cam.manufacturer == "Generic":
                                cam.manufacturer = cls.fingerprint_manufacturer(cam.scopes, cam.xaddrs, cam.mac_address)
                            discovered[cam.ip_address] = cam
                            logger.info("Discovered ONVIF camera: %s (%s - %s)", cam.ip_address, cam.manufacturer, cam.model)
                except socket.timeout:
                    break
                except Exception as e:
                    logger.debug("Socket read error during WS-Discovery: %s", e)
        finally:
            sock.close()

        return list(discovered.values())

    @classmethod
    def scan_ip_port(cls, ip: str, port: int, timeout_sec: float = 0.5) -> bool:
        """Tests whether a TCP port is open on target host."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout_sec)
                res = s.connect_ex((ip, port))
                return res == 0
        except Exception:
            return False

    @classmethod
    def scan_subnet(
        cls,
        subnet_cidr: str,
        timeout_per_host: float = 0.4,
        max_workers: int = 50,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> List[DiscoveredCamera]:
        """
        Scans a local subnet (e.g. 192.168.1.0/24) for active cameras on common surveillance ports.
        """
        discovered: Dict[str, DiscoveredCamera] = {}
        try:
            network = ipaddress.ip_network(subnet_cidr, strict=False)
            hosts = [str(ip) for ip in network.hosts()]
        except Exception as e:
            logger.error("Invalid CIDR format for subnet scan: %s", e)
            return []

        total_hosts = len(hosts)
        arp_cache = cls.get_arp_table()

        def probe_host(host_ip: str) -> Optional[DiscoveredCamera]:
            if cancel_token and cancel_token():
                return None

            open_ports = []
            for port in COMMON_CAMERA_PORTS:
                if cls.scan_ip_port(host_ip, port, timeout_sec=timeout_per_host):
                    open_ports.append(port)

            if not open_ports:
                return None

            has_rtsp = 554 in open_ports
            has_onvif = any(p in open_ports for p in [80, 8000, 8080, 8899, 37777])
            onvif_port = next((p for p in [80, 8080, 8000, 8899, 37777] if p in open_ports), 80)
            mac = arp_cache.get(host_ip, "Unknown")
            manufacturer = cls.fingerprint_manufacturer([], "", mac)

            return DiscoveredCamera(
                ip_address=host_ip,
                onvif_port=onvif_port,
                rtsp_port=554 if has_rtsp else 554,
                mac_address=mac,
                manufacturer=manufacturer,
                model="Network Camera",
                discovery_method="SUBNET_SCAN",
                has_onvif=has_onvif,
                has_rtsp=has_rtsp,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ip = {executor.submit(probe_host, ip): ip for ip in hosts}
            completed_count = 0

            for future in as_completed(future_to_ip):
                if cancel_token and cancel_token():
                    break
                completed_count += 1
                if progress_cb:
                    progress_cb(completed_count, total_hosts)

                cam = future.result()
                if cam:
                    discovered[cam.ip_address] = cam

        return list(discovered.values())

    @classmethod
    def discover_all(
        cls,
        subnet_cidr: Optional[str] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> List[DiscoveredCamera]:
        """
        Combines fast ONVIF WS-Discovery and subnet IP scanning, eliminating duplicates.
        """
        results: Dict[str, DiscoveredCamera] = {}

        # 1. WS-Discovery (fast UDP probe)
        ws_cams = cls.discover_onvif_ws(timeout_sec=2.0)
        for cam in ws_cams:
            results[cam.ip_address] = cam

        # 2. Subnet scan if CIDR is provided
        if subnet_cidr:
            subnet_cams = cls.scan_subnet(
                subnet_cidr=subnet_cidr,
                progress_cb=progress_cb,
                cancel_token=cancel_token,
            )
            for cam in subnet_cams:
                if cam.ip_address not in results:
                    results[cam.ip_address] = cam
                else:
                    # Enrich existing WS-discovered camera with MAC if available
                    if results[cam.ip_address].mac_address == "Unknown" and cam.mac_address != "Unknown":
                        results[cam.ip_address].mac_address = cam.mac_address

        return list(results.values())
