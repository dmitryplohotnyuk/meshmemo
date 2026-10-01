# USF1 USB protocol — diagnostics and replay

This local extension is experimental and private to the pinned firmware schema.
Field **100**, wire type **bytes**, is added to the `payload_variant` oneofs of
`ToRadio` and `FromRadio`. It is unused in the pinned upstream schema; this is
not an upstream allocation. Payload limit: 256 bytes. Existing Meshtastic serial
framing remains unchanged. No mesh packet or custom LoRa port carries USF1.

The Python projection in `bridge.proto` only declares field 100. Protobuf unknown
field preservation lets the pinned official SDK serialize the envelope without
forking its entire generated mesh schema. Runtime and SDK versions are pinned
or constrained in `pyproject.toml`; compatibility has an offline regression test.

## Profiles

| Profile / revision | Behavior |
| --- | --- |
| 0 / 1 | Diagnostics only; no radio transmission |
| 1 / 2 | Node-local history/control, fresh outer IDs and original_id |
| 1 / 3 | Revision 2 operations plus host-encrypted server-channel replies |

The current replay build advertises 1/3; the host accepts 1/2 for node-local
channels. These extension revisions are separate from the Meshtastic 2.7.26
firmware version. Profile 1 reports max_text=192, hardware_model=12 and the pinned
base commit. See [the replay contract](../../docs/history-replay.md).

All integers are unsigned and little-endian. The 16-byte header is:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | ASCII `USF1` |
| 4 | 1 | Operation: HELLO=1, REPLAY=2, ABORT=3, CONTROL=4, ENCRYPTED_REPLY=5; response sets bit 7 |
| 5 | 1 | Request flags=0 / response status |
| 6 | 2 | Reserved=0 |
| 8 | 4 | Nonzero host session |
| 12 | 4 | Nonzero, increasing command token |

HELLO and ABORT have no body. Every response is exactly 68 bytes. After the
header: max_text u16, profile u8, patch_revision u8, hardware_model u32,
queue_free u32, base_commit 40 ASCII bytes. **Profile 0** reports max_text=0,
patch_revision=1, hardware_model=12, queue_free=0. It has no radio-send path.
REPLAY always returns DISABLED; ABORT is a successful no-op because nothing can
be queued. The draft `ReplayMessage` encoder is reserved and cannot be submitted
through `BridgeClient.replay()` in this profile.

Statuses: OK=0, INVALID=1, UNSUPPORTED=2, SESSION=3, STALE=4, CONFLICT=5,
BUSY=6, DISABLED=7, RADIO_ERROR=8 (the send-related statuses apply to profile 1).

An identical retry of the last accepted token returns the cached reply. Different
bytes with that token return CONFLICT; older tokens return STALE. A new session
requires HELLO. These tokens are not authentication. Only one reply can be
pending; a second command is ignored until the reply is consumed. Hosts use
stop-and-wait and may retry the exact bytes once. On exhausted retries the host
fails closed. Reconfiguration/disconnect clears the firmware session.

Only the board's USB CDC `SerialConsole`, with the build flag explicitly set,
can handle field 100 after config synchronization. BLE, TCP, HTTP and alternate
debug serial ports ignore it. Stock firmware ignores the unknown field.

Generate the host projection with:

```sh
python -m grpc_tools.protoc -I firmware/protocol --python_out=src/meshtastic_sf/transport firmware/protocol/bridge.proto
```

Firmware generated bindings are included in the firmware patch. To regenerate,
compile `meshtastic/mesh.proto` from the patched protobuf checkout using
`grpc_tools.protoc --include_imports --include_source_info --descriptor_set_out`,
then `nanopb.generator.nanopb_generator` with the protobuf options directory,
output `src/mesh/generated`, and `-S .cpp`. Nanopb 0.4.9.1 matches this base.

## Profile 1/revision 3: host-encrypted replies

Operation 5 follows the 16-byte USF1 header with four little-endian uint32 values:
original sender, unicast recipient, fresh packet ID, RF channel hash (0..255).
Bytes 32..47 contain the first 16 bytes of SHA-256 of the deterministically
serialized current LoRa config. Bytes 48..255 contain 1..208 ciphertext bytes.
No channel PSK is sent to firmware. Revision 2 clients remain usable for ordinary
local channels, but cannot submit operation 5. Retry/session rules are unchanged.
Authorization and payload construction belong to the USB host; firmware cannot
validate the port or contents of this encrypted payload.
