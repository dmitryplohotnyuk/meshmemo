# Server-side channels

MeshMemo 0.1.0a6 adds a server channel catalogue. It does not write channel slots,
keys or modem settings to the USB node. Up to 256 private channel definitions are
supported on the node's current frequency/preset. This is not a multi-frequency receiver.

## Add and manage channels

Open **Server channels → Channels** in the authenticated admin. Channels appear
in a table. Choose **Add channel** to open the modal, then enter the exact channel name
(1–11 UTF-8 bytes) and a Base64-encoded 16- or 32-byte private PSK, or import an
HTTPS `meshtastic.org/e/` link containing exactly one channel. Multi-channel links
are rejected instead of silently changing unrelated channels or LoRa settings.
Public/default key aliases are not eligible.

Each channel has independent capture and replay switches. The global capture and
replay settings still apply. Adding a channel defaults to capture on, replay off.
Use **Edit** to change a channel in a modal. Leave the key empty to keep it.
Turn both capture and replay off to disable the definition. Changing a name or key creates a different
archive scope; old messages remain readable in their old archive and are not
served using the replacement key. Existing node channels continue to work.
If a definition matches a channel on the USB node, its policy applies to that
local channel without duplicating ingestion.

A configured server channel is decrypted on the server when the USB firmware
forwards its encrypted broadcast packet. The node must allow unknown channels
through its rebroadcast policy; LOCAL_ONLY/KNOWN_ONLY can prevent reception.
Channel-hash collisions are resolved by trying eligible keys and validating the
supported payload. Ambiguous results are dropped. Meshtastic channel AES-CTR
has no authentication tag; this does not add authenticity to channel traffic.
Messages and `/history` requests retain the protocol's existing trust limitations.

Unknown-key packets are **not stored** by this feature. There is no retroactive
archive recovery unless a separate encrypted-packet archive is implemented later.
Channel commands and history commands, including invalid commands, are excluded
from the message archive. Direct messages and telemetry remain excluded.

## History over radio

Existing local channels support USB profile 1/revision 2 or 3. Server-only channel
replay requires **profile 1/revision 3**, built with patch 0006. The host constructs
Store & Forward replies, reserves fresh outer packet IDs, retains the original
message ID/author, encrypts the complete Data payload and submits it over USB.
The node checks the current LoRa configuration digest, packet bounds, unicast
destination, TX enablement, airtime and queue capacity before submission. An older
bridge fails closed for this operation; it does not fall back to a wrong channel.

For this first version, server-only replay texts are limited to **160 UTF-8 bytes**
by the USB command budget. Larger texts remain archived but are omitted from radio
history; they are never truncated. The ordinary local-channel budget stays 192.
Server-only channels have no discovery heartbeat: use `/history 6` in the channel.
Pacing, deduplication, cooldown and cancellation use the shared replay service.
USB acceptance is not an RF acknowledgement. Stock-client radio acceptance for
server-only channels remains pending; it must be tested before claiming compatibility.

## Add through a direct message

Under **Server channels → Manage through direct messages**, register the administrator's actual
32-byte public key in Base64, then enable administrator commands. The switch is
initially off. Public keys must be verified through a trusted path; a node number
or advertised name is insufficient.

Send an end-to-end PKI encrypted DM to the server USB node:

```text
/channel add Private BASE64_KEY
```

Replace `BASE64_KEY` with the channel key. Only the exact PKI public keys on the
allowlist may register a channel; non-PKI, broadcast, MQTT and unknown-key commands
are rejected. Capture starts enabled and replay stays disabled. Replies never
repeat the key. Commands and replies are not archived by MeshMemo, but the sender's
Meshtastic application may retain the outgoing DM. Remote addition is bounded to
one accepted attempt per public key per minute; a durable packet-ID ledger prevents
re-execution after restart. At 10,000 requests the ledger fails closed pending
operator maintenance. No request body or PSK is written to diagnostic logs.

## Key storage and backups

PSKs in SQLite are encrypted with Fernet. The master key is generated on first
registration beside the database as `<database>.channels.key`; on POSIX it has
mode 0600. On Windows use an account-restricted data directory. It must be backed
up separately and restored alongside the matching database. The admin's SQLite
backup download **does not include the master key**. Losing this file prevents
use of the stored channel keys; startup never generates a replacement for an
existing catalogue. The application does not expose PSKs or the master key via
its public API. Protect the entire data directory and backups; a full host compromise
can access both the database and its key. Archived message text is still readable
SQLite data, as before; this feature encrypts channel keys, not the chat database.

For remote admin entry use HTTPS or an SSH tunnel: Basic authentication on plain
HTTP does not encrypt passwords, channel keys or chat data in transit.

## Validation and rollout

Offline tests cover migration, persistence, ciphertext capture, hash ambiguity,
key rotation, command exclusion, policy cancellation, PKI authorization, durable
request replay protection, response key redaction, API auth/CSRF and the USB codec.
The T-Beam S3 Core revision 3 build and native bridge checks passed. It was
flashed app-only on 2026-09-30; the write hash, configuration preservation and
a 75-second USB check passed. Server-only radio/DM acceptance is still pending.
Use the [firmware guide](../firmware/README.md) for app-only backup/partition checks.
The new firmware retains the USB screen-timeout fix and existing user board profile.

