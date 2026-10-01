# Third-party notices

MeshMemo is an independent project for Meshtastic networks, not an official
Meshtastic product. Product names identify compatibility; no endorsement is
implied. The MeshMemo SVG mark is project artwork.

## Meshtastic-derived material

Firmware patches target [Meshtastic firmware](https://github.com/meshtastic/firmware)
commit `54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb`. Protocol patches target
[Meshtastic protobufs](https://github.com/meshtastic/protobufs) commit
`6b1ded439633cd03d4af85b44231b91d1d106278`. Both pinned checkouts contain the GNU
General Public License version 3. A verbatim copy is included at
[firmware/LICENSE.upstream.txt](firmware/LICENSE.upstream.txt). Preserve upstream
copyrights and file-specific notices for derived work. The inherited UA22/Cyrillic
changes are recorded in [firmware/upstream.json](firmware/upstream.json).

Fetched firmware/submodules retain their own licenses. The source bundle excludes
compiled firmware and vendored checkouts. Binary firmware distribution requires a
separate review of corresponding-source and notice obligations for the exact build.

## Python and build dependencies

Dependencies are declared in pyproject.toml and tested versions recorded in
requirements/constraints.txt. They are installed separately and retain their own
licenses. Review installed distribution metadata and notices when assembling a
deployment or binary distribution. Dependencies are not relicensed by this project.

Newly authored MeshMemo code is licensed under [GPL-3.0-only](LICENSE).
This does not replace upstream or dependency licenses and notices.
