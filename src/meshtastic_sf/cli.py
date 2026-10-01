"""Diagnostic commands for the bridge PoC. No automatic firmware writes."""

import argparse
from dataclasses import asdict
import json
import logging

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="MeshMemo — Meshtastic History Server")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe", help="Read metadata and perform the local capability handshake")
    probe.add_argument("--device", required=True)
    probe.add_argument("--profile", type=int, choices=[0, 1], default=0, help="Expected USB capability profile")
    ios = commands.add_parser("ios-probe", help="Synthetic TCP node for observing client replay deduplication")
    ios.add_argument("--bind", default="127.0.0.1")
    ios.add_argument("--port", type=int, default=4403)
    capture = commands.add_parser("capture", help="Archive USB private-channel broadcasts; radio replay disabled")
    capture.add_argument("--device", required=True)
    capture.add_argument("--database", required=True)
    capture.add_argument("--max-records", type=int, default=100_000)
    backup = commands.add_parser("backup", help="Create a consistent SQLite backup without replacing a file")
    backup.add_argument("--database", required=True)
    backup.add_argument("--output", required=True)
    serve = commands.add_parser("serve", help="Run password-protected administration and optional USB capture")
    serve.add_argument("--config", default="meshmemo.toml", help="Private TOML configuration file")
    serve.add_argument("--database", help="Override the configured archive path")
    serve.add_argument("--device", help="Initial serial port; saved connection settings take precedence")
    serve.add_argument("--port", type=int, help="Override the configured HTTP port (default: 18765)")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        import ipaddress
        from .config import load_config
        from .web.application import create_app
        try:
            config = load_config(args.config)
        except ValueError as exc:
            parser.error(str(exc))
        port = config.port if args.port is None else args.port
        if not 1 <= port <= 65535:
            parser.error("Port must be 1..65535")
        uvicorn.run(create_app(args.database or config.database, args.device,
                              admin_password=config.password, allowed_hosts=config.allowed_hosts,
                              allow_remote=not ipaddress.ip_address(config.host).is_loopback),
                    host=config.host, port=port,
                    workers=1, proxy_headers=False, access_log=False)
        return
    if args.command in {"capture", "backup"}:
        from pathlib import Path
        from sqlalchemy.exc import SQLAlchemyError
        from .storage.repository import HistoryRepository
        try:
            if args.command == "capture":
                from .services.capture import capture as run_capture
                print(json.dumps(run_capture(args.device, args.database, max_records=args.max_records)))
            else:
                if not Path(args.database).is_file():
                    raise ValueError("Source database does not exist")
                repository = HistoryRepository(args.database)
                try:
                    repository.backup(args.output)
                finally:
                    repository.close()
                print("Backup completed")
        except (OSError, RuntimeError, ValueError, SQLAlchemyError) as exc:
            # SQL errors may contain private values even if an external driver adds context.
            detail = "Database operation failed" if isinstance(exc, SQLAlchemyError) else str(exc)
            parser.exit(1, detail + "\n")
        return
    if args.command == "ios-probe":
        from .diagnostics.ios_probe import serve
        try:
            serve(args.bind, args.port)
        except (OSError, ValueError, RuntimeError, EOFError) as exc:
            parser.exit(1, f"{exc}\n")
        except KeyboardInterrupt:
            parser.exit(0, "Probe stopped\n")
        return
    logging.getLogger("meshtastic").setLevel(logging.CRITICAL)
    from .transport.client import BridgeClient, BridgeUnavailable, BridgeRejected
    from .transport.serial import BridgeSerialInterface

    try:
        radio = BridgeSerialInterface(args.device)
        try:
            if args.profile == 1:
                from .transport.replay import ReplayBridgeClient
                response = ReplayBridgeClient(radio.exchange).connect()
            else:
                response = BridgeClient(radio.exchange).connect()
            print(json.dumps(asdict(response), indent=2))
        finally:
            radio.close()
    except (BridgeUnavailable, BridgeRejected, OSError) as exc:
        parser.exit(1, f"{exc}\n")
