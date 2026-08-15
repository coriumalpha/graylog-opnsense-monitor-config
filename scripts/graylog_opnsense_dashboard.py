#!/usr/bin/env python3
"""Create/update a six-page OPNsense dashboard on Graylog 7.1.x.

This is the generalized public version of a dashboard builder used in a real
Graylog 7.1.7 deployment. It never deletes searches or dashboards.

Environment:
  GRAYLOG_URL=https://graylog.example.com
  GRAYLOG_TOKEN=...

Run without --apply first. The preflight validates the complete Search payload
against Graylog and writes a local plan. --apply persists a new Search and
creates or updates the named dashboard.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_URL = "https://graylog.example.com"
DEFAULT_STREAM = "OPNsense stream"
DEFAULT_TITLE = "OPNsense Integral"
DEFAULT_DAYS = 7

COLORS = {
    "blue": "#4b78b8", "green": "#5d8947", "red": "#b94a48",
    "amber": "#c28a3a", "purple": "#8067a8", "teal": "#4f8f92",
    "gray": "#758085",
}


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def uid() -> str:
    return str(uuid.uuid4())


def relative(seconds: int) -> dict[str, Any]:
    return {"from": seconds, "type": "relative"}


def es_query(query: str) -> dict[str, str]:
    return {"type": "elasticsearch", "query_string": query}


def save(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class Graylog:
    def __init__(self, url: str, token: str, verify_tls: bool = True) -> None:
        self.url = url.rstrip("/")
        auth = base64.b64encode(f"{token}:token".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {auth}", "Accept": "application/json",
            "X-Requested-By": "graylog-opnsense-dashboard",
            "User-Agent": "graylog-opnsense-dashboard/1.0",
        }
        self.context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()

    def request(self, method: str, path: str, body: Any = None,
                *, content_type: str = "application/json", accept: str = "application/json") -> Any:
        if not path.startswith("/"):
            path = "/" + path
        headers = dict(self.headers)
        headers["Accept"] = accept
        data = None
        if body is not None:
            headers["Content-Type"] = content_type
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.context, timeout=30) as response:
                payload = response.read()
                return json.loads(payload.decode("utf-8")) if payload else None
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}\n{payload[:10000]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def series(name: str | None = None, kind: str = "count", field: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if kind == "count":
        function = "count()"
        search = {"type": "count", "id": name or function, "field": None}
    else:
        if not field:
            raise ValueError(f"{kind} requires a field")
        function = f"{kind}({field})"
        search = {"type": kind, "id": name or function, "field": field}
    widget = {"config": {"name": name, "thresholds": []}, "function": function}
    return widget, search


def value_group(fields: list[str], limit: int = 20, skip_empty: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    widget = {"fields": fields, "type": "values", "config": {"limit": limit, "skip_empty_values": skip_empty}}
    search = {"type": "values", "fields": fields, "limit": limit, "skip_empty_values": skip_empty}
    return widget, search


def time_group() -> tuple[dict[str, Any], dict[str, Any]]:
    interval = {"type": "auto", "scaling": 1.0}
    return (
        {"fields": ["timestamp"], "type": "time", "config": {"interval": interval}},
        {"type": "time", "fields": ["timestamp"], "interval": interval},
    )


def formatting(colors: dict[str, str] | None) -> dict[str, Any] | None:
    if not colors:
        return None
    return {"chart_colors": [{"field_name": k, "chart_color": v} for k, v in colors.items()]}


def viz_config(viz: str, stacked: bool = False) -> Any:
    if viz == "table":
        return {"pinned_columns": [], "show_row_numbers": True}
    if viz == "bar":
        return {"barmode": "stack" if stacked else "group", "axis_type": "linear", "axis_config": None}
    if viz in ("line", "area"):
        return {"interpolation": "linear", "axis_type": "linear"}
    return None


class Page:
    def __init__(self, name: str, stream_id: str, seconds: int) -> None:
        self.name, self.stream_id, self.seconds = name, stream_id, seconds
        self.query_id = uid()
        self.widgets: list[dict[str, Any]] = []
        self.search_types: list[dict[str, Any]] = []
        self.titles: dict[str, str] = {}
        self.mapping: dict[str, list[str]] = {}
        self.positions: dict[str, dict[str, int]] = {}

    def aggregation(self, title: str, query: str, viz: str, pos: tuple[int, int, int, int],
                    *, rows: list[str] | None = None, columns: list[str] | None = None,
                    limit: int = 20, timeline: bool = False, name: str | None = None,
                    kind: str = "count", field: str | None = None,
                    colors: dict[str, str] | None = None, stacked: bool = False) -> None:
        wid, sid = uid(), uid()
        row_pivots: list[dict[str, Any]] = []
        row_groups: list[dict[str, Any]] = []
        col_pivots: list[dict[str, Any]] = []
        col_groups: list[dict[str, Any]] = []
        if timeline:
            wp, sp = time_group(); row_pivots.append(wp); row_groups.append(sp)
        elif rows:
            wp, sp = value_group(rows, limit); row_pivots.append(wp); row_groups.append(sp)
        if columns:
            wp, sp = value_group(columns, limit); col_pivots.append(wp); col_groups.append(sp)
        ws, ss = series(name, kind, field)
        common = {"timerange": relative(self.seconds), "query": es_query(query), "streams": [self.stream_id],
                  "stream_categories": [], "filter": None, "filters": []}
        self.widgets.append({
            "id": wid, "type": "aggregation", **common,
            "config": {"row_pivots": row_pivots, "column_pivots": col_pivots, "series": [ws],
                       "sort": [], "units": {}, "visualization": viz,
                       "visualization_config": viz_config(viz, stacked),
                       "formatting_settings": formatting(colors), "rollup": False,
                       "event_annotation": False, "row_limit": limit if row_pivots else None,
                       "column_limit": limit if col_pivots else None},
            "description": None, "context": None,
        })
        self.search_types.append({
            "id": sid, "name": "chart", "type": "pivot", **common,
            "series": [ss], "sort": [], "rollup": False,
            "row_groups": row_groups, "column_groups": col_groups,
        })
        self.titles[wid] = title
        self.mapping[wid] = [sid]
        col, row, width, height = pos
        self.positions[wid] = {"col": col, "row": row, "width": width, "height": height}

    def messages(self, title: str, query: str, fields: list[str], pos: tuple[int, int, int, int], limit: int = 100) -> None:
        wid, sid = uid(), uid()
        common = {"timerange": relative(self.seconds), "query": es_query(query), "streams": [self.stream_id],
                  "stream_categories": [], "filter": None, "filters": []}
        self.widgets.append({
            "id": wid, "type": "messages", **common,
            "config": {"fields": fields, "units": {}, "show_message_row": True, "show_summary": True,
                       "decorators": [], "sort": [{"type": "pivot", "field": "timestamp", "direction": "Descending"}]},
            "description": None, "context": None,
        })
        self.search_types.append({
            "id": sid, "name": None, "type": "messages", **common,
            "limit": limit, "offset": 0, "sort": [{"field": "timestamp", "order": "DESC"}],
            "fields": fields, "decorators": [],
        })
        self.titles[wid] = title
        self.mapping[wid] = [sid]
        col, row, width, height = pos
        self.positions[wid] = {"col": col, "row": row, "width": width, "height": height}

    def query(self, v1: bool = False) -> dict[str, Any]:
        q = {"id": self.query_id, "timerange": relative(self.seconds), "filters": [],
             "query": es_query(""), "search_types": copy.deepcopy(self.search_types)}
        if v1:
            q["filter"] = None
        else:
            q["streams"] = [self.stream_id]
        return q

    def state(self) -> dict[str, Any]:
        return {
            "selected_fields": None, "static_message_list_id": None,
            "titles": {"tab": {"title": self.name}, "widget": self.titles},
            "widgets": self.widgets, "widget_mapping": self.mapping, "positions": self.positions,
            "formatting": {"highlighting": []}, "display_mode_settings": {"positions": {}},
        }


def build(stream_id: str, title: str, seconds: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    pages: list[Page] = []

    p = Page("Overview", stream_id, seconds)
    for i, (label, query, color) in enumerate([
        ("Firewall events", "opnsense_log_type:firewall", "blue"),
        ("Blocked", "opnsense_log_type:firewall AND event_action:block", "red"),
        ("DNS queries", "opnsense_parser:unbound_query", "teal"),
        ("NXDOMAIN", "opnsense_parser:unbound_reply AND dns_response_code:NXDOMAIN", "amber"),
        ("DHCP leases", "opnsense_parser:(kea_lease_allocated OR kea_lease_reused)", "amber"),
        ("Unparsed", "opnsense_parse_status:unparsed", "red"),
    ]):
        p.aggregation(label, query, "numeric", (1 + i * 2, 1, 2, 2), name=label, colors={label: COLORS[color]})
    p.aggregation("Traffic matrix · source → destination", "opnsense_log_type:firewall", "table", (1, 3, 6, 5), rows=["source_zone", "destination_zone"], limit=30)
    p.aggregation("Firewall action", "opnsense_log_type:firewall", "pie", (7, 3, 3, 5), rows=["event_action"], colors={"pass": COLORS["green"], "block": COLORS["red"]})
    p.aggregation("Subsystem activity", "opnsense_parser:*", "pie", (10, 3, 3, 5), rows=["opnsense_log_type"], colors={"firewall": COLORS["blue"], "dns": COLORS["teal"], "dhcp": COLORS["amber"], "vpn": COLORS["purple"]})
    p.aggregation("Activity over time", "opnsense_parser:*", "area", (1, 8, 12, 5), timeline=True, columns=["opnsense_log_type"], stacked=True)
    pages.append(p)

    p = Page("Firewall", stream_id, seconds)
    p.aggregation("Pass", "opnsense_log_type:firewall AND event_action:pass", "numeric", (1, 1, 3, 2), name="Pass", colors={"Pass": COLORS["green"]})
    p.aggregation("Block", "opnsense_log_type:firewall AND event_action:block", "numeric", (4, 1, 3, 2), name="Block", colors={"Block": COLORS["red"]})
    p.aggregation("Transport", "opnsense_log_type:firewall", "pie", (7, 1, 3, 5), rows=["network_transport"])
    p.aggregation("Interfaces", "opnsense_log_type:firewall", "bar", (10, 1, 3, 5), rows=["opnsense_interface"], limit=15)
    p.aggregation("Top blocked source IPs", "opnsense_log_type:firewall AND event_action:block", "bar", (1, 3, 6, 5), rows=["source_ip"], limit=20)
    p.aggregation("Top blocked destination ports", "opnsense_log_type:firewall AND event_action:block AND destination_port:*", "bar", (1, 8, 6, 5), rows=["destination_port"], limit=20)
    p.messages("Recent blocked flows", "opnsense_log_type:firewall AND event_action:block", ["timestamp", "source_ip", "source_port", "destination_ip", "destination_port", "source_zone", "destination_zone", "opnsense_interface", "network_transport"], (7, 6, 6, 7), 100)
    pages.append(p)

    p = Page("DNS", stream_id, seconds)
    p.aggregation("Queries", "opnsense_parser:unbound_query", "numeric", (1, 1, 3, 2), name="Queries", colors={"Queries": COLORS["teal"]})
    p.aggregation("Replies", "opnsense_parser:unbound_reply", "numeric", (4, 1, 3, 2), name="Replies", colors={"Replies": COLORS["green"]})
    p.aggregation("NXDOMAIN", "opnsense_parser:unbound_reply AND dns_response_code:NXDOMAIN", "numeric", (7, 1, 3, 2), name="NXDOMAIN", colors={"NXDOMAIN": COLORS["amber"]})
    p.aggregation("DNS failures", "opnsense_parser:unbound_reply AND dns_response_code:(SERVFAIL OR REFUSED OR FORMERR)", "numeric", (10, 1, 3, 2), name="Failures", colors={"Failures": COLORS["red"]})
    p.aggregation("Response codes", "opnsense_parser:unbound_reply", "pie", (1, 3, 4, 5), rows=["dns_response_code"])
    p.aggregation("Query types", "opnsense_parser:unbound_query", "bar", (5, 3, 4, 5), rows=["dns_query_type"], limit=15)
    p.aggregation("Top DNS clients", "opnsense_parser:unbound_query", "bar", (9, 3, 4, 5), rows=["source_ip"], limit=15)
    p.messages("Recent DNS replies", "opnsense_parser:unbound_reply", ["timestamp", "source_ip", "dns_query_name", "dns_query_type", "dns_response_code", "dns_response_time_seconds"], (1, 8, 12, 6), 100)
    pages.append(p)

    p = Page("DHCP", stream_id, seconds)
    p.aggregation("Lease allocated", "opnsense_parser:kea_lease_allocated", "numeric", (1, 1, 3, 2), name="Allocated", colors={"Allocated": COLORS["green"]})
    p.aggregation("Lease reused", "opnsense_parser:kea_lease_reused", "numeric", (4, 1, 3, 2), name="Reused", colors={"Reused": COLORS["blue"]})
    p.aggregation("DHCP message types", "opnsense_log_type:dhcp AND dhcp_message_type:*", "bar", (7, 1, 6, 5), rows=["dhcp_message_type"], limit=15)
    p.aggregation("Lease IPs", "opnsense_log_type:dhcp AND dhcp_lease_ip:*", "table", (1, 3, 6, 5), rows=["dhcp_lease_ip", "dhcp_client_mac"], limit=30)
    p.messages("Recent DHCP", "opnsense_log_type:dhcp", ["timestamp", "event_action", "dhcp_client_mac", "dhcp_lease_ip", "dhcp_requested_ip", "dhcp_message_type", "opnsense_interface"], (1, 8, 12, 6), 100)
    pages.append(p)

    p = Page("VPN", stream_id, seconds)
    p.aggregation("OpenVPN events", "application_name:openvpn*", "numeric", (1, 1, 3, 2), name="OpenVPN", colors={"OpenVPN": COLORS["purple"]})
    p.aggregation("Parsed VPN", "opnsense_log_type:vpn AND opnsense_parse_status:parsed", "numeric", (4, 1, 3, 2), name="Parsed", colors={"Parsed": COLORS["green"]})
    p.aggregation("Unparsed OpenVPN", "application_name:openvpn* AND opnsense_parse_status:unparsed", "numeric", (7, 1, 3, 2), name="Unparsed", colors={"Unparsed": COLORS["red"]})
    p.aggregation("OpenVPN applications", "application_name:openvpn*", "bar", (1, 3, 6, 5), rows=["application_name"], limit=15)
    p.aggregation("VPN parsers", "application_name:openvpn*", "pie", (7, 3, 6, 5), rows=["opnsense_parser"], limit=15)
    p.messages("Recent OpenVPN", "application_name:openvpn*", ["timestamp", "application_name", "opnsense_parser", "event_action", "message"], (1, 8, 12, 6), 100)
    pages.append(p)

    p = Page("Diagnostics", stream_id, seconds)
    p.aggregation("Unparsed", "opnsense_parse_status:unparsed", "numeric", (1, 1, 3, 2), name="Unparsed", colors={"Unparsed": COLORS["red"]})
    p.aggregation("Private-Other", 'source_zone:"Private-Other" OR destination_zone:"Private-Other"', "numeric", (4, 1, 3, 2), name="Private-Other", colors={"Private-Other": COLORS["amber"]})
    p.aggregation("Lookup misses", 'source_zone:"__NOT_FOUND__" OR destination_zone:"__NOT_FOUND__"', "numeric", (7, 1, 3, 2), name="Lookup miss", colors={"Lookup miss": COLORS["red"]})
    p.aggregation("Unparsed by subsystem", "opnsense_parse_status:unparsed", "bar", (1, 3, 6, 5), rows=["opnsense_unparsed_subsystem"], limit=20)
    p.aggregation("Private-Other source IPs", 'source_zone:"Private-Other"', "bar", (7, 3, 6, 5), rows=["source_ip"], limit=20)
    p.aggregation("Private-Other destination IPs", 'destination_zone:"Private-Other"', "bar", (1, 8, 6, 5), rows=["destination_ip"], limit=20)
    p.messages("Recent unparsed", "opnsense_parse_status:unparsed", ["timestamp", "application_name", "opnsense_unparsed_subsystem", "message"], (7, 8, 6, 6), 100)
    pages.append(p)

    search_v2 = {"id": None, "queries": [p.query(False) for p in pages], "parameters": []}
    search_v1 = {"id": None, "queries": [p.query(True) for p in pages], "parameters": [], "skip_no_streams_check": False}
    view = {
        "id": None, "type": "DASHBOARD", "title": title,
        "summary": "Operational OPNsense observability dashboard.",
        "description": "Generated dashboard using normalized OPNsense pipeline fields and CIDR zone enrichment.",
        "search_id": "__SEARCH_ID__", "properties": [], "requires": {},
        "state": {p.query_id: p.state() for p in pages},
    }
    return search_v2, search_v1, view


def validate_colors(view: dict[str, Any]) -> None:
    for page in view.get("state", {}).values():
        for widget in page.get("widgets", []):
            fs = widget.get("config", {}).get("formatting_settings") or {}
            for item in fs.get("chart_colors", []):
                color = item.get("chart_color")
                if not isinstance(color, str) or not re.fullmatch(r"#[a-f0-9]{3,6}", color):
                    die(f"Invalid Graylog chart color: {color!r}")


def streams(gl: Graylog) -> list[dict[str, Any]]:
    obj = gl.request("GET", "/api/streams")
    return obj.get("streams", []) if isinstance(obj, dict) else []


def dashboards(gl: Graylog) -> list[dict[str, Any]]:
    obj = gl.request("GET", "/api/dashboards?" + urllib.parse.urlencode({"page": 1, "per_page": 200, "sort": "title", "order": "asc", "scope": "read"}))
    return obj.get("elements", []) if isinstance(obj, dict) else []


def find_by_title(values: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    exact = [x for x in values if str(x.get("title", "")).casefold() == wanted.casefold()]
    if len(exact) > 1:
        die(f"More than one object is titled {wanted!r}")
    return exact[0] if exact else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Create/update OPNsense Integral dashboard")
    ap.add_argument("--url", default=os.getenv("GRAYLOG_URL", DEFAULT_URL))
    ap.add_argument("--token", default=os.getenv("GRAYLOG_TOKEN"))
    ap.add_argument("--stream", default=DEFAULT_STREAM)
    ap.add_argument("--title", default=DEFAULT_TITLE)
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--insecure", action="store_true")
    args = ap.parse_args()
    if not args.token:
        die("Set GRAYLOG_TOKEN or use --token")
    if not 1 <= args.days <= 90:
        die("--days must be between 1 and 90")

    gl = Graylog(args.url, args.token, not args.insecure)
    stream = find_by_title(streams(gl), args.stream)
    if not stream:
        die(f"Stream {args.stream!r} not found")
    seconds = args.days * 86400
    search_v2, search_v1, view = build(str(stream["id"]), args.title, seconds)
    validate_colors(view)

    out = Path(f"graylog-opnsense-dashboard-{datetime.now():%Y%m%d-%H%M%S}").resolve()
    out.mkdir(parents=True, exist_ok=False)
    save(out / "search-v2.json", search_v2)
    save(out / "search-v1-preflight.json", search_v1)
    save(out / "view-template.json", view)

    metadata = gl.request("POST", "/api/views/search/metadata", search_v1)
    save(out / "search-metadata.json", metadata)
    existing = find_by_title(dashboards(gl), args.title)

    if not args.apply:
        print(f"Preflight OK. No writes performed. Plan: {out}")
        return 0

    if existing:
        old_view = gl.request("GET", f"/api/views/{urllib.parse.quote(str(existing['id']))}")
        save(out / "backup-view.json", old_view)
        old_sid = old_view.get("search_id") if isinstance(old_view, dict) else None
        if old_sid:
            old_search = gl.request("GET", f"/api/views/search/{urllib.parse.quote(str(old_sid))}", accept="application/vnd.graylog.search.v1+json")
            save(out / "backup-search.json", old_search)

    created_search = gl.request("POST", "/api/views/search", search_v2,
                                content_type="application/vnd.graylog.search.v2+json",
                                accept="application/vnd.graylog.search.v2+json")
    if not isinstance(created_search, dict) or not created_search.get("id"):
        die("Graylog did not return a Search ID")
    search_id = str(created_search["id"])
    entity = copy.deepcopy(view)
    entity["search_id"] = search_id

    if existing:
        view_id = str(existing["id"])
        entity["id"] = view_id
        gl.request("PUT", f"/api/views/{urllib.parse.quote(view_id)}", {"entity": entity})
        action = "updated"
    else:
        entity["id"] = None
        created = gl.request("POST", "/api/views", {"entity": entity})
        if not isinstance(created, dict) or not created.get("id"):
            die("Graylog did not return a View ID")
        view_id = str(created["id"])
        action = "created"

    print(f"Dashboard {action}: {args.title}")
    print(f"View ID:   {view_id}")
    print(f"Search ID: {search_id}")
    print(f"Backup/plan: {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        die(str(exc))
