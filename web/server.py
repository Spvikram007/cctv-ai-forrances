"""
LAN Web Server Thread & Process Manager (Phase 15 Milestone W2).
Provides non-blocking background server execution alongside PySide6 desktop GUI
as well as standalone CLI execution.
"""

import sys
import os
import time
import argparse
import threading
from typing import Optional

import uvicorn
from web.config import web_settings
from web.api.app import app
from core.logging.logger import get_logger
from app.bootstrap import bootstrap_application

logger = get_logger("web_server")

_server_instance: Optional[uvicorn.Server] = None
_server_thread: Optional["UvicornServerThread"] = None


class UvicornServerThread(threading.Thread):
    """Executes Uvicorn in a dedicated daemon thread to prevent blocking Qt event loop."""

    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(daemon=True, name="LANWebServerThread")
        self.server = uvicorn.Server(config)

    def run(self) -> None:
        logger.info("Starting LAN Web Server thread on port %d...", self.server.config.port)
        self.server.run()

    def stop(self) -> None:
        logger.info("Stopping LAN Web Server thread...")
        self.server.should_exit = True


def start_lan_server_thread(
    host: Optional[str] = None,
    port: Optional[int] = None,
    ssl_cert: Optional[str] = None,
    ssl_key: Optional[str] = None
) -> UvicornServerThread:
    """
    Launches FastAPI / Uvicorn in a background thread.
    Can be invoked directly from app/main.py or test suites without blocking.
    """
    global _server_instance, _server_thread

    bind_host = host or web_settings.host
    bind_port = port or web_settings.port

    ssl_certfile = ssl_cert or (web_settings.ssl_cert_path if web_settings.ssl_enabled else None)
    ssl_keyfile = ssl_key or (web_settings.ssl_key_path if web_settings.ssl_enabled else None)

    # Verify SSL files if enabled
    if ssl_certfile and not os.path.exists(ssl_certfile):
        logger.warning("Configured SSL cert '%s' not found. Falling back to HTTP.", ssl_certfile)
        ssl_certfile = None
        ssl_keyfile = None

    config = uvicorn.Config(
        app=app,
        host=bind_host,
        port=bind_port,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        log_level="info",
        access_log=False
    )

    thread = UvicornServerThread(config)
    _server_instance = thread.server
    _server_thread = thread
    thread.start()

    logger.info("LAN Web Server successfully launched in background on %s:%d (SSL: %s)",
                bind_host, bind_port, bool(ssl_certfile))
    return thread


def stop_lan_server() -> None:
    """Signals background server thread to gracefully stop."""
    global _server_instance, _server_thread
    if _server_thread and _server_thread.is_alive():
        _server_thread.stop()
        _server_thread.join(timeout=3.0)
    _server_instance = None
    _server_thread = None
    logger.info("LAN Web Server stopped.")


def main():
    """Standalone CLI entry point for running the CCTV AI LAN Web Gateway."""
    parser = argparse.ArgumentParser(description="CCTV AI Intelligence Platform - LAN Web Gateway")
    parser.add_argument("--host", default=web_settings.host, help="Bind host IP address")
    parser.add_argument("--port", type=int, default=web_settings.port, help="Port to listen on")
    parser.add_argument("--ssl", action="store_true", help="Enable HTTPS")
    parser.add_argument("--cert", default=web_settings.ssl_cert_path, help="SSL certificate path")
    parser.add_argument("--key", default=web_settings.ssl_key_path, help="SSL private key path")
    args = parser.parse_args()

    # Ensure platform database and services are bootstrapped
    bootstrap_application()

    ssl_cert = args.cert if args.ssl else None
    ssl_key = args.key if args.ssl else None

    logger.info("Starting CCTV AI Web Gateway standalone on %s:%d (SSL=%s)...", args.host, args.port, args.ssl)
    uvicorn.run(
        "web.api.app:app",
        host=args.host,
        port=args.port,
        ssl_certfile=ssl_cert,
        ssl_keyfile=ssl_key,
        log_level="info",
        reload=False
    )


if __name__ == "__main__":
    main()
