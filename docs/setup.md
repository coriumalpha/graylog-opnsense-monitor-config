# Setup

## 1. OPNsense remote logging

Send the OPNsense subsystems you care about to Graylog using RFC5424 syslog. A dedicated Syslog UDP input is simple and works well.

Example Graylog input:

- Type: Syslog UDP
- Port: `5140`
- Store full message: enabled
- Bind address: as appropriate for your environment

The rules assume Graylog exposes the RFC5424 application name in `application_name`, for example `filterlog`, `unbound`, `kea-dhcp4`, `openvpn_server1`, etc.

## 2. Dedicated stream

Create a stream for OPNsense messages and connect the processing pipeline only to that stream. This keeps the rules from touching unrelated logs.

The dashboard script defaults to the stream title:

```text
OPNsense stream
```

Override it with `--stream` if necessary.

## 3. CIDR zone lookup

Create a CSV file based on:

[`../config/lookups/opnsense_network_zones.example.csv`](../config/lookups/opnsense_network_zones.example.csv)

The data adapter must perform CIDR lookups and the lookup table should be named:

```text
opnsense_network_zones
```

The current rule contract is intentionally simple:

```csv
network,zone
10.10.10.0/24,Trusted
10.10.30.0/24,IoT
```

Keep the file persistent if Graylog runs in Docker. A typical bind-mounted container path is:

```text
/usr/share/graylog/data/data/lookups/opnsense_network_zones.csv
```

The exact host path is deployment-specific.

### Do not use the lookup as an anomaly suppressor

If a private address appears as `Private-Other`, identify the network first. A Docker bridge, point-to-point service network or leaked RFC1918 source can be evidence of routing/NAT asymmetry. Only add networks that OPNsense is legitimately expected to observe.

## 4. Pipeline rules

Create the rules in:

[`../config/pipeline/opnsense-rules.conf`](../config/pipeline/opnsense-rules.conf)

Then create the pipeline in:

[`../config/pipeline/opnsense-processing.conf`](../config/pipeline/opnsense-processing.conf)

Use stage matching mode **None or more rules on this stage match** / match-any semantics, not match-all.

Recommended stages:

- Stage 0 — Classification
- Stage 1 — Parsing
- Stage 2 — Normalization / reserved for shared canonicalization
- Stage 3 — CIDR zone enrichment
- Stage 4 — Zone fallback
- Stage 5 — Quality / diagnostics

## 5. Migration from extractors

If an older deployment uses input extractors, do not remove them immediately.

1. Feed the same messages through the pipeline.
2. Compare canonical fields with legacy extractor output.
3. Validate TCP/UDP/ICMP/IGMP separately.
4. Remove legacy extractors only after parity is demonstrated.

Graylog does not retroactively re-run new pipeline rules over historical messages. During a migration, dashboards with a multi-day range will temporarily mix old and newly enriched records.

## 6. Dashboard scripts

Create an API access token for a Graylog user with enough permissions to read streams/searches/views and, for `--apply`, create/update dashboards/searches.

Environment variables:

```bash
export GRAYLOG_URL='https://graylog.example.com'
export GRAYLOG_TOKEN='...'
```

Read-only snapshot:

```bash
python3 scripts/graylog_opnsense_snapshot.py --dashboard 'Firewall monitoring'
```

Dashboard preflight:

```bash
python3 scripts/graylog_opnsense_dashboard.py
```

Apply:

```bash
python3 scripts/graylog_opnsense_dashboard.py --apply
```

Use `--insecure` only for test environments where certificate validation genuinely cannot be used.
