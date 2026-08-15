# Processing architecture

## Why a staged pipeline

The pipeline separates parsing from semantics and enrichment. That makes it possible to change a dashboard without re-implementing vendor log parsing in every query.

```text
OPNsense RFC5424 syslog
        |
        v
Stage 0  Classification
        |
        v
Stage 1  Subsystem parsers
        |   filterlog / Unbound / Kea / OpenVPN
        v
Stage 2  Shared normalization (reserved/evolving)
        |
        v
Stage 3  Known-network CIDR lookup
        |
        v
Stage 4  Public / Private-Other fallback
        |
        v
Stage 5  Parser quality diagnostics
```

## Stage 0 — Classification

All OPNsense messages receive:

- `event_source_product = opnsense`
- `opnsense_subsystem = lowercase(application_name)`
- `opnsense_parser_version`

This gives later rules a stable vendor/product context.

## Stage 1 — Parsing

Subsystem-specific rules parse raw vendor messages and set both raw-ish `opnsense_*` fields and canonical fields.

The firewall rules normalize to:

- `source_ip`
- `destination_ip`
- `source_port`
- `destination_port`
- `event_action`
- `network_direction`
- `network_ip_version`
- `network_iana_number`
- `network_transport`
- `network_bytes`
- `network_data_bytes`

Each successful parser also sets:

```text
opnsense_parse_status = parsed
opnsense_parser = <parser-name>
```

## Stage 2 — Normalization

The source deployment left this stage mostly free after moving the most useful normalization into parser rules. It is intentionally retained as the place for future shared semantics such as:

- `event_category`
- `event_type`
- `traffic_scope`
- consistent VPN/DNS/DHCP event naming

## Stage 3 — Zone enrichment

`source_ip` and `destination_ip` are looked up in the `opnsense_network_zones` CIDR lookup table.

Known addresses receive `source_zone` / `destination_zone`.

## Stage 4 — Zone fallback

Lookup misses are classified so the dashboard can distinguish known internal zones from other addresses.

The source deployment used `WAN` as the public fallback label. That is convenient but semantically imperfect: it means "public/not one of my known private networks", not necessarily "this packet traversed the WAN interface".

For new deployments, consider using `Public` as the fallback label and derive an independent `traffic_scope` from interface, direction and zones.

Private RFC1918/ULA addresses not present in the lookup become `Private-Other`.

## Stage 5 — Quality

Any message that has not received `opnsense_parse_status` by this point is marked:

```text
opnsense_parse_status = unparsed
opnsense_parser = unparsed
opnsense_unparsed_subsystem = lowercase(application_name)
```

This rule should be universal. Avoid stacking subsystem-specific "unparsed" rules unless they add a genuinely different diagnostic signal.

## Future anomaly model

A useful next step is to distinguish topology metadata from zone names, for example:

```text
network,zone,scope
10.10.10.0/24,Trusted,routed
10.255.250.0/30,Host-Internal,local-only
```

Then a `local-only` network observed by OPNsense can become a deterministic anomaly rather than simply another valid zone.
