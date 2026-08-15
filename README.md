# Graylog + OPNsense monitoring configuration

An opinionated, practical baseline for turning OPNsense syslog into structured Graylog data and a useful multi-page dashboard.

This repository was extracted from a real Graylog 7.1 deployment and cleaned for reuse. Hostnames, domains, addresses, Graylog object IDs and site-specific names have been removed or replaced with examples.

## What it contains

- A staged Graylog pipeline for OPNsense logs.
- IPv4 `filterlog` parsers for TCP, UDP, ICMP and IGMP.
- Parsers/reference rules for Unbound, Kea DHCP and OpenVPN management activity.
- Canonical fields (`source_ip`, `destination_ip`, `event_action`, `network_transport`, etc.).
- CIDR-based zone enrichment with public/`Private-Other` fallback logic.
- Parser-quality diagnostics (`opnsense_parse_status`, `opnsense_parser`).
- A six-page dashboard builder: Overview, Firewall, DNS, DHCP, VPN and Diagnostics.
- A read-only snapshot utility for reverse-engineering an existing Graylog dashboard/search schema.

## Tested baseline

The source deployment was running Graylog **7.1.7** with Graylog Data Node / OpenSearch. The scripts use the Graylog REST API rather than an external SDK.

## Repository layout

- [`docs/setup.md`](docs/setup.md) — input, stream, lookup and pipeline setup.
- [`docs/architecture.md`](docs/architecture.md) — processing stages and design rationale.
- [`docs/fields.md`](docs/fields.md) — normalized field contract.
- [`docs/dashboard.md`](docs/dashboard.md) — dashboard pages, caveats and API notes.
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — parser/enrichment failures and investigation workflow.
- [`docs/anomaly-detection.md`](docs/anomaly-detection.md) — deterministic anomaly model and future direction.
- [`config/pipeline/opnsense-processing.conf`](config/pipeline/opnsense-processing.conf) — pipeline stage definition.
- [`config/pipeline/opnsense-rules.conf`](config/pipeline/opnsense-rules.conf) — rules used by the pipeline.
- [`config/lookups/opnsense_network_zones.example.csv`](config/lookups/opnsense_network_zones.example.csv) — anonymized CIDR lookup example.
- [`scripts/graylog_opnsense_snapshot.py`](scripts/graylog_opnsense_snapshot.py) — read-only export/snapshot helper.
- [`scripts/graylog_opnsense_dashboard.py`](scripts/graylog_opnsense_dashboard.py) — dashboard builder/updater.

## Design principles

1. **Parse first, visualize later.** Dashboards should consume stable fields instead of encoding vendor log syntax in every widget.
2. **Preserve vendor fields and add canonical fields.** Raw OPNsense context remains available while dashboards use normalized names.
3. **Do not hide anomalies by expanding the lookup table blindly.** A private network appearing as `Private-Other` can be evidence of a routing, NAT or topology problem. Identify it first; only then decide whether it belongs in the zone catalog.
4. **Treat pipeline health as production telemetry.** Unparsed events, unknown zones and missing enrichment are first-class diagnostics.
5. **Keep historical transition effects in mind.** Graylog does not automatically reprocess old messages when new pipeline rules are added.

## Quick start

1. Configure OPNsense remote syslog to a Graylog Syslog UDP input.
2. Route those messages to a dedicated OPNsense stream.
3. Create the CIDR lookup table described in [`docs/setup.md`](docs/setup.md).
4. Import/create the rules in [`config/pipeline/opnsense-rules.conf`](config/pipeline/opnsense-rules.conf).
5. Create the pipeline from [`config/pipeline/opnsense-processing.conf`](config/pipeline/opnsense-processing.conf) and connect it only to the OPNsense stream.
6. Validate new messages before removing legacy extractors.
7. Build the dashboard:

```bash
export GRAYLOG_URL='https://graylog.example.com'
export GRAYLOG_TOKEN='...'
python3 scripts/graylog_opnsense_dashboard.py
python3 scripts/graylog_opnsense_dashboard.py --apply
```

The first run is a dry-run/preflight. `--apply` performs writes.

## Important compatibility notes

- Graylog pipeline DSL does not use conventional `if {}` blocks inside `then`; split conditional actions into separate rules/stages.
- Java named regex capture groups cannot contain underscores. Prefer ordinary capture groups plus Graylog `group_names`, or CSV parsing where appropriate.
- In the tested setup `in_private_net()` is called with a string value, while `cidr_match()` expects an IP value.
- Graylog 7.1 chart color validation expects lowercase hexadecimal color strings such as `#4b78b8`.

## Status

This is a working baseline, not a finished SIEM content pack. Known next areas are documented in [`docs/dashboard.md`](docs/dashboard.md), especially richer OpenVPN semantics and deterministic anomaly classification.

## License

AGPL-3.0, matching the repository license.
