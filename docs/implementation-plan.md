# Roadmap and release gates

## Product scope

MeshMemo receives private-channel conversations through a USB node, stores them
in SQLite and provides a local admin. The optional patched node serves bounded
history snapshots through S&F while preserving authors. iOS acceptance comes first;
Android follows separately.

The repository is intended to be public. Keep the src layout, clear package
boundaries, explicit firmware patches, synthetic tests and operational guides.
Private archives, configuration, device backups and working documents are local
operator data, not source assets.

## Completed foundation

Capture/storage, password-protected admin, three locales, pagination, USB discovery,
node-name synchronization, `/history <hours>` and replay controls are implemented.
Debian service deployment and one secondary-channel radio response were exercised. Replay defaults to off. Inherited firmware changes including OLED
Cyrillic support are retained. See [status](implementation-status.md) and
[architecture](architecture.md).

## Before GitHub publication

1. Select a license compatible with included/required upstream material; preserve notices.
2. Review the explicit source bundle and staged diff for private information.
3. Run offline/native tests, package smoke check and dependency audit.
4. Configure private vulnerability reporting, repository description and CI policies.
5. Publish as alpha/preview with known limitations.

See [publishing](publishing.md). File preparation does not publish a repository
or grant a license.

## Before operational acceptance

1. Validate capture, reconnect, ownership and recovery on the target Linux/Windows host.
2. Exercise backups, restore and upgrades on copies; verify permissions and disk monitoring.
3. Record the installed App Store version/build and complete [radio acceptance](hardware-acceptance.md).
4. Test Android separately and report exact tested versions.
5. Run sustained load, queue pressure and disk-failure recovery checks.

Multi-user administration and role-based access, automatic firmware installation,
unbounded archive paging over radio and distributed databases are outside this
release scope and require separate design/security review.

## Server channel catalogue (approved 2026-09-30)

Implemented: encrypted channel-key catalogue, admin registration/import and key
replacement, separate capture/history controls, host decryption, USB revision 3
host-encrypted replies, and default-off PKI administrator registration by DM.
Commands are excluded from message history. See [server channels](server-channels.md).

The candidate was flashed on 2026-09-30; configuration preservation and USB checks passed.
Remaining acceptance: verify capture and `/history 6` from a channel absent from the node's local channel list,
then test authorized and unauthorized administrator DMs. Keep remote registration
off until administrator public keys have been pinned. Hardware results must be
recorded separately from offline tests; no blind unknown-key archive is included.
