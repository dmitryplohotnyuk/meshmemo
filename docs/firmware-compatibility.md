# MeshMemo firmware compatibility

Server 0.1.0a8 accepts the portable contract produced by MeshMemo Firmware
Builder 0.1.0a2, while retaining existing firmware support. Update the server
before installing firmware with the new contract.

| Firmware response | History profile | Hardware policy | Server-channel replies |
| --- | --- | --- | --- |
| USF1, 68 bytes | 1/2 | Existing model 12 and pinned base | Unavailable |
| USF1, 68 bytes | 1/3 | Existing model 12 and pinned base | Available |
| USF2, 112 bytes | 1/4 | Actual hardware ID; validated capabilities | Requires ENCRYPTED_REPLY bit |

The pinned base remains Meshtastic firmware commit
`54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb`. Unknown versions, revisions, profiles,
limits or transports are rejected. USF2 reports the actual model, operations,
request/payload limits and a 32-byte build ID. The ID describes build inputs;
it is not device authentication. Capabilities are checked on every response,
and changes during a session require reconnecting.

Requests retain the USF1 envelope and existing replay/control formats. Response
magic and length distinguish the new layout; protobuf field 100 is unchanged.
The server continues using its local serial connection. Firmware permits the
extension only on the board's explicitly selected SerialConsole transport,
after configuration completes. BLE, TCP and HTTP do not inherit this permission.

Builder profiles now cover T-Beam S3 Core (model 12, native USB CDC) and Heltec
WiFi LoRa 32 V3 (model 43, USB–UART console). The build manifests distinguish
compilation from USB/radio acceptance. Physical hardware acceptance for these
new builds is pending. Existing device tests apply to the previously installed
1/3 firmware, not automatically to a new image.

UA22, OLED Cyrillic and display timeout remain independent builder options,
disabled by default. Replay also stays off by default on the server. No database
migration or client-node firmware update is introduced by this contract change.

The independent builder repository owns new firmware changes. The server's
`firmware/` directory is retained as the historical 1/3 fixture and is not
silently rewritten to a different protocol.
