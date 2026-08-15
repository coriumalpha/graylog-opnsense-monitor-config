# Field contract

The dashboard is designed around normalized fields. Vendor-specific fields are kept for debugging, but new visualizations should prefer the canonical names below.

## Common classification

| Field | Meaning |
|---|---|
| `event_source_product` | Product identifier, normally `opnsense` |
| `opnsense_subsystem` | Lowercase RFC5424 application name |
| `opnsense_parser_version` | Parser schema/version marker |
| `opnsense_log_type` | Logical subsystem such as `firewall`, `dns`, `dhcp`, `vpn`, `firewall_admin` |
| `opnsense_parser` | Rule/parser that successfully handled the message |
| `opnsense_parse_status` | `parsed` or `unparsed` |

## Network / firewall canonical fields

| Field | Type/meaning |
|---|---|
| `source_ip` | Source IP |
| `destination_ip` | Destination IP |
| `source_port` | Source transport port, when applicable |
| `destination_port` | Destination transport port, when applicable |
| `source_zone` | CIDR-enriched source zone |
| `destination_zone` | CIDR-enriched destination zone |
| `event_action` | `pass`, `block`, or subsystem-specific action |
| `network_direction` | OPNsense/pf direction (`in`/`out`) |
| `network_ip_version` | IP version |
| `network_iana_number` | IANA protocol number |
| `network_transport` | `tcp`, `udp`, `icmp`, `igmp`, etc. |
| `network_bytes` | IP packet length when present |
| `network_data_bytes` | Payload/data length when present |
| `opnsense_interface` | OPNsense interface name from filterlog |
| `opnsense_rule_number` | pf/filter rule number |
| `opnsense_tracker` | OPNsense tracker/rule identifier when present |
| `opnsense_tcp_flags` | TCP flags from filterlog |

## DNS / Unbound

| Field | Meaning |
|---|---|
| `dns_query_name` | Queried FQDN/name |
| `dns_query_type` | A, AAAA, PTR, HTTPS, etc. |
| `dns_query_class` | Usually IN |
| `dns_response_code` | NOERROR, NXDOMAIN, SERVFAIL, ... |
| `dns_response_time_seconds` | Resolver response latency |
| `dns_from_cache` | Cache indicator when the log contains it |
| `dns_response_size` | Response size when available |
| `opnsense_unbound_worker` | Unbound worker/thread identifier |

Do not equate NXDOMAIN with resolver failure. A useful dashboard separates `NXDOMAIN` from actual failures such as `SERVFAIL`, `REFUSED` or `FORMERR`.

## DHCP / Kea

Common normalized fields:

- `dhcp_hw_type`
- `dhcp_client_mac`
- `dhcp_client_id`
- `dhcp_transaction_id`
- `dhcp_message_type`
- `dhcp_message_type_code`
- `dhcp_lease_ip`
- `dhcp_requested_ip`
- `dhcp_lease_duration_seconds`

## OpenVPN

The initial parser intentionally handles management messages conservatively and sets:

- `opnsense_openvpn_management_message`
- `opnsense_log_type = vpn`
- `opnsense_parser = openvpn_management`

A richer deployment should split semantic event types such as TLS handshake, certificate verification, authentication, client connect/disconnect and tunnel up/down.
