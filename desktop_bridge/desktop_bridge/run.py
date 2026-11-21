#!/usr/bin/env python3
"""
Desktop Bridge Runner - Start the Desktop Bridge service.
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from desktop_bridge.config import settings
from desktop_bridge.main import app


def setup_logging(debug: bool = False):
    """Configure logging."""
    level = logging.DEBUG if debug else logging.INFO
    
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "desktop_bridge.log")
        ]
    )


def main():
    parser = argparse.ArgumentParser(description="Desktop Bridge Runner")
    parser.add_argument("--host", default=settings.bridge_host, help="Host to bind")
    parser.add_argument("--port", type=int, default=settings.bridge_port, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    parser.add_argument("--port-scan", action="store_true", help="Scan serial ports and exit")
    
    args = parser.parse_args()
    
    setup_logging(args.debug)
    
    if args.port_scan:
        from desktop_bridge.device.serial_manager import SerialManager
        ports = SerialManager.list_ports()
        print("Available serial ports:")
        for port in ports:
            print(f"  {port['device']}: {port['description']} (VID:{port['vid']}, PID:{port['pid']})")
        return
    
    # Override settings from args
    if args.host:
        settings.bridge_host = args.host
    if args.port:
        settings.bridge_port = args.port
    
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║                  DESKTOP BRIDGE v1.0.0                      ║
║  Industrial Inspection & Desk Buddy Integration Layer      ║
╠═══════════════════════════════════════════════════════════╣
║  Host: {settings.bridge_host:<45} ║
║  Port: {settings.bridge_port:<45} ║
║  Serial: {settings.serial_port:<43} ║
║  Backend: {settings.backend_url:<42} ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    import uvicorn
    uvicorn.run(
        "desktop_bridge.main:app",
        host=settings.bridge_host,
        port=settings.bridge_port,
        reload=args.reload,
        log_level="debug" if args.debug else "info"
    )


if __name__ == "__main__":
    main()