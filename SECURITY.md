# Security policy

MeshMemo is an alpha publication candidate with no supported stable release series.
Review the [deployment guide](docs/deployment.md).

## Trust boundaries

The admin is for one trusted operator. Every route requires HTTP Basic login
(`admin`) with a mandatory password from private TOML configuration. The default
bind is loopback on port 18765; LAN binding requires explicit configuration.
Host checks, CSRF tokens and same-origin checks protect writes. Ten failed login
attempts per source address trigger a temporary block within a one-minute window.
Forwarded headers are not trusted. There are no individual accounts or roles.
HTTP does not encrypt credentials or messages; use SSH forwarding or HTTPS outside
a trusted LAN. Do not publish this alpha service directly on the Internet.

Protect configuration with mode 0600 or root:meshmemo 0640 on Linux (world access
and group write are rejected), and private ACLs on Windows. Never commit real
configuration or passwords. Change the configured password and restart the service
to invalidate old credentials. Browsers cache Basic credentials; close the private
browser session to leave the admin. Local users with service-account or root access
remain trusted.

SQLite and backups contain plaintext messages, node identifiers and saved
settings. Protect them with OS permissions and suitable host/disk security.
Configuration frames and keys discovered automatically from the USB node are not
archived. Explicitly registered server-channel PSKs are encrypted in SQLite with
a separate `<database>.channels.key` master key (0600 on POSIX). Back up both; the
admin database download excludes the master key. Host compromise can expose both
files. Device backups and serial captures may contain plaintext credentials and
must never be published. Use HTTPS or SSH forwarding for channel-key entry.

One capture/server process may own an archive. The OS lock covers cooperating
versions using the same resolved database path on a local filesystem. It does not
coordinate different databases using one USB device, older versions without locks,
network filesystems or hard-link aliases. Stop old versions before upgrading.

## Experimental radio replay

Replay starts disabled. Profile 1 uses fresh outer packet IDs with original_id
inside the S&F payload; intentional original-ID re-encryption is blocked. The
durable ledger prevents known reuse but cannot guarantee freedom from collisions
with unknown/future IDs in Meshtastic's 32-bit space.

The USB host is trusted. Session tokens and configuration digests are consistency
checks, not credentials. Private-channel PSK membership is not individual requester
authentication. Replay shares an author's identity and requires a trusted operator.
Revision 3 adds USB-only host-encrypted replies: firmware checks packet bounds,
LoRa configuration, airtime and queue capacity, but cannot inspect encrypted
application contents. Remote `/channel add` is a separate, default-off operation:
only PKI-authenticated DMs from pinned administrator public keys are accepted.
Channel PSK possession or a node ID does not grant that administrator access.
Commands are excluded from the archive, but the sender app may retain its DM.
Keep BLE/network APIs separate from the USB extension. See
[replay security](docs/replay-security.md) and [current contract](docs/history-replay.md).

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/dmitryplohotnyuk/meshmemo/security/advisories/new)
or **Security → Report a vulnerability** in the repository. Private reporting is enabled.
Do not open public issues containing exploit details, keys or private archives.
Use synthetic examples and provide version, platform, impact and reproduction steps.

Dependency scans detect known published advisories only. Passing tests/scans does
not certify the deployment, firmware or radio protocol as secure.
