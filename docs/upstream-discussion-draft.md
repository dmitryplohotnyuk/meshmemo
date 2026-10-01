# External Store and Forward backend over USB

Would the firmware maintainers be interested in a narrowly scoped, opt-in USB API
for an external Store & Forward history backend? We have a working local archive
and an experimental firmware bridge in MeshMemo, and would like to agree on the
interface and trust model before preparing protobuf and firmware PRs.

## Use case

A computer connected to a Meshtastic node over USB stores eligible private-channel
messages in SQLite. It provides retention, backups and a local chat browser. When
a client requests history through the existing S&F protocol, the computer selects
a bounded set of messages and the node transmits them with their original authors.
This keeps archive storage and queries on the host and bounds firmware memory use.

The missing piece is a supported way to submit historical messages with their
original authors. The normal client path deliberately resets `p.from` in
[MeshService::handleToRadio](https://github.com/meshtastic/firmware/blob/778184c7a1b91993c810558325570cdbec4cc457/src/mesh/MeshService.cpp).
We want to preserve that protection for ordinary client traffic and add a specific
S&F operation for an explicitly trusted USB backend.

## Proposed scope

- Typed local API messages in the existing ToRadio/FromRadio transport, with capability negotiation and tags agreed in meshtastic/protobufs.
- An explicit device opt-in, off by default, plus an authorized USB session. Disconnect, expiry, configuration changes and loss of authorization revoke the session.
- Replay of archived UTF-8 broadcast text from private channels to the requesting node. Firmware constructs only the allowed S&F response, preserving author, original_id, reply ID and emoji metadata.
- A fresh outer packet ID for each new replay operation; never deliberately reuse the original ID for the changed payload.
- Bounded request size, stop-and-wait submission, idempotent exact retries, channel/configuration checks and normal airtime/queue restrictions.
- Host-side storage, history selection, retention and request pacing. Native S&F and the external backend must not answer simultaneously.

The on-air message remains STORE_FORWARD_APP with StoreAndForward.original_id,
building on [firmware PR #11849](https://github.com/meshtastic/firmware/pull/11849).
We are not requesting a new mesh application port or a replacement phone protocol.
Client compatibility still needs testing with the exact application versions.

This proposal contains no radio power/region changes, display/font changes or
local build workarounds. The USB polling fix in
[PR #11901](https://github.com/meshtastic/firmware/pull/11901) is already upstream
and would not be duplicated.

## Trust and failure behavior

The backend is trusted to represent archived authors correctly; private-channel
membership does not authenticate an individual author. The API must respect the
existing serial enablement and per-connection authorization/lockdown checks, and
must not become a general arbitrary-sender packet injection API. The first version
would exclude DMs/PKI, public/default-key channels and BLE/TCP/HTTP access.

An accepted submission means local queue admission, not RF transmission or delivery
to a phone. Exact retries must return the same result without a second submission.
After a disconnect or reboot, the host must not automatically replay a command
whose outcome is unknown. Stopping a session cannot recall packets already handed
to the mesh queue.

Our prototype reserves fresh outer IDs in a durable host ledger. This avoids known
reuse but cannot guarantee uniqueness against unknown or future IDs from the
original sender in a 32-bit space. ID allocation and restart behavior need explicit
agreement; we do not claim the prototype solves that globally.

## Current evidence and limitations

The prototype is based on firmware v2.7.26.54e0d8d and has been installed on a
T-Beam Supreme. USB capability negotiation and private-channel capture into the
archive have been exercised. Automated checks cover the host scheduler, filtering,
ID reservation and the portable C++ command parser/payload encoder.

Radio replay acceptance, repeated live/history deduplication on the actual App
Store client, secondary channels and multi-hop behavior are still pending. Replay
remains off. The prototype has not been rebased or hardware-tested against current
develop. Its private field 100, binary envelope and board/commit-specific handshake
are experimental details, not the requested upstream interface.

## Questions before implementation

1. Is a USB-only external S&F backend an acceptable addition, and where should its explicit enablement and session ownership live?
2. Would maintainers prefer typed replay operations in ToRadio/FromRadio, and should ordinary S&F control replies use the existing packet API or the same bounded session API?
3. What packet-ID allocation/restart policy and hardware/client acceptance matrix would you require before merging?

If this direction is acceptable, the proposed sequence is a small protobuf API PR,
a firmware implementation with regression tests, then an SDK adapter. MeshMemo
would be one consumer; the interface would not depend on its database or UI.
