# Deployment and operations

This guide targets a **single trusted operator**, one USB node and one local
SQLite archive. The current release is an alpha. Debian deployment, service
autostart configuration, process recovery and USB capture have been exercised.
Whole-host reboot, extended soak and full radio/client acceptance remain open;
see [current status](implementation-status.md). Adjust this template for your host.

## Install a reviewed build

Python 3.11–3.13 is supported by the source/CI configuration. Start with a clean
virtual environment and a reviewed checkout or wheel. Record the source revision,
wheel SHA-256 and resolved dependency versions. The checked-in constraints capture
the tested Windows/Python 3.12 runtime; Linux can have additional platform-specific
SDK dependencies. Validate them on the actual host.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -c requirements/constraints.txt .
python -m pip check
cp deploy/config.example.toml meshmemo.toml
chmod 600 meshmemo.toml
# Edit admin.password before starting.
meshtastic-sf-server serve --config meshmemo.toml
```

The data directory must be writable by the service and inaccessible to unrelated
users. Use a local filesystem, not a network share; SQLite WAL and ownership locks
are intended for local storage. Keep installation files read-only to the service.

## Linux service (Debian/Ubuntu example)

These commands require an administrator. Adjust device/group names for your distro.
Install a reviewed checkout/wheel under `/opt/meshmemo` before enabling the service.

```sh
sudo useradd --system --home-dir /var/lib/meshmemo --create-home --shell /usr/sbin/nologin meshmemo
sudo usermod -aG dialout meshmemo
sudo install -d -o meshmemo -g meshmemo -m 0700 /var/lib/meshmemo
sudo install -d -o root -g root -m 0755 /opt/meshmemo
sudo sh -c 'umask 022; python3 -m venv /opt/meshmemo/venv'
sudo sh -c 'umask 022; /opt/meshmemo/venv/bin/python -m pip install -c requirements/constraints.txt .'
sudo install -d -o root -g meshmemo -m 0750 /etc/meshmemo
sudo install -o root -g meshmemo -m 0640 deploy/config.example.toml /etc/meshmemo/config.toml
# Edit /etc/meshmemo/config.toml: set admin.password and
# server.database = "/var/lib/meshmemo/history.db" before enabling.
sudo install -m 0644 deploy/meshmemo.service /etc/systemd/system/meshmemo.service
sudo systemctl daemon-reload
sudo systemctl enable --now meshmemo
sudo systemctl status meshmemo
```

The supplied unit starts without a forced serial device. Configure auto/manual USB selection
through the admin; it is persisted in the archive. For the first seed only, an
operator may add `--device /dev/serial/by-id/YOUR_NODE` to `ExecStart` before startup.
Do not run the app as root, and do not use `chmod 666` on device nodes.

`PrivateDevices` is intentionally disabled so USB remains visible. `PrivateTmp`,
`ProtectSystem=strict`, `ProtectHome` and `UMask=0077` limit the process. Device
access is still constrained by Unix permissions. Review the unit on your distro.

```sh
journalctl -u meshmemo --since today
curl --fail --user admin http://127.0.0.1:18765/healthz
# curl prompts for the password; do not place it in the command line.
sudo systemctl stop meshmemo
```

`/healthz` reports HTTP/worker liveness only; it can be OK with USB disconnected.
Use the admin for connection state and a manual integrity check for database health.
An ownership lock rejects a second `serve`/`capture` for the same resolved database
path. It is released by the OS on crashes; an empty `.lock` file can remain and must
not be deleted while the app is running. Use one path per archive; filesystem
hard-link aliases are not a supported deployment pattern.

## Windows

Run from a terminal using a virtual environment and a private data directory.
Select the COM port in Settings. Stop with Ctrl+C and wait for shutdown before
upgrading. A Windows service installer is not included; do not register the
application as a service without providing an orderly stop procedure and a fixed
working directory. Running the desktop app or another Meshtastic CLI against the
same port will conflict with the server.

## Remote administration

Every endpoint requires HTTP Basic authentication: login **admin**, password from
`[admin] password` in the private configuration file. The default port is **18765**.
A missing, empty or short password prevents startup. Configuration changes take
effect after restart; changing the password invalidates previous credentials.
Use a unique password of 12–256 characters. Real config files are excluded from
Git and source distributions. The public example intentionally has a blank password.

Relative database paths resolve from the configuration file's directory. With the
systemd unit, use `/var/lib/meshmemo/history.db`. Keep `/etc/meshmemo/config.toml`
owned by root:meshmemo with mode 0640; use 0600 for a private operator-owned file.

For private LAN access, set `server.host` to the server's LAN IP and list that IP
in `server.allowed_hosts` (without the port). Only listed hostnames/IPs are accepted.
The service waits for network-online before startup and restarts on failure.
There is no anonymous health endpoint; monitoring must authenticate too.

HTTP Basic sends credentials without transport encryption. On an untrusted network,
keep the default loopback binding and use an SSH tunnel, or provide HTTPS with an
appropriately configured reverse proxy. For a private SSH tunnel:

```sh
ssh -N -L 18765:127.0.0.1:18765 operator@your-server
```

Then open http://127.0.0.1:18765 and sign in. Do not publish this alpha directly on
the Internet. Browser Basic credentials are cached: use a private browser window
and close it when finished. There are no separate accounts or roles. Ten failed
logins from one address within a one-minute window temporarily block attempts.
CSRF/origin checks still protect writes after login; a password is not a replacement
for them. Forwarded headers are disabled, so a reverse proxy shares one rate-limit
bucket for its clients.

Check autostart with `systemctl is-enabled meshmemo` and worker state with
`systemctl is-active meshmemo`. Test recovery with `sudo systemctl restart meshmemo`;
a service restart does not establish recovery after a whole-host reboot.

For a read-only acceptance check from a reviewed checkout, run
`python scripts/check-deployment.py --config meshmemo.toml` with access to the
private config. It checks password enforcement, assets, worker liveness, CSRF and
SQLite integrity without displaying credentials or message contents. A healthy
worker can be waiting for an unplugged node; radio reception still needs a hardware
test after USB connection.

## Back up and restore

Back up before every schema/software upgrade and before shortening retention.
Use Database → Download backup, or:

```sh
meshtastic-sf-server backup --database data/history.db --output data/backups/manual-copy.db
```

The destination must not exist. The command uses SQLite's backup API and checks
integrity. It may be used with the running server **at the same application/schema
version**. Opening a repository applies migrations, so do not use a newer backup
CLI against a still-running older server. Never back up by copying only an active
`.db` while leaving its WAL behind.

If the server catalogue is populated, also back up `<database>.channels.key`
separately. The downloaded SQLite snapshot includes encrypted PSKs but not this
master key. Keep both in protected storage; see [key backup](#server-channel-key-backup).

For restoration, stop the server. Keep the original database, WAL and SHM together
in a private quarantine directory. Restore a verified snapshot to a **new path**
and restore its master key, if present, beside the new path as
`<restored-database>.channels.key` (service-owned, mode 0600). Start the matching
application version against that path. Check integrity,
message counts, node identity and settings before resuming. Do not combine an old
`.db` with newer `-wal`/`-shm` files. Keep the restored replay switch off until you
have reviewed its saved value. A backup includes the replay-ID ledger and settings.

## Update and roll back

1. Record the current version, constraints and firmware/profile.
2. Make and verify a backup with the current version, then stop the server.
3. Install the candidate into a separate virtual environment. Run tests and
   `pip check`; validate migration on a copy of the backup first.
4. Start the candidate against the intended archive. Startup applies packaged
   Alembic migrations; wait for connected status and confirm a received message.
5. Keep the previous environment and backup until acceptance completes.

Rollback restores the **previous application plus its matching backup** to a new
path. Downgrade migrations are not an operational rollback guarantee. Messages
received after the backup will not appear in that rollback copy; preserve the newer
archive for recovery rather than merging databases manually.

Stop old versions before starting a version with ownership locks: an already-running
older version does not participate in the new lock protocol.

## Monitor capacity

Check disk free space, archive counts and the connection state. Retention bounds
message history only: backup files require operator cleanup, and the durable
replay-ID ledger has a separate one-million-entry limit. SQLite does not necessarily
shrink its file after deletions. Do not run maintenance/VACUUM on the live archive
without a backup and a maintenance window. Rotate service logs using the OS tools.

Radio replay remains experimental. Follow [hardware acceptance](hardware-acceptance.md)
before enabling it; service uptime alone does not establish radio delivery.

## Server channel key backup

When using the [server channel catalogue](server-channels.md), include the
`<database>.channels.key` file in a separate protected backup. The admin SQLite
download does not contain this master key. Restore the matching key beside the
database, owned by the service user (0600 on Linux). Do not publish either file.
Use HTTPS or an SSH tunnel when entering channel keys in the admin.

## Versioned systemd upgrades

A separate environment such as `/opt/meshmemo/venv-a6` can be prepared and tested
before stopping the current service. Keep it at its final path: virtualenv script
shebangs contain absolute paths. A systemd drop-in may select the new executable:

```ini
[Service]
ExecStart=
ExecStart=/opt/meshmemo/venv-a6/bin/meshtastic-sf-server serve --config /etc/meshmemo/config.toml
```

Stop the service, create and verify the backup, then install the drop-in, run
`systemctl daemon-reload` and start the service. Preserve the previous environment,
unit/drop-ins, database and master key. Inspect `systemctl cat meshmemo` before the
next upgrade; updating a base unit does not override a drop-in. Rollback requires
both the prior executable and its matching database/key backup.
