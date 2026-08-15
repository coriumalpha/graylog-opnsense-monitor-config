# Anomaly-detection direction

The Diagnostics page is deliberately built around data-quality signals first. Before adding statistical anomaly detection, establish deterministic signals that have clear operational meaning.

Good candidates include:

- `Private-Other` observed on a VLAN/interface where only known source networks are expected;
- a network explicitly classified as `local-only` appearing at the router;
- parsed IP fields with missing zone enrichment;
- unexpected interface-to-zone combinations;
- sustained growth in `opnsense_parse_status:unparsed`;
- new RFC1918/ULA source ranges not present in the network catalog.

A future field model can use fields such as:

```text
anomaly_type
anomaly_severity
anomaly_reason
traffic_scope
```

## Important principle

Do not make `Private-Other` disappear merely by adding every observed private network to the CIDR lookup. First establish whether the router is legitimately expected to see that network. A previously unknown range may reveal asymmetric routing, missing NAT, a leaked container/service subnet or source spoofing.

## Suggested network metadata evolution

The current lookup remains intentionally simple (`network,zone`). A future version can separate topology intent from the display zone:

```csv
network,zone,scope
10.10.10.0/24,Trusted,routed
10.255.250.0/30,Host-Internal,local-only
```

Then `local-only` traffic observed by OPNsense can be flagged as a deterministic anomaly instead of silently becoming a normal dashboard zone.
