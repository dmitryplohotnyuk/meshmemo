# Contributing to MeshMemo

Start with the [architecture](docs/architecture.md) and [current status](docs/implementation-status.md).
Use Python 3.11–3.13 in a virtual environment:

```sh
python -m pip install -c requirements/constraints.txt -e '.[dev]'
python -m pytest
node --test tests/ui/i18n.test.cjs
python scripts/release-check.py
python -m build
```

Node.js 22+ is needed only for UI logic tests. Tests use synthetic data and never
open a physical USB port. Native tests skip if the harness is not configured;
a passing run with skips is not full protocol validation.

## Native protocol checks

Prepare a fresh checkout (Git and network access required):

```sh
python scripts/prepare-firmware.py --profile inherited-ua22 --replay
g++ -std=c++17 -Wall -Wextra -Werror -I .build/firmware/src/mesh tests/native/bridge_harness.cpp .build/firmware/src/mesh/UsbSfBridge.cpp -o .build/bridge_harness
USF_BRIDGE_HARNESS=.build/bridge_harness python -m pytest
```

These compiler/test commands are for Linux. On Windows, install Visual Studio
C++ Build Tools and pass the actual vcvars64.bat path to
`scripts/test-firmware-native.ps1 -VcVars 'YOUR_PATH'`. It expects the project's
.venv and default .build/firmware checkout. Preparation refuses to replace an
existing destination; use --destination for another checkout. These checks compile
the portable protocol harness, not the full radio firmware.

## Change boundaries

- Keep domain rules independent of hardware; SDK calls belong in transport.
- Change storage through Alembic migrations, with migration tests on an older archive.
- Preserve off-by-default replay and fail-closed capability/scope checks.
- Keep firmware as ordered patches against the recorded upstream commit.
- Update all three locale catalogs; preserve user text and unsaved UI drafts.
- Test data integrity, protocol and security behavior; document operational impact.

Never commit real messages, channel URLs/PSKs, private node IDs, device backups,
private screenshots, serial captures or machine-specific paths. Use synthetic
fixtures. Review the staged diff and bundle even when the release check passes.

Offline checks do not establish iOS/Android, RF or multi-hop compatibility.
Flashing and [hardware acceptance](docs/hardware-acceptance.md) are explicit
operator actions. CI must never transmit test radio traffic.

Contributions to MeshMemo are provided under [GPL-3.0-only](LICENSE).
Retain upstream notices and identify the provenance of imported or derived code.
