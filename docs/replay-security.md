# Blocker: encrypted replay identity

Implementation update 2026-09-30: an **opt-in, disabled** fresh-ID candidate is
implemented in USB profile 1/revision 2 and the server scheduler. It does not reuse
the original ID as the replay transport ID. The device has not been flashed and
radio/client acceptance remains pending. [Contract and limits](history-replay.md).
The original stable-ID proposal below remains blocked.

Latest follow-up: [App Store-compatible alternatives research](replay-alternatives-research.md).
It distinguishes the merged upstream identity fixes from receiver firmware
behavior and examines exact-ciphertext replay routing limitations.

2026-09-25, found during implementation against firmware
`54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb`.

`CryptoEngine::encryptPacket()` initializes AES-CTR with a nonce constructed from
the packet ID (64-bit field containing the 32-bit mesh ID), sender node number,
and block counter. There is no recipient or port number in this nonce.
`Router::perhapsEncode()` serializes `Data` and encrypts it with this nonce and
the selected channel key. Its PKI path requires a locally originated packet;
it cannot authenticate a historical message as another sender.

The stable `StoreForwardModule::historySend()` profile retains the original
sender and ID, but replaces TEXT_MESSAGE_APP data with STORE_FORWARD_APP and a
StoreAndForward envelope. Thus, on the same channel key it encrypts different
plaintext with the same AES-CTR keystream as the original message. Our proposed
copy of this profile would inherit the issue. This conclusion follows from the
pinned source, and does not require transmitting private messages to test it.

For a reused keystream K, C1 = P1 xor K and C2 = P2 xor K, so
C1 xor C2 = P1 xor P2. This does not by itself recover the channel key, but can
disclose message content. A private channel does not prevent this problem.

Pinned sources:

- [CryptoEngine.cpp](https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/mesh/CryptoEngine.cpp)
- [Router.cpp](https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/mesh/Router.cpp)
- [StoreForwardModule.cpp](https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/modules/StoreForwardModule.cpp)

## Consequence

The original stable replay proposal is blocked, even before mobile and multi-hop
acceptance. USB diagnostics can proceed. Firmware profile 0 has no radio-send
path and always rejects REPLAY; the Python client also blocks it before sending.
Do not remove encryption, change device keys, or silently relax duplicate
requirements to work around this gate.

Next research must evaluate a fresh outer ID with original identity metadata
and compatible clients, or byte-identical encrypted replay with its routing and
UI limitations. Neither is currently accepted as meeting the original TЗ.
The decision to patch only the server USB node is retained; feasibility under
the unchanged-client requirement remains unproven.

## Comparison of next candidates

Update after direct iOS 2.7.22 (2395) testing: fresh outer IDs with original_id
produced duplicates in both live/replay and repeated-history cases. Sender and
channel were preserved. See [the observed results](ios-client-probe.md).
The firmware replay gate remains closed; the unchanged-client requirement has
not been relaxed.

Follow-up review on 2026-09-25 uses the pinned client snapshots in
`protocol-notes.md`; it does not assert which builds are currently in app stores.

| Candidate | Encryption / identity | Remaining obstacle |
| --- | --- | --- |
| Fresh outer ID, original sender, `StoreAndForward.original_id` | Avoids deliberately reusing the original nonce; original identity travels separately | Checked Android main normalizes original_id, but checked Android release and iOS paths do not. A compatible released client matrix is still required. |
| Replay exact original ciphertext as broadcast | Does not encrypt changed plaintext under the original nonce | It remains ordinary text, not a S&F text response. Duplicate caches, rebroadcast exceptions and receiver UI need separate validation; this does not establish the original S&F contract. |
| Replay original TEXT_MESSAGE ciphertext as unicast | Changing destination does not change channel AES nonce | Pinned Router rejects decoded channel-encrypted TEXT_MESSAGE_APP addressed to the local node as a legacy DM when PKI is enabled and the node is not licensed. This is not a general unchanged-client workaround. |

A decoded `MeshPacket` from the Python SDK is not an exact copy of the original
encrypted Data bytes. Re-serializing it can change the plaintext. An exact-byte
candidate would require capture before decryption and preservation of the
original channel-key scope; it must not be implemented by re-encoding saved text.

Recommended next investigation: fresh outer IDs with explicit original identity,
first verifying released client support. This is a research direction, not an
accepted relaxation of the TЗ. If compatible official clients cannot be found,
present the choice between waiting for upstream and explicitly changing client
requirements. Keep diagnostic profile 0 until that decision and validation.

Evidence for client behavior is linked in `protocol-notes.md`; firmware behavior
is in the pinned Router above and
[FloodingRouter.cpp](https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/mesh/FloodingRouter.cpp).
