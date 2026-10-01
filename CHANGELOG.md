# Changelog

## 0.1.0a8 — unreleased

- Add a Russian README alongside the English project overview and include both in source releases.
- Publish the project under GPL-3.0-only with repository links and private vulnerability reporting.
- Upgrade cryptography to 50.0.2 following dependency audit (CVE-2026-69247).
- Accept USF2 profile 1/4 by declared operations, limits, local transport and build identity, without a model-12 restriction.
- Retain the existing USF1 1/2–1/3 policy; require the encrypted-reply capability for server channels and reconnect on capability drift.
- Add native contract checks for T-Beam S3 Core and Heltec V3 with Firmware Builder 0.1.0a2. New hardware acceptance remains pending.
- Align CLI and module version reporting with package 0.1.0a8; check consistency in release tests and the installed-package smoke check.

## 0.1.0a7 — unreleased

- `/history` returns only archived messages, without the visible count/window/last-request summary. Empty results are silent and still respect cooldown.
- Preserve native Client History protocol headers. No firmware update or schema migration is required.

## 0.1.0a6 — unreleased

- Server-side private channel catalogue with encrypted PSKs, admin import/rotation and independent capture/replay controls.
- Channel table, modal add/edit forms with optional key replacement, and a separate remote-administration tab.
- Decode supported encrypted broadcasts without consuming node channel slots; reject ambiguous channel matches.
- Revision 3 USB host-encrypted history replies; retain revision 2 support for local channels. App-only flash, write-hash, configuration and 75-second USB checks passed; server-channel radio acceptance is pending.
- Disabled-by-default PKI allowlisted `/channel add` commands with durable replay protection and secret-free receipts.
- Preserve secret redaction on invalid API input; document master-key backup and radio acceptance limits.
- Refresh English/Russian operator guides, security/storage boundaries, versioned deployment and the source-layout audit for 0.1.0a6.

## 0.1.0a5 — unreleased

- Firmware candidate: honor the display timeout during an active USB session; retain CPU wakefulness and wake the display on local input. Flashed with configuration preserved; USB checks passed and the operator confirmed screen operation. Radio after this update has not been retested.
- Move chat refresh status next to the displayed-message count; reclaim the empty top row.
- Use consistent select-field text, spacing, chevrons, disabled and focus states across the admin.

## 0.1.0a4 — unreleased

- Load node names from the USB node database at connection so existing chat messages resolve their authors.
- Bound the initial synchronization buffer with room for node information and configuration.

## 0.1.0a3 — unreleased

- Private-channel `/history <hours>` requests using ordinary client firmware.
- Commands, including invalid syntax, are excluded from capture and replay.
- Existing sharing switch, channel isolation, message limits, pacing and cooldown apply.
- Radio settings now show maximum history in hours and separate native-client compatibility.
- One stock-client command and replayed message verified over radio on a secondary channel.

## 0.1.0a2 — unreleased

- Default administration port 18765 and required private TOML configuration.
- Password protection for all routes, failed-login throttling, and explicit LAN binding.
- systemd autostart after network readiness; isolated service account and private configuration.
- Authentication/configuration regression tests and updated deployment instructions.

## 0.1.0a1 — unreleased

- Private-channel UTF-8 capture over USB, SQLite migrations, scoped deduplication and retention.
- Local admin: paginated chats, search, database health/backups, connection and storage settings.
- English, Ukrainian and Russian interface; preserved user text and local date formatting.
- Automatic USB discovery, saved device identity, manual selection and connection status.
- Experimental off-by-default replay through a patched USB node, preserved authors and fresh packet IDs.
- Replay pacing, limits, cancellation, scope checks and durable ID ledger.
- Single-process archive ownership and worker liveness endpoint.
- Deployment/recovery/contribution instructions, package exclusions and publication checks.

This preview is not an accepted production or App Store compatibility release.
See [current status](docs/implementation-status.md).
