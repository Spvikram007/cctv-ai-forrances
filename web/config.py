"""
Web Gateway Configuration and Dynamic LAN Subnet Filtering.
"""

import os
import ipaddress
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class WebSettings(BaseModel):
    """Dynamic configuration for the CCTV AI FastAPI Web Server."""
    host: str = Field(default_factory=lambda: os.getenv("CCTV_WEB_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("CCTV_WEB_PORT", "8443")))
    ssl_enabled: bool = Field(default_factory=lambda: os.getenv("CCTV_SSL_ENABLED", "false").lower() in ("true", "1"))
    ssl_cert_path: Optional[str] = Field(default_factory=lambda: os.getenv("CCTV_SSL_CERT", "storage/vault/cctv_server.crt"))
    ssl_key_path: Optional[str] = Field(default_factory=lambda: os.getenv("CCTV_SSL_KEY", "storage/vault/cctv_server.key"))
    
    # Session & Cookie Security
    session_cookie_name: str = "cctv_session"
    cookie_secure: bool = Field(default_factory=lambda: os.getenv("CCTV_COOKIE_SECURE", "false").lower() in ("true", "1"))
    cookie_samesite: Literal["lax", "none", "strict"] = "lax"  # Lax allows navigation while guarding against cross-site POSTs
    session_lifetime_minutes: int = 30

    # Dynamic LAN Subnets whitelist (Never hardcoded to a single IP)
    # Default covers standard private LAN RFC 1918 subnets + loopback
    allowed_subnets: List[str] = Field(
        default_factory=lambda: [
            s.strip() for s in os.getenv(
                "CCTV_ALLOWED_SUBNETS",
                "127.0.0.1/32,::1/128,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12"
            ).split(",") if s.strip()
        ]
    )

    # CORS settings
    cors_allowed_origins: List[str] = Field(
        default_factory=lambda: [
            o.strip() for o in os.getenv(
                "CCTV_CORS_ORIGINS",
                "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,https://localhost:8443"
            ).split(",") if o.strip()
        ]
    )

    def is_ip_allowed(self, client_ip: str) -> bool:
        """
        Validates if client IP belongs to an authorized LAN subnet.
        Supports both IPv4 and IPv6 loopback / LAN formats.
        """
        if not client_ip:
            return False

        # In-process test client
        if client_ip in ("testclient", "localhost"):
            return True

        # Clean IPv6-mapped IPv4 e.g. '::ffff:192.168.1.5'
        if client_ip.startswith("::ffff:"):
            client_ip = client_ip[7:]

        try:
            ip_obj = ipaddress.ip_address(client_ip)
            for subnet_str in self.allowed_subnets:
                try:
                    network = ipaddress.ip_network(subnet_str, strict=False)
                    if ip_obj in network:
                        return True
                except ValueError:
                    continue
            return False
        except ValueError:
            return False

    def is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Validates if WebSocket or HTTP Origin is permitted."""
        if not origin:
            return True
        if origin in self.cors_allowed_origins or "*" in self.cors_allowed_origins:
            return True
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            hostname = parsed.hostname or ""
            return self.is_ip_allowed(hostname)
        except Exception:
            return False


# Singleton web settings
web_settings = WebSettings()
