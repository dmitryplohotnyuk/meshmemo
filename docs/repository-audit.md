# Repository audit — 2026-09-30, source 0.1.0a6

> Historical snapshot. On 2026-10-01 the 0.1.0a8 publication preparation added
> Git, the public [meshmemo repository](https://github.com/dmitryplohotnyuk/meshmemo),
> GPL-3.0-only, private vulnerability reporting and a Russian README. The
> missing-license and missing-remote findings below are therefore resolved.
> Current checks: 183 Python/native tests passed (one POSIX-only test skipped on
> Windows), two UI tests passed, and the dependency audit passed after upgrading
> cryptography to 50.0.2. Package contents and installed-wheel startup passed.
> Remote CI results are available in [Actions](https://github.com/dmitryplohotnyuk/meshmemo/actions).

**The structure is suitable for a public GitHub alpha project.** The Python src
layout separates domain rules, storage, USB transport, services and web assets.
No folder moves or separate frontend package are needed for the current project.
The workspace has no root `.git` directory or configured project remote; this
audit does not initialize, commit or publish it.

This audit updated documentation and inspected public files, build contents,
ignore rules and firmware provenance. It did not redeploy, flash, change settings
or transmit radio traffic. Earlier deployment and hardware results are recorded
in [implementation status](implementation-status.md).

## Structure

| Location | Purpose | Assessment |
| --- | --- | --- |
| `src/meshtastic_sf/` | Installable Python package, domain/storage/transport/services/web | Appropriate src layout; package boundaries already separated |
| `tests/` | Python, native C++ protocol and JS locale tests | Separate from runtime package; synthetic inputs |
| `firmware/` | Pinned provenance, ordered patches, bridge sources and upstream license | No vendored checkout or built firmware in public source |
| `deploy/` | Blank-password configuration and systemd example | Actual configuration remains private |
| `requirements/` | Tested runtime constraints | Useful reproducibility baseline, not a portable hash-verified lock |
| `scripts/` | Build/preparation, publication and deployment checks | Operational tooling separated from runtime |
| `docs/` | Guides, contract, decisions, research and upstream proposals | Indexed by purpose; current guides take precedence over dated evidence |
| `.github/` | CI, dependency updates, issue and PR templates | Prepared; not evidence that Actions has run remotely |
| Local `data/`, `.build/`, `.venv/`, `dist/`, caches | Operational data and generated output | Ignored by Git and excluded from source publication |

There is no need to split this into several repositories or add a frontend package
manager for the current plain JS/CSS UI. Historical document paths were retained
to preserve references; the documentation index now explicitly separates them from
current instructions.

## Corrections made

- README, architecture and SECURITY distinguish node-discovered keys from explicitly
  registered server keys encrypted in SQLite. Message text remains plaintext.
- English/Russian guides describe the channel table, modal add/edit forms, optional
  key replacement, separate DM tab and default-off administrator authorization.
- Backup/restore instructions include the separate `.channels.key` file. The admin
  database download does not contain this master key.
- Firmware/protocol/replay guides distinguish installed profile 1/3 from historical
  1/2 results, and host-encrypted replies from node-local replies. The documented
  text budgets are 160 and 192 UTF-8 bytes respectively.
- Hardware acceptance covers server-only channels, PKI administrator commands,
  authorization failures and key restoration. USB checks are not radio acceptance.
- Deployment instructions explain versioned environments and systemd drop-ins.
- Current version/schema/device state is summarized before historical results.

## Checks performed in this audit

| Check | Result |
| --- | --- |
| Publication allowlist and local Markdown file links | 140 public source files; no broken local file targets or matching credential signatures |
| Package build | Source distribution and wheel built successfully for 0.1.0a6 |
| Source distribution | Exactly the 140 declared source files plus PKG-INFO |
| Wheel | 54 package/metadata files; no local databases, key files, firmware binaries or bytecode |
| Runtime resources | Catalogue services/crypto, migration 0005, template and locales included |
| Git ignore rules in an isolated temporary repository | 17 private/generated path examples ignored; no declared public source file ignored |
| Firmware provenance | Seven recorded patch hashes verified |
| Focused privacy scan | No searched deployment credentials, personal workspace paths or real deployment node-ID markers in public files |
| Root Git / project license | No root Git repository; project LICENSE still missing |

The ignore checks include database/WAL/SHM, the new `.channels.key` files,
configuration, flash backups, logs, private documents, caches and build output.
Generated files may remain on disk under ignored directories; they are not part
of the publication set. Never upload the entire workspace.

Latest functional validation before this documentation-only audit: **143 Python/
native tests passed**, one Linux-only permission test skipped on Windows; two JS
locale tests passed. The installed Linux 0.1.0a6 wheel passed assets/migrations/
startup checks and dependency consistency. These tests were not unnecessarily
repeated for prose edits. The previous native and device evidence is retained.

The strict `--require-license` publication check must fail while LICENSE is absent.
The scanner checks a narrow set of secret patterns and local Markdown file targets;
external URLs, every heading anchor and absence of all possible secrets are not
certified. Review the exact staged diff before publication. CI is configured but
has not run on a project GitHub remote. No online dependency-advisory scan was
performed in this documentation audit.

## Remaining gates

1. Choose a license for newly authored code and resolve pending notices; preserve
   upstream firmware licenses. No license has been invented.
2. Choose the GitHub owner/repository, add real project URLs, and configure private
   vulnerability reporting or a private contact in SECURITY.md.
3. Initialize and review only the public source set, then run GitHub Actions.
   Follow the [publication checklist](publishing.md).
4. Complete server-channel radio/DM, phone display/deduplication, server-authored
   replay, multi-hop, whole-host reboot, soak/load, disk exhaustion and recovery
   checks before production acceptance. See [hardware acceptance](hardware-acceptance.md).

Preparing a public repository is separate from declaring this alpha production-ready.
