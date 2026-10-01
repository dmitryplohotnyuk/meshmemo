# Draft USB API for an external history backend

Status: detailed local design proposal, 2026-09-30. The shorter
[discussion text](upstream-discussion-draft.md) was published as
[firmware Discussion #12021](https://github.com/meshtastic/firmware/discussions/12021).
This detailed RFC has not been submitted and the API has not been approved upstream.
The behavioral requirements below describe a proposed upstream implementation;
they must not be read as capabilities already present in the installed prototype.

## Objective and scope

Allow a trusted USB host to answer ordinary S&F history requests using an external
archive while preserving the original message author. The normal ToRadio packet
API must continue to normalize client-provided sender identities. Keep database
code, retention, web UI and archive queries outside firmware.

The first scope is private-channel broadcast text replayed by unicast to the
requester. It excludes DMs/PKI, public/default keys, MQTT-originated history,
arbitrary application payloads, remote transports and automatic firmware updates.
Region/power, display fonts and Windows build changes are explicitly excluded.

## Reviewed upstream baseline

Reviewed on 2026-09-30:

- Firmware develop: `778184c7a1b91993c810558325570cdbec4cc457`.
- Protobufs master: `adda93634eba450448392c92a1ebe39c4d5deaff`.

The ordinary sender restriction is in
[MeshService.cpp](https://github.com/meshtastic/firmware/blob/778184c7a1b91993c810558325570cdbec4cc457/src/mesh/MeshService.cpp).
Connection authorization checks are in
[PhoneAPI.cpp](https://github.com/meshtastic/firmware/blob/778184c7a1b91993c810558325570cdbec4cc457/src/mesh/PhoneAPI.cpp).
The existing replay envelope is implemented in
[StoreForwardModule.cpp](https://github.com/meshtastic/firmware/blob/778184c7a1b91993c810558325570cdbec4cc457/src/modules/StoreForwardModule.cpp).
Use these as integration points, not a justification for bypassing their checks.

The upstream original_id change and USB polling correction are already merged:
[PR #11849](https://github.com/meshtastic/firmware/pull/11849) and
[PR #11901](https://github.com/meshtastic/firmware/pull/11901). Neither belongs in
our new PR. Recheck branch state before implementation; these are dated findings.

## Responsibilities

| Host | Firmware |
| --- | --- |
| Persist eligible messages and configuration-scoped archive identity | Retain ownership of radio settings, encryption and mesh submission |
| Receive S&F requests through ordinary FromRadio packets | Ensure eligible requests reach the authorized backend without a competing native S&F answer |
| Select a bounded history window and enforce operator limits | Reject stale configuration, unsupported channels, malformed/oversized messages and unauthorized sessions |
| Pace work, apply cooldown and handle client aborts | Enforce final airtime, queue and session limits independently of host pacing |
| Store operation/ID decisions before submission | Deduplicate retries within the agreed session boundary |

Request forwarding while native S&F is disabled must be verified on the chosen
upstream baseline. If a dispatch change is necessary, limit it to this opt-in mode;
do not assume the host sees every request merely because it sees channel text.

## Proposed local operations

Use typed protobuf messages over existing serial framing. Names below are semantic
placeholders, not assigned proto field names or numbers. Do not publish experimental
field 100 as an upstream allocation. NanoPB bounds and total envelope sizes require
measurement before committing a schema.

| Operation | Required information | Result |
| --- | --- | --- |
| Capabilities | Supported API versions | Supported operations, bounds, mode state and compatibility version; no transmission |
| Open backend session | Compatible version and requested eligible channel set | Firmware-issued connection-bound session, lifetime and channel configuration contexts |
| Replay text | Session, operation ID, channel/context, requester, original sender/ID, UTF-8 text, reply ID, emoji and agreed fresh-ID input | Local admission result, operation ID and resulting outer ID |
| Keep session alive | Existing session | Renew the local session lifetime without radio traffic |
| Close backend session | Existing session | Revoke further submissions and clear unsent bridge work |

Opening a session must not enable the device policy. The operator separately opts
in through an authorized configuration path, and the host's replay switch also
defaults to off. The appropriate existing/new configuration field is a maintainer
decision, with any required protobuf/config-client changes included in scope.

After configuration synchronization, firmware binds the session to that physical
USB connection and current authorized identity. Only one backend owns a device at
a time. Capabilities are versioned independently of a particular board or commit;
ordinary DeviceMetadata supplies hardware and firmware identification.

Proposed results distinguish UNSUPPORTED, DISABLED, UNAUTHORIZED, INVALID,
STALE_CONTEXT, EXPIRED_SESSION, CONFLICT, BUSY and LOCAL_ADMISSION. A permanent
rejection is not retried as if it were congestion. Repeated capability requests
have no radio side effects, and an unsupported stock node remains capture-only.

## On air behavior and control replies

Firmware constructs a STORE_FORWARD_APP / ROUTER_TEXT_BROADCAST envelope with the
archived author's sender number and original_id. The outer packet goes to the
requester with a fresh ID. Preserve supported reply/emoji metadata; do not truncate
UTF-8 or create a new fragmentation scheme. The prototype's 192-byte text limit
is a measured local constraint, not an unchangeable upstream requirement.

Discovery, history counts, busy, pong and statistics use existing S&F control
messages with the server node as sender. Prefer the existing ToRadio path if it
can preserve the same mode/channel/airtime requirements. Otherwise propose a
strictly typed control operation in the same session. The choice is open for
maintainers; it must not permit arbitrary ports or a caller-selected control sender.
Only the permitted discovery heartbeat may use broadcast destination. Its cadence
must remain bounded; local session keepalive is distinct from radio heartbeat.

The protocol provides bounded snapshots, not reliable delivery or automatic paging
through an entire archive. No new phone protocol is proposed. Existing clients
must nevertheless be tested with their exact original_id/deduplication behavior.

## Channel binding and authorization

Every transmission requires an enabled device policy, a live authorized USB
session and a current channel context. BLE, TCP, HTTP and alternate debug UART
entry points cannot reach the operation in the initial version. Respect serial
disablement and existing lockdown/auth revocation, including changes after session
creation. A session token is correlation state, not a replacement credential.

Prefer an opaque firmware-issued configuration generation/context bound to the
session and channel. It must change on channel key/role or relevant LoRa changes
and on reconnect/reboot. The host must bind it to the synchronized configuration
used to select the archive scope; it cannot apply an old archive selection to a
newly obtained context. The exact generation mechanism remains a design choice.

Validate and snapshot the allowed channel/configuration under the appropriate
firmware synchronization before enqueueing. Determine whether the router can
invalidate queued packets on reconfiguration or whether mode changes need to wait
for draining. A comparison just before enqueueing does not make later RF emission
atomic with configuration changes. This is an implementation gate, not a solved
property of the prototype's configuration digest.

Reject invalid/default keys, disabled channels, invalid destinations and malformed
text. Group PSK membership does not authenticate an individual requester or archived
author. A trusted backend can misrepresent history; document that power explicitly.
The API is not cryptographic proof that the original sender authored the text.

## Identity and retry semantics

The changed replay payload must not intentionally reuse the original sender/ID
combination under the same key. The original ID belongs inside StoreAndForward.
Select and document the outer-ID allocator before implementation: host ledger,
firmware allocation, or a reservation exchange. Firmware must at least reject
zero IDs, equality with original_id and known conflicts. Fresh random IDs do not
guarantee global uniqueness for another sender's 32-bit ID space.

The prototype's host ledger survives restarts and retention. It checks known
archived/reserved IDs, but it cannot see all past/future sender traffic. That is
evidence for a design discussion, not a complete nonce-uniqueness guarantee.

Use stop-and-wait with monotonically ordered operation IDs within a firmware-issued
session. Cache the completed operation's exact request and result in bounded
memory. Identical retries return the cached result; different bytes with the same
ID fail with CONFLICT; older operation IDs cannot be resubmitted. A new congestion
attempt uses a new operation only after a definite rejection. Execution/admission
and retry bookkeeping must be coordinated so an ACK lost on USB cannot cause a
second local submission.

After link loss, session revocation or reboot, do not resubmit a command with an
unknown outcome into a new session. The guarantee is bounded session idempotency,
not exactly-once delivery across power failure. The host may retain a message that
was never delivered. LOCAL_ADMISSION must mean actual local queue acceptance; it
must not claim RF transmission, an acknowledgment or display on a phone. Surface
known enqueue failures, including the mesh service's returned status.

Closing/revoking the session stops new work. It cannot promise to recall packets
already owned by the router. Use a bounded lease and no hidden automatic continuation
after reconnect. Keep replay disabled if capabilities or session state are uncertain.

## Prototype differences to remove

| Current local implementation | Required direction for upstream |
| --- | --- |
| Private field 100 and USF1 byte envelope | Maintainer-reviewed typed schema and allocated tags |
| Model 12 and fixed base SHA in handshake | Generic capabilities plus actual device metadata |
| Build flag on one board; host switch | Explicit device policy, session lifecycle and supported-board selection |
| Direct sendToMesh call with a generic success response | Authorization integration and precise local admission/error reporting |
| Digest checked before submission | Agreed configuration synchronization and queued-packet policy |
| ESP32 mbedTLS implementation | Use supported abstractions or explicitly constrain the first target |
| Per-PhoneAPI bridge buffers | Measure memory cost; follow upstream transport lifetime/allocation constraints |
| Native built-in S&F disabled manually | Enforced mutual exclusion with the external backend |

These are proposed changes, not silent upgrades to the running node or server.
The local profile remains described by [history-replay.md](history-replay.md).

## Implementation and acceptance plan

1. Discuss feature scope, trust model, allocator and configuration with maintainers.
2. Submit the agreed bounded schema and compatibility tests to meshtastic/protobufs.
3. Build firmware changes on a fresh develop baseline using generated bindings;
   exclude all unrelated local patches. Keep the ordinary client sender restriction.
4. Add an SDK adapter and update MeshMemo capability negotiation. Unsupported
   firmware remains usable for capture with replay off.
5. Complete the matrix below and provide sanitized synthetic evidence with the PR.

| Test group | Required outcome | Current evidence |
| --- | --- | --- |
| Parser and encoder bounds, exact retries and malformed input | No duplicate submission, overflow or arbitrary-port injection | Portable local C++/host tests exist; new API tests still required |
| Off mode, unauthorized clients, non-USB transports, lockdown revocation | No history submission; ordinary capture/client behavior preserved | Local off-mode coverage; proposed device/session checks not implemented |
| Private/default keys, secondary channel, stale configuration and reconfiguration races | No cross-scope response or stale queued transmission | Host filtering covered; hardware/race checks pending |
| Queue pressure, airtime, returned enqueue errors and cancellation | Bounded work and accurate admission results | Partial prototype checks; fault injection pending |
| Host/firmware restart, lost replies and ID ledger | No automatic replay of uncertain submissions | Local host/codec coverage; full hardware sequence pending |
| Live plus repeated history, authors, Unicode, reply/emoji, multi-hop | Correct display/deduplication on exact client builds | Radio/App Store acceptance pending |
| Build/resource and normal USB/BLE regression | Measured flash/RAM and baseline compatibility | Prototype built on T-Beam Supreme; upstream/other-target checks pending |

The repository audit recorded 76 passing Python tests including the native harness
and 2 UI logic tests. Subsequent [preflight work](upstream-preflight.md) added 19
failure-path cases and passed all 95 Python tests with the rebuilt native harness.
Those results apply to the prototype; they do not validate this proposed API or
establish radio compatibility. See
[hardware acceptance](hardware-acceptance.md) for the existing operator procedure.

## Submission conditions

Follow the upstream [contribution instructions](https://github.com/meshtastic/firmware/blob/778184c7a1b91993c810558325570cdbec4cc457/CONTRIBUTING.md):
discuss the feature, use the repository template and formatting tools, and complete
the CLA with the contributing account. Account-owner agreement and contribution
rights cannot be inferred from this design document. The local project license
decision remains separate from the upstream API discussion.
