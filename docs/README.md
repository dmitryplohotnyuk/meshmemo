# Documentation

Start with the user guide or deployment guide. [Implementation status](implementation-status.md)
is the current record of implemented behavior and remaining acceptance work.
Dates and version numbers in research reports describe past observations.

## Use and operate MeshMemo

- [User guide (English)](user-guide.md) · [Русский](user-guide.ru.md)
- [Server channels, key management and remote registration](server-channels.md)
- [Deployment, configuration, backups and recovery](deployment.md)
- [Current implementation status](implementation-status.md)
- [Roadmap and release gates](implementation-plan.md)
- [Hardware acceptance procedure](hardware-acceptance.md)

## Develop and publish

- [Architecture and data rules](architecture.md)
- [Current history replay contract and command](history-replay.md)
- [Firmware build guide](../firmware/README.md) and [USB protocol](../firmware/protocol/README.md)
- [Contributing](../CONTRIBUTING.md), [security](../SECURITY.md) and [third-party notices](../THIRD_PARTY_NOTICES.md)
- [Repository audit](repository-audit.md) and [GitHub publication checklist](publishing.md)

## Design decisions and dated investigations

These are evidence for the design, not current installation instructions or claims
about the latest App Store release. Earlier statements such as “not implemented”
apply to their recorded stage; use the current guides above for present behavior.

- [ADR 0001: patched USB node](adr/0001-patched-usb-node.md)
- [Protocol investigation](protocol-notes.md)
- [Client compatibility](client-compatibility.md) and [snapshot](client-compatibility-snapshot.json)
- [iOS probe procedure](ios-client-probe.md) and [results](ios-client-probe-result.json)
- [Replay alternatives](replay-alternatives-research.md) and [security analysis](replay-security.md)
- [Hardware inventory](hardware-inventory.md) and [inherited firmware changes](inherited-firmware-changes.md)

## Upstream work

Proposals describe requested upstream behavior, which may differ from the local
implementation. Snapshots are dated evidence, not a live upstream status feed.

- [Submission plan](upstream-submission-plan.md)
- [USB history RFC](upstream-usb-history-rfc.md) and [status snapshot](upstream-usb-history-status.json)
- [Discussion draft](upstream-discussion-draft.md) and [preflight](upstream-preflight.md)
- [iOS issue notes](upstream-issue.md), [source snapshot](upstream-snapshot.json)
  and [2026-09-27 status](upstream-status-2026-09-27.json)

## Maintenance rules

When behavior changes, update the relevant user/deployment guide, current status
and changelog; update the architecture or replay contract if their rules change.
Keep historical evidence dated rather than rewriting past test results as current.
Use relative links within public source and synthetic examples. Private hostnames,
credentials, real node identifiers, message screenshots and operational logs do
not belong here. The original working specification is retained privately; its
current scope and acceptance gates are summarized in the roadmap.
