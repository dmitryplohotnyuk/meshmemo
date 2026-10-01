# MeshMemo user guide

## Connect a node

1. Start `meshtastic-sf-server serve --config meshmemo.toml` and open
   http://127.0.0.1:18765 (or the configured server IP with that port).
   Sign in as `admin` using the password from `[admin]` in the configuration.
   To change it, edit the file and restart the service.
2. Open Settings → Connection. Choose **Automatic**, or choose **Manual** and
   select the USB port. Apply the settings.
3. Wait for **Connected · receiving**. The current port and firmware are displayed.
4. Send a test broadcast from another node into a configured private channel.
   Open Chats to verify it was archived.

Automatic discovery remembers the verified USB device. If its port changes,
it follows the device identity. With no remembered identity, it opens a port only
when exactly one recognized USB candidate exists. If several devices are present,
select manually. A node without a USB serial identifier may only be recognizable
by its physical USB location; use manual selection if discovery is ambiguous.

A database is bound to one node. To use another node, stop the server and start
with a separate database. Do not edit the identity directly in SQLite.

## Read chats

The first channel containing messages opens automatically. Each request loads up
to 100 messages. **Load older messages** fetches the previous page instead of the
whole database. While reading older history, live updates are paused; use
**Latest messages** to return. Search matches literal text inside the selected
channel. Chat times show when the server received the message, formatted using
the selected interface language and the browser's timezone.

Channel names, authors and message contents are displayed as received. Changing
the language does not translate or modify chat data.

## Store and back up

- Capture can be paused; existing messages remain readable. New messages received
  during a pause are not buffered for later.
- The default record limit is 100,000. At the limit, new messages are refused.
  Increase the limit or select a retention period to resume storage.
- Retention defaults to **0** (no automatic deletion). Enabling or shortening it
  requires confirmation. Cleanup runs about once a minute and cannot be undone
  without a prior backup.
- Database → Check integrity runs SQLite `quick_check`.
- Download backup creates a consistent snapshot, including committed WAL data.
  A server-side copy is kept in the archive's `backups/` directory; manage its
  disk usage separately. Backups contain private plaintext messages. With server
  channels, also back up `<database>.channels.key` separately; it is not included
  in this download and is required to restore the encrypted channel keys.

Save applies settings without restarting. Unsaved edits can be discarded. Changing
interface language preserves drafts and the currently loaded chat history.

## Radio history sharing

Leave it disabled until the firmware/client acceptance procedure has passed for
your setup. Capture does not require replay firmware. Replay does: the supported
experimental target is LILYGO T-Beam Supreme with USB profile 1/revision 2 or 3
(revision 3 is required for server-only channels), plus a
client that correctly handles S&F `original_id`.

Controls include message limit, default/maximum history window, message interval,
per-requester cooldown, and optional server announcements. Changing these controls
cancels the pending queue. Disabling sharing stops new submissions; a packet
already accepted by the node can still be transmitted. Announcements are also
silent while sharing is disabled. See [history replay](history-replay.md).


Send **`/history 6`** as an ordinary message in the desired private channel to
request the last 6 hours, measured by server reception time. Examples: `/history 1`,
`/history 24`. Hours must be a positive integer of at most six digits. Larger windows
are capped to the configured maximum (at most 7 days); the message limit selects
the most recent eligible messages. The requester's own messages, unsupported long
texts and ambiguous identities are excluded. Replies are addressed to the requester
using Store & Forward.

The initial request is visible to channel members. `/history` commands, including
invalid ones, are **never archived or replayed**. Commands already present in an older
archive are excluded from replay without deleting records. Invalid commands, requests
during cooldown and requests while sharing is disabled receive no text response.
Pausing capture does not disable sharing previously saved messages.

Use the private channel, not a direct message to the server. Sending the command
requires no client firmware patch. Response display and duplicate handling still
depend on the app version. The native Client History button is a separate path;
its verified PKI channel-loss limitation does not apply to this broadcast request.

## Server channels and administrator DMs

Open **Server channels → Channels**. The table shows each channel, last received
message time and capture/history settings. **Add channel** and **Edit** open a
modal. Enter the exact channel name and private Base64 key, or a single-channel
Meshtastic link. Leave the key empty when editing to preserve it. Changing the
name or key separates future messages from the old archive. Unsaved modal edits
require confirmation before closing.

The catalogue supports up to 256 definitions on the USB node's current frequency
and LoRa settings. It does not change the node's channel slots. Global capture
and replay settings still apply; both per-channel switches can be turned off to
disable a definition. Unknown-key ciphertext is not archived for later decoding.

The separate **Manage through direct messages** tab is off by default. To allow
remote registration, pin each administrator's verified Base64 PKI public key,
then enable the switch. The authorized administrator sends a PKI-encrypted DM:

```text
/channel add Private BASE64_KEY
```

Replace the name and key with the intended channel. It starts with capture on
and replay off. `/channel` commands never enter the chat archive; the sender app
may retain its outgoing DM. Use HTTPS or an SSH tunnel when entering channel keys
through the web admin. See [server channels](server-channels.md) for limits,
key-file backups and the remaining hardware acceptance.

Since 0.1.0a7, `/history` returns only archived messages, without a count/window
summary. Empty results receive no response. Native Client History retains its
protocol header. Previously received summaries remain in the phone chat.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Waiting for node | Data-capable USB cable, available ports, OS driver/permissions. |
| Several devices found | Select the node's port manually. |
| Port busy | Close other Meshtastic tools; only one process may own USB. |
| Another node detected | Reconnect the original node or use a new archive. |
| No chat messages | Broadcast text in a private channel; public keys, DM, MQTT and telemetry are excluded. |
| Capture stopped at capacity | Increase the limit or review retention. |
| Server unavailable | Keep the server process running; verify its local URL and port. |
| Session changed | Reload the page after a server restart, preserving any edits you need first. |
| Duplicate replay messages on iOS | Keep replay off until the installed client passes the acceptance tests. |

Change node channel slots and radio settings in the Meshtastic app. Additional
server-side channels are managed in MeshMemo as described below. A changed name,
key or radio configuration creates a separate history scope.

Node names are loaded from the USB node database on connection and updated by
NodeInfo announcements. Unknown names fall back to IDs such as `!12345678`;
once a name is received, existing messages display it as well.
