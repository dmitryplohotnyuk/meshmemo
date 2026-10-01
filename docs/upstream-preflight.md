# USB history bridge preflight

Checked 2026-09-30. [Discussion #12021](https://github.com/meshtastic/firmware/discussions/12021)
was refreshed and still had zero replies. The API has not been agreed with
maintainers; no new message, PR, protobuf tag or public branch was created.

## Work completed while the proposal is under discussion

Extended the existing portable C++ bridge harness with controlled radio-adapter
results. Added 19 failure-path test cases in
[test_firmware_failures.py](../tests/test_firmware_failures.py). They execute the
real UsbSfBridge C++ implementation with an injected callback, without hardware:

- BUSY, DISABLED, RADIO_ERROR and INVALID outcomes reach the host unchanged.
- An exact USB retry returns the cached failure even after simulated recovery;
  another submission requires an explicit new operation.
- A conflicting retry does not replace the original cached outcome.
- Reset invalidates an old session after an operation with an unknown outcome.
- A full reply slot does not admit another operation before its result is consumed.
- Invalid sender/requester/channel/emoji/packet IDs do not reach the radio callback.
- Empty or oversized replay text does not reach the radio callback.

The full Python suite, with a freshly compiled MSVC native harness, passed:
**95 passed, no skips**. The existing Starlette TestClient deprecation warning
remains. This run did not rebuild/flash the board, enable replay, or transmit RF.
UI code did not change, so UI tests were not repeated.

These tests exercise command dispatch, validation and callback-result handling.
They do not execute UsbSfRadio's real board adapter, MeshService, an RF queue or
the proposed future API. Their acceptance boundary must remain explicit in a PR.

## Radio admission result remains an integration gate

The pinned v2.7.26 base defines MeshService::sendToMesh as returning void. Our
prototype checks queue/airtime first, calls it, then reports bridge OK. A queue
check before submission cannot establish the eventual admission result. Existing
prototype documentation therefore describes this as submission to the local
service, not verified RF delivery or confirmed queue admission.

The reviewed [develop implementation](https://github.com/meshtastic/firmware/blob/778184c7a1b91993c810558325570cdbec4cc457/src/mesh/MeshService.cpp)
returns ErrorCode. An upstream adapter must consume that result, map explicit
failures, preserve packet ownership/release rules, and define what each success
case establishes. In particular, a release/local-delivery result must not be
silently treated as successful radio enqueueing. Do not bypass MeshService or
double-release its packet to work around the old void API.

The new callback tests provide fault-injection cases for that future adapter.
They do not fix or validate the current board adapter's admission reporting.
An integration test exercising the real upstream MeshService/Router path under
queue pressure is still required after the baseline/API are selected.

## Next dependent work

Follow the [RFC](upstream-usb-history-rfc.md) once maintainers respond: agree mode
enablement, authorization/session ownership, message schema, ID allocation and
control replies; then implement on the agreed upstream baseline. Reuse these
failure scenarios in the upstream test framework and add hardware acceptance.
Font, radio-power and local build patches remain outside that work.
