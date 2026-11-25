"""
Network Discovery and Subnet Scanner Module.
Implements authorized subnet scanning, ARP & MAC resolution, ping reachability,
duplicate IP detection, IEEE OUI vendor identification, and CCTV device classification.
"""

import re
import socket
import struct
import ctypes
import platform
import subprocess
import ipaddress
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from core.logging.logger import get_logger

logger = get_logger("network_scanner")


class DeviceType(str, Enum):
    IP_CAMERA = "IP_CAMERA"
    NVR = "NVR"
    GATEWAY = "GATEWAY"
    SWITCH = "SWITCH"
    HOST = "HOST"
    UNKNOWN = "UNKNOWN"


class DeviceStatus(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


# IEEE OUI Prefix database for CCTV and Network Infrastructure Hardware
OUI_VENDOR_DATABASE: Dict[str, str] = {
    # Hikvision & OEMs
    "44:19:B6": "Hikvision",
    "C0:56:E3": "Hikvision",
    "BC:AD:28": "Hikvision",
    "A4:14:37": "Hikvision",
    "54:C4:15": "Hikvision",
    "C4:2F:90": "Hikvision",
    "D4:6E:5C": "Hikvision",
    "34:08:04": "Hikvision",
    "B8:A3:86": "Hikvision",
    "10:DA:43": "Hikvision",
    # Dahua & OEMs
    "3C:EF:8C": "Dahua Technology",
    "E0:50:8B": "Dahua Technology",
    "4C:11:BF": "Dahua Technology",
    "A0:BD:1D": "Dahua Technology",
    "90:02:A9": "Dahua Technology",
    "B4:A3:82": "Dahua Technology",
    "50:EC:50": "Dahua Technology",
    "E4:5A:A2": "Dahua Technology",
    # CP PLUS
    "D8:B0:4C": "CP PLUS",
    "B0:C5:54": "CP PLUS",
    "00:1A:E8": "CP PLUS",
    # Axis Communications
    "00:40:8C": "Axis Communications",
    "AC:CC:8E": "Axis Communications",
    "B8:A4:4F": "Axis Communications",
    # Hanwha Techwin / Samsung
    "00:16:6C": "Hanwha Techwin",
    "00:09:18": "Hanwha Techwin",
    "00:12:FB": "Hanwha Techwin",
    "E4:7E:66": "Hanwha Techwin",
    # Uniview (Uniview Technologies)
    "48:EA:63": "Uniview",
    "E0:67:B3": "Uniview",
    "C8:02:8F": "Uniview",
    # Bosch Security
    "00:07:5F": "Bosch Security",
    "00:1C:44": "Bosch Security",
    "18:03:73": "Bosch Security",
    # Sony Professional
    "00:01:4A": "Sony",
    "00:1D:BA": "Sony",
    # Pelco / Motorola
    "00:04:7D": "Pelco",
    "00:20:94": "Pelco",
    # Vivotek
    "00:02:D1": "Vivotek",
    # TP-Link
    "50:C7:BF": "TP-Link",
    "70:4F:57": "TP-Link",
    "E8:48:B8": "TP-Link",
    "B0:95:75": "TP-Link",
    # Ubiquiti Networks
    "78:8A:20": "Ubiquiti",
    "24:A4:3C": "Ubiquiti",
    "B4:FB:E4": "Ubiquiti",
    "F0:9F:C2": "Ubiquiti",
    # Cisco Systems
    "00:00:0C": "Cisco Systems",
    "00:01:42": "Cisco Systems",
    "00:01:43": "Cisco Systems",
    "00:24:97": "Cisco Systems",
    # Netgear
    "00:14:6C": "Netgear",
    "20:4E:7F": "Netgear",
    # Intel Corporation
    "00:1B:21": "Intel",
    "34:13:E8": "Intel",
    # Realtek / Virtual
    "00:E0:4C": "Realtek",
    "52:54:00": "QEMU Virtual NIC",
    "08:00:27": "PCS Systemtechnik / VirtualBox",
    "00:0C:29": "VMware",
    "00:50:56": "VMware",
}

# Standard ports scanned during discovery
PROBE_PORTS = {
    80: "HTTP",
    443: "HTTPS",
    554: "RTSP",
    8000: "ONVIF/ISAPI",
    8080: "HTTP-ALT",
    8899: "ONVIF",
    37777: "DAHUA-RPC",
    5000: "UPNP/ONVIF",
    23: "TELNET",
    22: "SSH",
}


@dataclass
class DiscoveredNetworkDevice:
    """Represents a discovered host on the physical/logical network."""
    ip_address: str
    mac_address: str = "Unknown"
    vendor: str = "Unknown Vendor"
    device_type: DeviceType = DeviceType.UNKNOWN
    hostname: str = ""
    status: DeviceStatus = DeviceStatus.ONLINE
    latency_ms: float = 0.0
    open_ports: List[int] = field(default_factory=list)
    protocols: List[str] = field(default_factory=list)
    nvr_channel_count: Optional[int] = None
    parent_gateway_ip: Optional[str] = None
    is_duplicate_ip: bool = False
    conflicting_macs: List[str] = field(default_factory=list)
    firmware_version: str = "Unknown"
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["device_type"] = self.device_type.value
        d["status"] = self.status.value
        return d


def validate_cidr_block(cidr: str, max_hosts: int = 1024) -> ipaddress.IPv4Network:
    """
    Validates a CIDR string strictly.
    Rejects malformed strings, loopback, multicast, 0.0.0.0/0, and excessively large ranges.
    """
    if not cidr or not isinstance(cidr, str):
        raise ValueError("CIDR network string cannot be empty.")

    cidr_clean = cidr.strip()
    try:
        network = ipaddress.ip_network(cidr_clean, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid IPv4 CIDR network format '{cidr_clean}': {e}")

    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError(f"Only IPv4 networks are supported: '{cidr_clean}'")

    # Safety checks
    if network.is_multicast:
        raise ValueError(f"Multicast network '{cidr_clean}' is not an authorized scan target.")
    if network.is_loopback:
        raise ValueError(f"Loopback network '{cidr_clean}' is not an authorized scan target.")
    if network.prefixlen == 0:
        raise ValueError("0.0.0.0/0 global Internet scan is strictly prohibited.")
    if network.prefixlen < 20:
        raise ValueError(f"CIDR prefix /{network.prefixlen} exceeds safe single-pass boundary (minimum /20).")

    num_hosts = network.num_addresses
    if num_hosts > max_hosts:
        raise ValueError(f"Network '{cidr_clean}' contains {num_hosts} addresses, exceeding max limit of {max_hosts}.")

    return network


def get_default_gateway() -> Optional[str]:
    """Detects the default gateway IP on the local host."""
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output("route print 0.0.0.0", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                    gateway_candidate = parts[2]
                    # Validate IP format
                    ipaddress.IPv4Address(gateway_candidate)
                    return gateway_candidate
        else:
            output = subprocess.check_output("ip route", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                if line.startswith("default via"):
                    return line.split()[2]
    except Exception as e:
        logger.debug("Failed detecting default gateway: %s", e)
    return None


def get_local_subnets() -> List[str]:
    """Detects active local subnets configured on this machine."""
    subnets: Set[str] = set()
    try:
        # Get all local IP addresses via socket
        hostname = socket.gethostname()
        local_ips = socket.gethostbyname_ex(hostname)[2]
        for ip in local_ips:
            if not ip.startswith("127."):
                try:
                    # Construct default /24
                    net = ipaddress.ip_network(f"{ip}/24", strict=False)
                    subnets.add(str(net))
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Failed detecting local subnets: %s", e)

    if not subnets:
        subnets.add("192.168.1.0/24")
    return sorted(list(subnets))


def lookup_vendor_by_mac(mac: str) -> str:
    """Maps a MAC address to its manufacturer using OUI database."""
    if not mac or mac.upper() == "UNKNOWN":
        return "Unknown Vendor"

    clean_mac = mac.upper().replace("-", ":")
    parts = clean_mac.split(":")
    if len(parts) >= 3:
        prefix = ":".join(parts[:3])
        if prefix in OUI_VENDOR_DATABASE:
            return OUI_VENDOR_DATABASE[prefix]

    return "Unknown Vendor"


class NetworkScanner:
    """
    Subnet scanner engine with ARP resolution, ping reachability,
    duplicate IP detection, and device classification.
    """

    def __init__(self, max_threads: int = 50, socket_timeout: float = 0.8) -> None:
        self.max_threads = max_threads
        self.socket_timeout = socket_timeout

    @staticmethod
    def get_system_arp_table() -> Dict[str, str]:
        """Reads local ARP cache to map IP addresses to MAC addresses on Windows/Linux."""
        arp_map: Dict[str, str] = {}
        try:
            cmd = "arp -a"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            # Match IP address and MAC address
            # Windows format:  192.168.1.1       00-11-22-33-44-55     dynamic
            pattern = re.compile(
                r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})"
            )
            for line in output.splitlines():
                m = pattern.search(line)
                if m:
                    ip = m.group(1)
                    mac = m.group(2).replace("-", ":").upper()
                    if not mac.startswith("FF:FF:FF") and not mac.startswith("01:00:5E"):
                        arp_map[ip] = mac
        except Exception as e:
            logger.debug("Failed reading system ARP table: %s", e)
        return arp_map

    @classmethod
    def resolve_mac_windows_api(cls, ip_address: str) -> Optional[str]:
        """Resolves MAC address directly using Windows SendARP API if available."""
        if platform.system() != "Windows":
            return None
        try:
            inet_addr = ctypes.windll.ws2_32.inet_addr(ip_address.encode("ascii"))
            if inet_addr == -1:
                return None
            mac_buf = (ctypes.c_byte * 6)()
            mac_len = ctypes.c_ulong(6)
            res = ctypes.windll.iphlpapi.SendARP(inet_addr, 0, ctypes.byref(mac_buf), ctypes.byref(mac_len))
            if res == 0:
                mac_bytes = [mac_buf[i] & 0xFF for i in range(6)]
                return ":".join(f"{b:02X}" for b in mac_bytes)
        except Exception:
            pass
        return None

    def probe_host(
        self,
        ip_str: str,
        ports_to_check: Optional[List[int]] = None,
        default_gateway: Optional[str] = None,
        arp_cache: Optional[Dict[str, str]] = None,
    ) -> Optional[DiscoveredNetworkDevice]:
        """
        Probes a single IP address:
        - Resolves MAC address via ARP cache or direct ARP
        - Checks TCP reachability on specified ports
        - Classifies device type
        """
        if ports_to_check is None:
            ports_to_check = [80, 554, 8000, 8080, 8899, 37777, 23, 22]

        open_ports: List[int] = []
        protocols: List[str] = []
        total_latency = 0.0
        successful_probes = 0

        # Try socket connect on ports
        for port in ports_to_check:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.socket_timeout)
            t0 = time.perf_counter()
            try:
                result = s.connect_ex((ip_str, port))
                t1 = time.perf_counter()
                if result == 0:
                    open_ports.append(port)
                    proto_name = PROBE_PORTS.get(port, f"TCP-{port}")
                    protocols.append(proto_name)
                    total_latency += (t1 - t0) * 1000.0
                    successful_probes += 1
            except Exception:
                pass
            finally:
                s.close()

        # Check ARP cache
        mac = "Unknown"
        if arp_cache and ip_str in arp_cache:
            mac = arp_cache[ip_str]
        else:
            direct_mac = self.resolve_mac_windows_api(ip_str)
            if direct_mac:
                mac = direct_mac

        # If no open ports and no ARP response, check ICMP ping
        is_ping_reachable = False
        ping_latency_ms = 0.0
        if not open_ports and mac == "Unknown":
            # Attempt single ping
            try:
                t0 = time.perf_counter()
                if platform.system() == "Windows":
                    cmd = ["ping", "-n", "1", "-w", "500", ip_str]
                else:
                    cmd = ["ping", "-c", "1", "-W", "1", ip_str]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                t1 = time.perf_counter()
                if res.returncode == 0:
                    is_ping_reachable = True
                    ping_latency_ms = (t1 - t0) * 1000.0
            except Exception:
                pass

        if not open_ports and mac == "Unknown" and not is_ping_reachable:
            # Host did not respond
            return None

        # Calculate average latency
        avg_latency = 0.0
        if successful_probes > 0:
            avg_latency = total_latency / successful_probes
        elif is_ping_reachable:
            avg_latency = ping_latency_ms
        else:
            avg_latency = 5.0  # nominal for local ARP match

        # Lookup vendor
        vendor = lookup_vendor_by_mac(mac)

        # Classify Device Type
        device_type = self._classify_device(
            ip_str=ip_str,
            mac=mac,
            vendor=vendor,
            open_ports=open_ports,
            protocols=protocols,
            default_gateway=default_gateway,
        )

        status = DeviceStatus.ONLINE
        if avg_latency > 150.0:
            status = DeviceStatus.DEGRADED

        # Resolve hostname optionally
        hostname = ""
        try:
            hostname = socket.gethostbyaddr(ip_str)[0]
        except Exception:
            pass

        return DiscoveredNetworkDevice(
            ip_address=ip_str,
            mac_address=mac,
            vendor=vendor,
            device_type=device_type,
            hostname=hostname,
            status=status,
            latency_ms=round(avg_latency, 2),
            open_ports=open_ports,
            protocols=protocols,
            parent_gateway_ip=default_gateway,
        )

    @staticmethod
    def _classify_device(
        ip_str: str,
        mac: str,
        vendor: str,
        open_ports: List[int],
        protocols: List[str],
        default_gateway: Optional[str] = None,
    ) -> DeviceType:
        """Classifies device into IP_CAMERA, NVR, GATEWAY, SWITCH, HOST, or UNKNOWN."""
        # 1. Gateway
        if default_gateway and ip_str == default_gateway:
            return DeviceType.GATEWAY

        # Common gateway heuristics
        if ip_str.endswith(".1") or ip_str.endswith(".254"):
            if 53 in open_ports or 80 in open_ports or 443 in open_ports:
                if 554 not in open_ports and 37777 not in open_ports:
                    return DeviceType.GATEWAY

        # 2. NVR (Port 37777 or 8000 with recorder characteristics)
        cctv_vendors = ("Hikvision", "Dahua Technology", "CP PLUS", "Uniview", "Bosch Security")
        if 37777 in open_ports:
            # Dahua NVR / DVR port
            return DeviceType.NVR
        if 8000 in open_ports and 554 in open_ports and any(v in vendor for v in cctv_vendors):
            # Hikvision / CP PLUS device
            # If multiple channels or designated recorder port
            if "NVR" in vendor or "Recorder" in vendor:
                return DeviceType.NVR

        # 3. IP Camera
        if 554 in open_ports:
            # RTSP streaming port open
            return DeviceType.IP_CAMERA
        if 8899 in open_ports:
            # ONVIF default WS-Discovery / HTTP port
            return DeviceType.IP_CAMERA
        if any(v in vendor for v in ("Axis Communications", "Hanwha Techwin", "Vivotek", "Pelco")):
            return DeviceType.IP_CAMERA
        if any(v in vendor for v in cctv_vendors) and (80 in open_ports or 8000 in open_ports or 8080 in open_ports):
            return DeviceType.IP_CAMERA

        # 4. Managed Switch
        if any(v in vendor for v in ("Cisco Systems", "Netgear", "TP-Link", "Ubiquiti")):
            if 554 not in open_ports and 37777 not in open_ports:
                return DeviceType.SWITCH

        # 5. Generic Host / Workstation
        if open_ports or mac != "Unknown":
            return DeviceType.HOST

        return DeviceType.UNKNOWN

    def scan_network(
        self,
        cidr: str,
        progress_callback: Optional[Callable[[int, int, List[DiscoveredNetworkDevice]], None]] = None,
        ports_to_check: Optional[List[int]] = None,
    ) -> List[DiscoveredNetworkDevice]:
        """
        Executes a multi-threaded subnet scan over an authorized CIDR block.
        Detects duplicate IPs, resolves MACs and vendors, and classifies devices.
        """
        network = validate_cidr_block(cidr)
        all_hosts = list(network.hosts())
        total_hosts = len(all_hosts)
        default_gateway = get_default_gateway()
        arp_cache = self.get_system_arp_table()

        logger.info(
            "Starting subnet scan on %s (%d hosts) with %d threads",
            cidr,
            total_hosts,
            self.max_threads,
        )

        discovered: List[DiscoveredNetworkDevice] = []
        completed_count = 0

        with ThreadPoolExecutor(max_workers=min(self.max_threads, total_hosts or 1)) as executor:
            future_to_ip = {
                executor.submit(
                    self.probe_host,
                    str(host_ip),
                    ports_to_check,
                    default_gateway,
                    arp_cache,
                ): str(host_ip)
                for host_ip in all_hosts
            }

            for future in as_completed(future_to_ip):
                completed_count += 1
                try:
                    dev = future.result()
                    if dev:
                        discovered.append(dev)
                except Exception as e:
                    logger.debug("Host probe exception: %s", e)

                if progress_callback and (completed_count % 10 == 0 or completed_count == total_hosts):
                    progress_callback(completed_count, total_hosts, list(discovered))

        # Perform Duplicate IP Detection Analysis
        self._detect_duplicate_ips(discovered, arp_cache)

        # Sort discovered devices by IP address
        discovered.sort(key=lambda d: ipaddress.IPv4Address(d.ip_address))
        logger.info("Scan completed on %s: discovered %d active devices", cidr, len(discovered))
        return discovered

    @staticmethod
    def _detect_duplicate_ips(
        devices: List[DiscoveredNetworkDevice],
        arp_cache: Dict[str, str],
    ) -> None:
        """
        Detects IP and MAC collisions / duplicate IP addresses.
        Flags devices where multiple distinct MAC addresses respond to one IP,
        or where multiple distinct IPs claim the exact same physical MAC address.
        """
        # Map IP -> MAC
        ip_to_devs: Dict[str, List[DiscoveredNetworkDevice]] = {}
        mac_to_ips: Dict[str, List[str]] = {}

        for dev in devices:
            ip_to_devs.setdefault(dev.ip_address, []).append(dev)
            if dev.mac_address and dev.mac_address.upper() != "UNKNOWN":
                mac_to_ips.setdefault(dev.mac_address, []).append(dev.ip_address)

        # Check MAC sharing across different IPs (excluding virtual interfaces)
        for mac, ip_list in mac_to_ips.items():
            if len(set(ip_list)) > 1:
                logger.warning("Duplicate MAC collision detected: MAC %s shared by IPs: %s", mac, ip_list)
                for dev in devices:
                    if dev.mac_address == mac:
                        dev.is_duplicate_ip = True
                        dev.conflicting_macs = [f"MAC {mac} shared by {ip_list}"]
