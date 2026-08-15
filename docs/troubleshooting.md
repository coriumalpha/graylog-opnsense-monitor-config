# Troubleshooting and diagnostic workflow

## Unparsed messages

Search:

```text
opnsense_parse_status:unparsed
```

Group by:

```text
opnsense_unparsed_subsystem
```

Then inspect representative raw `message` values. Add a parser only when the format is understood; not every maintenance/debug line needs full semantic parsing.

## Missing zone fields

Use Graylog's exists syntax rather than relying on a leading wildcard query:

```text
opnsense_log_type:firewall AND NOT _exists_:source_zone
```

and:

```text
opnsense_log_type:firewall AND NOT _exists_:destination_zone
```

If `source_ip`/`destination_ip` are also missing, the problem is parsing/normalization. If the IP exists but the zone does not, inspect lookup/enrichment.

## `Private-Other`

Search separately by side:

```text
source_zone:"Private-Other"
```

Group by `source_ip`, then:

```text
destination_zone:"Private-Other"
```

Group by `destination_ip`.

Classify each network before editing the CSV:

- legitimate routed network -> add to lookup;
- known local-only/service network unexpectedly seen by OPNsense -> investigate routing/NAT;
- truly unknown network -> investigate ownership/topology.

## Why a strange source IP can arrive on a VLAN

A VLAN is an L2 broadcast domain, not source-IP validation. A host in a VLAN can send an Ethernet frame to the router's MAC while the encapsulated IP packet carries an unexpected RFC1918 source. Unless source validation/ACL features block it earlier, OPNsense can receive and log it.

This makes combinations such as:

```text
interface = vlanX
source_zone = Private-Other
```

valuable anomaly signals.

## Transition artifacts

When a new enrichment rule is added, old indexed messages retain their previous fields. A 7-day dashboard can therefore show blanks or `__NOT_FOUND__` for several days after deployment even if all new traffic is correct.

Use a short diagnostic window only to test current behavior; do not necessarily shrink the operational dashboard's normal time range.

## OpenVPN

Raw `application_name:openvpn*` volume may be dominated by management polling/status messages. Inspect `opnsense_parser` and raw events before interpreting that count as sessions or users.

## DNS

NXDOMAIN is not automatically an operational failure. Separate it from SERVFAIL/REFUSED/FORMERR when building alerting or KPIs.
