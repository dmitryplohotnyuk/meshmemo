# Portable firmware hardware preflight — 2026-10-01

## Observed state

- No Meshtastic USB serial device was present on the Windows development PC.
  Only the system COM1 port was enumerated; no device port was opened.
- The existing LAN deployment answered an authenticated status request. Its USB
  connection was connected, firmware metadata was `2.7.26`, frames and packets
  were being received, and no runtime error was reported. Schema: `0005_catalog`.
- Replay was already enabled on that deployment. No settings were changed and
  no synthetic radio messages or history requests were sent.
- SSH reached the known host but unattended authentication was rejected.
  Updating the server and directly inspecting its node require operator-provided
  access. The firmware metadata version alone cannot identify the installed patch.

## Prepared software

The server package is 0.1.0a8. A pre-deployment check found stale CLI/module
version constants; both now agree with package metadata. One regression test
checks CLI, module and pyproject versions together. The separately installed
wheel passed its version check, offline startup, migrations and packaged web
asset checks. Its CLI reports `0.1.0a8`.

The corrected artifacts are in `dist/portable-contract-20261001/`. They supersede
the earlier locally built 0.1.0a8 artifacts for deployment; none was uploaded or
installed on the running server during this preflight.

The T-Beam candidate preserves the previously installed UA22, OLED Cyrillic and
display-timeout options. This device-specific choice does not change the
builder's default: all three options remain off. Source preparation uses the
same pinned firmware/protobuf commits and dependency lock as the base profile.

The complete offline T-Beam build passed in 562.07 seconds, including runtime
checksum verification before and after compilation. Its application-only image
is in the builder's `dist/portable-tbeam-options/` directory:

- Size: **2,411,424 bytes**.
- SHA-256: `48dd6ef70c4fab1e4519fa39d9fb642f73834a442650f4882640a34031245524`.
- Build ID: `b01e2bbb819c91bb0bb89064a718614e3e01a918fda46bff7d37b976b7f3af86`.
- The historical 8 MiB flash backup contains an app0 partition at `0x10000`
  with size **2,424,832 bytes**. The candidate fits with **13,408 bytes** left.
  This is an offline check of the earlier backup, not a live-device check or
  authorization to use the build's larger default partition table.

## Remaining hardware work

1. Obtain SSH access, verify the current service/package and device identity,
   and preserve a protected database/config/channel-key backup plus rollback
   environment before updating the server.
2. Check server 0.1.0a8 with the existing 1/3 firmware before replacing firmware.
3. With exclusive access to the device, read its current configuration and full
   flash. Verify the live partition table and active application slot. The
   historical device app partition is smaller than the new build's partition;
   a successful compilation does not establish fit on the device.
4. Write only the verified application image when the live checks pass. Preserve
   partitions, configuration and keys. Compare configuration and node identity
   after boot, then verify USF2 model, capabilities and exact build ID.
5. Check sustained USB connection, reconnect and display timeout/button wake.
   Perform isolated synthetic radio/client checks from the hardware acceptance
   procedure, recording physical results separately from host-side success.

Firmware writing, service replacement, screen behavior and radio acceptance of
the portable firmware have not been performed. The existing deployment remains
in operation.
