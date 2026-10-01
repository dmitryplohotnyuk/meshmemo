"""Private TOML configuration. Passwords are never accepted on the command line."""

from dataclasses import dataclass, field
import ipaddress
import os
from pathlib import Path
import tomllib

DEFAULT_PORT = 18765


@dataclass(frozen=True)
class ServerConfig:
    password: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    database: str = "data/history.db"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")


def load_config(filename: str) -> ServerConfig:
    path = Path(filename).resolve()
    try:
        if os.name != "nt" and path.stat().st_mode & 0o027:
            raise ValueError("Config permissions must be 0600 or 0640")
        with path.open("rb") as source:
            data = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError):
        # TOML errors can contain the line with the password.
        raise ValueError("Cannot read config; check path, permissions and TOML syntax") from None
    if set(data) - {"server", "admin"}:
        raise ValueError("Unknown configuration section")
    server, admin = data.get("server", {}), data.get("admin", {})
    if not isinstance(server, dict) or not isinstance(admin, dict):
        raise ValueError("server and admin must be TOML tables")
    if set(server) - {"host", "port", "database", "allowed_hosts"} or set(admin) - {"password"}:
        raise ValueError("Unknown configuration option")
    password = admin.get("password")
    if not isinstance(password, str) or not 12 <= len(password.strip()) <= 256:
        raise ValueError("Set admin.password to a unique password of at least 12 characters")
    host = server.get("host", "127.0.0.1")
    if not isinstance(host, str):
        raise ValueError("server.host must be an IP address")
    try:
        ipaddress.ip_address(host)
    except (ValueError, TypeError):
        raise ValueError("server.host must be a local IP address or a wildcard bind address") from None
    port = server.get("port", DEFAULT_PORT)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("server.port must be an integer from 1 to 65535")
    hosts = server.get("allowed_hosts", ["127.0.0.1", "localhost", "[::1]"])
    if (not isinstance(hosts, list) or not hosts or
            any(not isinstance(h, str) or not h or any(c in h for c in "*/@?# ") for h in hosts)):
        raise ValueError("server.allowed_hosts must list explicit hostnames or IP addresses")
    database = server.get("database", "data/history.db")
    if not isinstance(database, str) or not database.strip():
        raise ValueError("server.database must be a file path")
    return ServerConfig(password, host, port, str((path.parent / database).resolve()), tuple(hosts))
