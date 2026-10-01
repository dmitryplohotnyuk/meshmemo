# Hardware acceptance: experimental history replay

**One text-command request and one replayed message were received over radio.**
Replay remains off by default; the operator enabled it on the test deployment.
See the [2026-09-30 hardware findings](history-replay.md). Discovery reached iOS,
and `/history 6` received one rr=9 message on the expected secondary channel.
Native Client History requests still lose their channel through PKI; phone UI,
duplicate handling, server-authored texts and multi-hop delivery remain unaccepted.
Use an isolated test channel and synthetic messages. Back up app data, node
configuration and archive before switching test devices.

## Setup

Record host OS/Python/server commit, board/firmware/profile, exact phone OS and
app version/build, radio settings and topology. Keep keys, device identifiers and
private snapshots out of public results. Preserve configuration during app-only
flashing; never assume another board has the same partition map.

Use legacy profile **1, revision 2 or 3**, or portable **USF2 1/4**, for node-local
channels. Server-only channels require legacy revision 3 or portable 1/4 with the
ENCRYPTED_REPLY capability. Update the server to 0.1.0a8 before using USF2;
see [compatibility](firmware-compatibility.md). Keep the node's built-in
Store & Forward disabled. Diagnostic profile 0 cannot replay. The old iOS
2.7.22 (2395) is a known duplicate case; verify the actual App Store build supports
original_id. A merged upstream PR alone is insufficient.

The [2026-10-01 preflight](portable-hardware-preflight-2026-10-01.md) records
preparation for the portable firmware. It does not mark USB/radio acceptance
of that firmware as passed.

## Procedure

1. With replay off, receive a synthetic live message from another node. Confirm one stored row, correct channel/author/text, no history reply or heartbeat.
2. Confirm USB capability/configuration handshake. Enable replay explicitly with a small limit/window and conservative interval. Verify private-channel discovery.
3. Send `/history 6` in the private channel; separately test the client's S&F action if its firmware preserves channel context. Check chronology, original authors, Unicode, reply IDs and channel. Outer IDs must be fresh; original_id must identify the original messages.
4. Request the same window again; combine live and replay delivery. Verify one displayed copy per original. Compare packet observations and UI results; USB submission is not an RF acknowledgment.
5. Repeat on a secondary private channel and multiple hops. History must not cross scopes/channels.
6. Exercise limits, default/maximum windows, cooldown, second-requester busy handling, abort and oversized-text exclusion. Excluded messages must remain archived.
7. Disconnect/reconnect and restart the host. The ledger persists and an uncertain old queue does not resume. Same-session USB retries must not submit duplicate RF packets.
8. Change radio settings only while idle; verify old digests/scopes are rejected. Exercise airtime and queue pressure.
9. Disable replay during a response. New submissions/heartbeats stop; already-submitted mesh packets cannot be recalled.
10. Restore replay to off and verify persistence after restart. Record pass/fail for each case.

Stop on wrong-channel delivery, intentional original-ID reuse, unexpected authors,
replay while disabled or duplicate RF submissions. Keep captures private and
publish sanitized synthetic evidence only.

## Server-channel and administrator-DM acceptance

The revision 3 device has passed flashing, configuration preservation and USB
checks. The following radio checks are still pending:

1. Add a synthetic private channel only to the server catalogue and a client node;
   keep it absent from the USB node's slots. Match frequency/LoRa settings and
   allow unknown-channel forwarding. Receive a test message and verify its scope.
2. Enable global and per-channel replay. Send `/history 6` from another participant.
   Verify channel, author, original ID, unicast destination and client display.
   Repeat the request; include a server-authored message and a text over 160 bytes.
3. Disable per-channel capture/replay independently; verify cancellation and no
   cross-channel delivery. Change the key while idle; old history must not be
   served with the new key. Reconnect and restart to verify catalogue persistence.
4. Keep remote administration off and confirm no registration. Enable it with a
   verified test administrator key; send a PKI `/channel add` DM. Verify capture
   on/replay off, key-free receipt and no command in the message archive.
5. Reject an unlisted key, non-PKI DM, broadcast command and replayed request,
   including after restart. Confirm configured rate limits and queue bounds.
6. Restore the database plus its master key on an isolated host. Verify startup
   fails with a missing/wrong key rather than silently replacing it. Return replay
   and remote administration to off after the test.

## Release decision

Claim compatibility only for tested firmware/server/client combinations. Repeat
client-sensitive checks after upgrades. Linux service and backup/restore acceptance
are separate from radio tests.
