# Dashboard

`scripts/graylog_opnsense_dashboard.py` builds a six-page dashboard designed for a multi-day operational view.

Default title:

```text
OPNsense Integral
```

Default time range: **7 days**.

## Pages

### Overview

High-level firewall, DNS, DHCP and parser-health KPIs; traffic zone matrix; firewall action; subsystem activity; activity timeline; top source zones.

### Firewall

Pass/block counts, inbound WAN noise, transport mix, blocked sources/ports, interface distribution and recent blocked flows.

### DNS

Queries, replies, response codes, query types, latency, clients and recent DNS activity.

**Known semantic caveat in the original deployed dashboard:** the historical `DNS errors` KPI counted every non-NOERROR response, therefore NXDOMAIN dominated the number. Prefer a separate `NXDOMAIN` KPI and a `DNS failures` KPI for SERVFAIL/REFUSED/FORMERR and similar genuine resolver failures.

### DHCP

Lease allocation/reuse activity, DHCP message types, requested/assigned addresses and recent lease events.

### VPN

OpenVPN raw application activity, parsed/unparsed split and recent messages.

The initial OpenVPN parser mostly recognizes `MANAGEMENT:` messages, so raw OpenVPN event volume is not equivalent to client sessions. The `OpenVPN port pass` KPI is also weak in deployments where policy/NAT means successful VPN activity does not appear as a simple destination-port pass count.

### Diagnostics

Parser coverage, unparsed subsystem counts, `Private-Other`, lookup misses, application activity and recent unparsed events.

This page is intentionally operational: unknown private networks should be investigated before being added to the CIDR lookup.

## API implementation notes

Graylog dashboards are backed by Views and Searches. The builder uses those REST objects rather than the legacy dashboard API.

The accompanying snapshot tool is useful when Graylog changes schema details: export an existing dashboard/view/search and compare its JSON to the builder's payload.

## Color validation gotcha

The tested Graylog 7.1 release validates chart colors strictly. Use lowercase hex strings:

```text
#4b78b8   valid
#4B78B8   rejected in the tested release
```

## Safe workflow

1. Run without `--apply`.
2. Inspect the generated plan.
3. Run with `--apply`.
4. Keep the old dashboard until the new one has accumulated enough homogeneous pipeline data.
5. During pipeline migrations, remember that old messages are not reprocessed automatically.
