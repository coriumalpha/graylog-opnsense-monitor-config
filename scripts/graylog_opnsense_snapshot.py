#!/usr/bin/env python3
"""Read-only Graylog 7.1 dashboard/search snapshot helper.

Environment:
  GRAYLOG_URL=https://graylog.example.com
  GRAYLOG_TOKEN=...

Examples:
  python3 scripts/graylog_opnsense_snapshot.py --dashboard "OPNsense"
  python3 scripts/graylog_opnsense_snapshot.py --dashboard "OPNsense" --insecure

The token is never written to the output directory.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def pretty(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


class Graylog:
    def __init__(self, url: str, token: str, verify_tls: bool = True) -> None:
        self.url = url.rstrip("/")
        auth = base64.b64encode(f"{token}:token".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "X-Requested-By": "graylog-opnsense-snapshot",
            "User-Agent": "graylog-opnsense-snapshot/1.0",
        }
        self.context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()

    def get(self, path: str, *, accept: str = "application/json", quiet_404: bool = False) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        headers = dict(self.headers)
        headers["Accept"] = accept
        req = urllib.request.Request(self.url + path, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, context=self.context, timeout=30) as response:
                data = response.read()
                if not data:
                    return None
                return json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if quiet_404 and exc.code == 404:
                return None
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GET {path} -> HTTP {exc.code}\n{body[:5000]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GET {path} failed: {exc}") from exc


def items(obj: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if not isinstance(obj, dict):
        return []
    for key in keys:
        value = obj.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def object_id(obj: dict[str, Any]) -> str | None:
    value = obj.get("id") or obj.get("_id")
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "$oid" in value:
        return str(value["$oid"])
    return None


def title(obj: dict[str, Any]) -> str:
    return str(obj.get("title") or obj.get("name") or "")


def choose(objects: list[dict[str, Any]], wanted: str, kind: str) -> dict[str, Any]:
    exact = [x for x in objects if title(x).casefold() == wanted.casefold()]
    if len(exact) == 1:
        return exact[0]
    partial = [x for x in objects if wanted.casefold() in title(x).casefold()]
    if len(partial) == 1:
        return partial[0]
    print(f"\nVisible {kind}s:")
    for item in objects:
        print(f"  {object_id(item) or '?':24}  {title(item)}")
    die(f"Cannot uniquely identify {kind} {wanted!r}")


def save(path: Path, value: Any) -> None:
    path.write_text(pretty(value) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Graylog dashboard/search snapshot")
    ap.add_argument("--url", default=os.getenv("GRAYLOG_URL"))
    ap.add_argument("--token", default=os.getenv("GRAYLOG_TOKEN"))
    ap.add_argument("--dashboard", default="OPNsense")
    ap.add_argument("--stream", default="OPNsense")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    if not args.url:
        die("Set GRAYLOG_URL or use --url")
    if not args.token:
        die("Set GRAYLOG_TOKEN or use --token")

    out = Path(args.out or f"graylog-opnsense-snapshot-{datetime.now():%Y%m%d-%H%M%S}").resolve()
    out.mkdir(parents=True, exist_ok=False)
    gl = Graylog(args.url, args.token, verify_tls=not args.insecure)

    dashboards = gl.get(
        "/api/dashboards?" + urllib.parse.urlencode(
            {"page": 1, "per_page": 200, "sort": "title", "order": "asc", "scope": "read"}
        )
    )
    save(out / "dashboard-list.json", dashboards)
    dashboard = choose(items(dashboards, "elements", "dashboards", "views"), args.dashboard, "dashboard")
    dashboard_id = object_id(dashboard)
    if not dashboard_id:
        die("Dashboard has no ID")

    view = gl.get(f"/api/views/{urllib.parse.quote(dashboard_id)}")
    save(out / "view.json", view)
    if not isinstance(view, dict) or not view.get("search_id"):
        die("View has no search_id")

    search_id = str(view["search_id"])
    search = gl.get(
        f"/api/views/search/{urllib.parse.quote(search_id)}",
        accept="application/vnd.graylog.search.v1+json",
    )
    save(out / "search.json", search)

    streams_obj = gl.get("/api/streams")
    save(out / "streams.json", streams_obj)
    streams = items(streams_obj, "streams", "elements")
    matching_streams = [s for s in streams if args.stream.casefold() in title(s).casefold()]

    system = gl.get("/api/system", quiet_404=True)
    if system is not None:
        save(out / "system.json", system)

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "graylog_url": gl.url,
        "dashboard": {"id": dashboard_id, "title": title(view), "search_id": search_id},
        "matching_streams": [
            {"id": object_id(s), "title": title(s), "index_set_id": s.get("index_set_id")}
            for s in matching_streams
        ],
        "notes": [
            "Read-only snapshot; this script only performs GET requests.",
            "The REST token is not stored in output files.",
        ],
    }
    save(out / "snapshot.json", manifest)

    print(f"Snapshot written to {out}")
    print(f"Dashboard ID: {dashboard_id}")
    print(f"Search ID:    {search_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        die(str(exc))
