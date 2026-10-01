<p align="center"><img src="src/meshtastic_sf/web/static/logo.svg" width="88" alt="MeshMemo logo"></p>
<h1 align="center">MeshMemo</h1>
<p align="center"><strong>Meshtastic History Server</strong><br>Keep the conversation. A local archive for your mesh network.</p>

<p align="center"><strong>English</strong> · <a href="README.ru.md">Русский</a></p>

MeshMemo connects to a Meshtastic node over USB, saves eligible channel messages
in SQLite, and provides a local web interface for reading chats and managing the
archive. It works without a cloud account, an external database, or a frontend
build toolchain. The interface supports **English, Ukrainian and Russian**.

**Status: alpha / preview.** USB capture and administration have been
exercised on Windows and Debian with a LILYGO T-Beam Supreme. A `/history 6`
request and one replayed message were received over radio on a secondary channel
using stock client firmware. Replay remains **off by default**; iPhone display,
deduplication, server-authored replay and multi-hop acceptance are incomplete.
See [current status](docs/implementation-status.md) for the tested boundaries.

Server 0.1.0a8 supports the portable USF2 1/4 firmware contract from MeshMemo
[Firmware Builder](https://github.com/dmitryplohotnyuk/meshmemo-firmware-builder) 0.1.0a2, alongside legacy USF1 1/2–1/3. T-Beam S3 Core and
Heltec V3 have separate builder profiles; new-build hardware acceptance is
pending. See [firmware compatibility](docs/firmware-compatibility.md).

## What it does

- Archives decoded UTF-8 broadcast messages from private channels.
- Manages up to 256 server-side channel definitions without using extra node slots.
- Provides a channel table, modal add/edit forms and per-channel capture/replay controls.
- Supports optional PKI-allowlisted `/channel add` registration, disabled by default.
- Separates history by node identity and channel/radio configuration.
- Deduplicates repeat packets and preserves conflicting variants separately.
- Shows channel chats, text search, sender names and paginated history.
- Provides archive statistics, integrity checks and consistent SQLite backups.
- Supports automatic USB discovery, manual port selection and reconnection.
- Configures capture, retention, limits and experimental history sharing.
- Accepts `/history <hours>` in a private channel; commands are never archived or replayed.
- Loads sender names from the USB node database and subsequent NodeInfo announcements.
- Keeps data on the host; there is no external analytics or CDN dependency.

Direct/private messages, public/default-key channels, MQTT traffic, telemetry and
received S&F replays and `/history` or `/channel` commands (including invalid ones)
are excluded. Unknown-key encrypted packets are not archived. Pausing capture drops new messages; disconnected
periods may leave gaps. See [architecture and data rules](docs/architecture.md).

## Quick start

Use Python **3.11–3.13**. Install from a reviewed checkout; no PyPI release is
claimed. The package and command names remain `meshtastic-sf-server` for compatibility.

```sh
python -m venv .venv
# Linux / macOS shell:
. .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install -c requirements/constraints.txt .
cp deploy/config.example.toml meshmemo.toml
# Windows PowerShell: Copy-Item deploy/config.example.toml meshmemo.toml
# Set admin.password in meshmemo.toml before starting (12+ characters).
# Linux/macOS: chmod 600 meshmemo.toml
meshtastic-sf-server serve --config meshmemo.toml
```

Open **http://127.0.0.1:18765** and sign in as **admin** using the password from
your configuration file. The browser shows its built-in login dialog.
In Settings, choose automatic USB discovery or a
port from the list and apply the connection settings. A new archive starts with
USB disconnected and radio history sharing disabled.

You can seed the initial port at first startup:

```sh
meshtastic-sf-server serve --config meshmemo.toml --device /dev/serial/by-id/YOUR_NODE
# Windows: replace the device with the actual COM port, for example COM7.
```

Saved connection settings take precedence over `--device` on subsequent starts.
Use one server/capture process per archive and USB device. The server must remain
running to receive messages. Stock firmware supports capture; preserving authors
when replaying history requires the custom firmware.

## Request history

With experimental sharing explicitly enabled and compatible server firmware, send
`/history 6` as an ordinary message in the desired private channel. It requests
the last six hours, subject to the configured window, message limit and cooldown.
The command itself is visible once in the channel but is excluded from the archive
and replay. Replies use S&F and are addressed to the requesting node. Its own
messages are excluded. Sending this command requires no client firmware patch;
phone compatibility still needs acceptance. See the [user guide](docs/user-guide.md).

## Documentation

The [documentation index](docs/README.md) separates current guides from dated
research and upstream proposals.

| Task | Guide |
| --- | --- |
| Read chats, choose a port, configure storage | [User guide (English)](docs/user-guide.md) · [Русский](docs/user-guide.ru.md) |
| Add channel keys or configure administrator DMs | [Server channels](docs/server-channels.md) |
| Run as a Linux service, back up, update or restore | [Deployment and operations](docs/deployment.md) |
| Understand storage, filtering and trust boundaries | [Architecture](docs/architecture.md) |
| Select compatible MeshMemo firmware | [Current compatibility](docs/firmware-compatibility.md) · [Legacy firmware instructions](firmware/README.md) |
| Understand experimental radio replay | [Protocol and limits](docs/history-replay.md) · [Acceptance procedure](docs/hardware-acceptance.md) |
| Check readiness and unresolved work | [Audit report](docs/repository-audit.md) · [Roadmap](docs/implementation-plan.md) |
| Prepare a GitHub upload | [Publishing checklist](docs/publishing.md) |

## Operational boundaries

The admin defaults to **127.0.0.1:18765** and requires a password from a private
TOML file. HTML, assets, API, backups and health checks all require authentication.
For private LAN access, configure the server's bind IP and allowed hosts; see the
[deployment guide](docs/deployment.md). HTTP Basic authentication does not encrypt
traffic: use an SSH tunnel or HTTPS when the network is not trusted. This is a
single-operator service, without individual accounts or roles.

The archive and backups contain plaintext messages and node identifiers. Protect
the data directory with OS permissions and disk encryption as appropriate. USB
configuration frames and automatically discovered node channel keys are not
persisted. Keys explicitly registered in the server catalogue are stored encrypted
in SQLite; the separate `<database>.channels.key` master-key file is required for
restore and is not included in the admin database download. Firmware backups may
contain plaintext keys and must remain private. See [key backup](docs/server-channels.md#key-storage-and-backups).

Firmware Builder 0.1.0a2 keeps **UA22, OLED Cyrillic and display timeout** as
independent options, disabled by default. The historical `firmware/` scripts
retain their inherited profile for the previously installed T-Beam firmware.
Installation never flashes automatically.

## Development

```sh
python -m pip install -c requirements/constraints.txt -e '.[dev]'
python -m pytest
node --test tests/ui/i18n.test.cjs
python scripts/release-check.py
python -m build
```

Node.js 22+ is only needed for UI logic tests. Native C++ replay tests additionally
require the prepared firmware checkout and compiler; see [CONTRIBUTING](CONTRIBUTING.md).
Tests use synthetic data and never open physical USB ports. Hardware acceptance
is separate. Constraints record tested runtime versions, not a cross-platform,
hash-verified lockfile; validate the resolved environment on the deployment OS.

```text
src/meshtastic_sf/  domain, storage, USB transport, services and web UI
firmware/          pinned upstream references, ordered patches and bridge code
scripts/           preparation, build and publication checks
requirements/      tested dependency constraints
deploy/           example service configuration
tests/            synthetic Python, native C++ and UI tests
docs/             guides, architecture, decisions and dated research
```

Local `data/`, `.build/`, `.venv/`, `dist/` and caches are excluded from publication.
Do not publish real message screenshots, node backups or serial logs.

## Contributing and licensing

Read [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md) and
[third-party notices](THIRD_PARTY_NOTICES.md). MeshMemo is an independent project
for Meshtastic networks; it is not an official Meshtastic product.

MeshMemo is licensed under the [GNU General Public License v3.0](LICENSE)
(`GPL-3.0-only`). Firmware-derived files retain their upstream notices and
licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).
