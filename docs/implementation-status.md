# Implementation status — 2026-09-30

MeshMemo is an **alpha publication candidate**. Current source and guides supersede
earlier plans. Dated compatibility snapshots are historical evidence, not statements
about the latest upstream release.

## Current versions

| Component | Recorded state |
| --- | --- |
| Server source | 0.1.0a8; database schema 0005_catalog unchanged |
| Last recorded deployed package | 0.1.0a7; no deployment performed during portable-contract work |
| USB node | Meshtastic 2.7.26, profile 1/revision 3; flashed 2026-09-30 |
| Latest device check | Write hash, unchanged settings/channels, 75-second USB test passed |
| Server-only channel radio / administrator DMs | Implemented; hardware acceptance pending |

The firmware check used the node attached to the development PC. Subsequent USB
reconnection to the deployed server was verified during the 0.1.0a7 upgrade.
Older device and deployment checks below remain dated evidence.

Source 0.1.0a8 adds the portable USF2 1/4 handshake from Firmware Builder
0.1.0a2, retaining legacy 1/2–1/3 support. Native checks cover real IDs 12 and 43;
new firmware USB/radio checks remain pending. See [compatibility](firmware-compatibility.md).

On 2026-10-01, [portable hardware preflight](portable-hardware-preflight-2026-10-01.md)
confirmed the existing deployment's USB connection through its status API. The
T-Beam image with all three inherited options was built and checked against a
historical flash backup. Server/node updates await SSH access; no device was
flashed. CLI/module version reporting was aligned with package 0.1.0a8.

## Implemented and locally exercised

- USB configuration handshake, private-channel filtering and SQLite persistence.
- Scoped deduplication, collision preservation, retention and packaged migrations.
- Password-protected admin on port 18765, explicit LAN binding, paginated chats/search,
  backups, connection settings and three languages.
- Automatic/manual USB connection and reconnect status.
- Experimental profile 1 replay, fresh IDs/ledger, validation, limits and cancellation; disabled by default.
- Single-process archive ownership and worker liveness endpoint.
- Windows capture from another physical node into a private channel observed in the admin.
- Debian systemd deployment: restricted service account, autostart, recovery after
  process failure, authenticated administration and live Private capture into SQLite.
- S&F discovery observed on iOS after repeating the heartbeat; client-history request
  reproduced on hardware and rejected because firmware changes it to PKI/channel 0.
  See [diagnostic evidence and compatibility options](history-replay.md).

- `/history <hours>` command: private-channel broadcast, shared replay limits,
  no command capture/replay. One response text received over radio on the expected
  secondary channel with stock client firmware; command excluded from the database.

- Node names loaded from the USB node database on connection; existing messages
  resolve their authors. Verified on the deployed 0.1.0a4 service.

The T-Beam Supreme application was updated to profile 1 revision 2 with the USB
polling fix. App-only flashing preserved configuration; local HELLO passed.
Inherited UA22 and OLED Cyrillic support fit and were retained. Flash backups
and configuration comparisons remain private local data.

A subsequent [USB screen-timeout candidate](../firmware/README.md#usb-screen-timeout-candidate)
was built on 2026-09-30 with the same profile 1/revision 2 wire protocol. It is
flashed app-only after a full backup and live partition verification. Write hash,
configuration/channel preservation and USB HELLO passed. OLED/E-Ink host FSM
checks and clean patch reconstruction passed. The operator confirmed screen
operation after the timeout/button-wake check. HELLO succeeded through 92 seconds
of the USB check, then the operator unplugged the device. Concurrent radio capture
with the display off has not been retested after this update.


## Not yet accepted

- Phone display, repeated requests without duplicates, server-authored replay and multi-hop behavior on hardware.
- The specific App Store client after the upstream fix. Prior iOS 2.7.22 (2395) produced duplicates; a merged fix is not acceptance.
- Reboot of the whole Linux host and extended USB reconnect/soak acceptance.
- Sustained load, disk exhaustion/recovery and operational backup/restore drills.

The project uses GPL-3.0-only. Its public repository is
[dmitryplohotnyuk/meshmemo](https://github.com/dmitryplohotnyuk/meshmemo), with
private vulnerability reporting enabled. This does not change radio acceptance.

Offline results are in the [repository audit](repository-audit.md).
They do not replace [hardware acceptance](hardware-acceptance.md).

## Server channel catalogue — 0.1.0a6

Implemented server key storage, admin management/import, host-side encrypted
broadcast decoding, per-channel policy, host-encrypted history replies and PKI
allowlisted `/channel add` registration (off by default). Details and bounds:
[server channels](server-channels.md). Firmware 1/3 was flashed app-only on 2026-09-30 after a full backup and live
partition verification. Write-hash, configuration preservation and 75 seconds
of USB checks passed. New-channel radio reception/replay and real-client DM
registration remain pending.

The home-server deployment was upgraded to 0.1.0a6 on 2026-09-30 using a separate
virtual environment and a systemd override. The previous environment and a
protected pre-migration database/config backup were retained. Schema migration
to 0005_catalog, archive integrity, existing record count, authenticated HTTP,
USB reconnection, enabled startup and new table/modal assets passed. Remote DM
administration remains disabled and the server catalogue is initially empty.
Offline validation: 143 tests passed on Windows, one Linux-only permissions test
skipped; two JavaScript tests passed. The installed Linux package smoke check
and dependency consistency check passed. These do not establish radio acceptance.

## Quiet chat-command replies — 0.1.0a7

`/history` returns only archived texts; the visible ROUTER_HISTORY count/window/
last-request summary is omitted. Empty results are silent but still consume the
request cooldown. Native Client History keeps its header, including empty results.
No firmware or schema change was required. Deployed on 2026-09-30 with a protected
pre-upgrade backup and retained previous environment. Authenticated HTTP, archive
integrity, unchanged record count, USB connection and enabled service passed.
145 Python/native tests passed, one platform-specific test skipped; the installed
Linux wheel smoke test and dependency check passed. One initial Windows TCP probe
teardown failed with ConnectionAbortedError; the full rerun passed. A new radio
request after this deployment has not yet been observed.
