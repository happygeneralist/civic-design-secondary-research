#!/usr/bin/env python3
"""Bounded, provenance-preserving collection for public SEND source material.

This tool is deliberately an acquisition catalogue, not an evidence ingester. It
does not create CDI research objects or make judgements about a source's claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

VERSION = "0.3.0"
DIRECT_CLASSES = {"direct_pdf", "direct_html", "direct_data"}
AUTOMATED_DOCUMENT_CLASSES = {"direct_pdf", "direct_data"}
# reports.ofsted.gov.uk is included solely because files.ofsted.gov.uk redirects
# its robots policy there; document redirects remain same-host only.
TRUSTED_FETCH_HOSTS = frozenset({
    "files.ofsted.gov.uk", "reports.ofsted.gov.uk", "www.gov.uk",
    "assets.publishing.service.gov.uk",
})
USER_AGENT = "CivicDesignSENDCollector/0.1 (+research source acquisition; contact repository owner)"
PRIVATE_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"), ipaddress.ip_network("fe80::/10"),
)


class CollectionError(Exception):
    """An expected, reportable collection error."""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def canonical_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise CollectionError("only absolute http(s) URLs are accepted")
    if parsed.username or parsed.password:
        raise CollectionError("URLs containing credentials are not accepted")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise CollectionError("URL has no hostname")
    port = parsed.port
    netloc = host if port is None or (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80) else f"{host}:{port}"
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def host_for(url: str) -> str:
    return urllib.parse.urlsplit(canonical_url(url)).hostname or ""


def is_public_address(address: str) -> bool:
    try:
        candidate = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (candidate.is_private or candidate.is_loopback or candidate.is_link_local or
                candidate.is_multicast or candidate.is_reserved or candidate.is_unspecified or
                any(candidate in network for network in PRIVATE_NETWORKS))


def assert_safe_url(url: str, allowed_hosts: frozenset[str] | None = None) -> str:
    normalized = canonical_url(url)
    host = host_for(normalized)
    if host == "localhost" or host.endswith(".localhost"):
        raise CollectionError("localhost URLs are not allowed")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise CollectionError(f"host {host} is not approved for this bounded collection")
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise CollectionError(f"cannot resolve host {host}: {exc}") from exc
    if not addresses or any(not is_public_address(address) for address in addresses):
        raise CollectionError(f"host {host} resolves to a non-public address")
    return normalized


def extension_for(content_type: str, url: str) -> str:
    content_type = content_type.split(";", 1)[0].strip().lower()
    known = {"application/pdf": ".pdf", "text/html": ".html", "application/json": ".json", "text/plain": ".txt"}
    if content_type in known:
        return known[content_type]
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    return suffix if suffix and len(suffix) <= 8 else ".bin"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def external_archive_root(root: Path, repository_root: Path) -> Path:
    """Reject archive locations that could put raw source material into Git."""
    archive = root.expanduser().resolve()
    repository = repository_root.expanduser().resolve()
    if archive == repository or repository in archive.parents:
        raise CollectionError("archive-root must be outside the Git checkout")
    return archive


def stable_source_key(prefix: str, url: str) -> str:
    return f"{prefix}-{hashlib.sha256(canonical_url(url).encode()).hexdigest()[:16]}"


def is_discovery_url(url: str) -> bool:
    path = urllib.parse.urlsplit(canonical_url(url)).path.lower().rstrip("/")
    return path.endswith("/special-educational-needs") or "/search" in path or "/collections/" in path


def verified_url_records(path: Path) -> list[dict[str, Any]]:
    """Load bounded individual document candidates without changing supplied seeds."""
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(load_csv(path), start=2):
        try:
            for field in ("url", "title", "source_class", "source_verification", "rights_check"):
                if not (row.get(field) or "").strip():
                    raise CollectionError(f"{field} is required")
            url = assert_safe_url(row["url"], TRUSTED_FETCH_HOSTS)
            if row["source_class"] not in AUTOMATED_DOCUMENT_CLASSES:
                raise CollectionError("source_class must be direct_pdf or direct_data for automated acquisition")
            if is_discovery_url(url):
                raise CollectionError("directories, category pages, collections, and searches are not individual document URLs")
            verification = row["source_verification"].strip()
            if not (verification.startswith("verified_") or verification.startswith("official_")):
                raise CollectionError("source_verification must record an official or verified direct URL check")
            parent = (row.get("discovery_parent_url") or "").strip()
            source_key = (row.get("source_key") or "").strip() or stable_source_key("import", url)
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,100}", source_key):
                raise CollectionError("source_key must use lower-case letters, numbers, and hyphens")
            records.append({
                "source_key": source_key, "title": row["title"].strip(), "record_kind": "document_candidate",
                "source_class": row["source_class"].strip(), "discovery_url": None, "document_url": url,
                "publisher": (row.get("publisher") or "").strip() or None,
                "local_authority": (row.get("local_authority") or "").strip() or None,
                "ons_code": (row.get("ons_code") or "").strip() or None,
                "source_verification": verification, "retrieval_status": "not_attempted",
                "rights_check": row["rights_check"].strip(),
                "discovery_parent_url": canonical_url(parent) if parent else None,
                "collection_id": (row.get("collection_id") or "").strip() or None,
                "seed_provenance": path.name, "import_provenance": [{"input": path.name, "row": row_number}],
                "repository_archive_ref": None, "notes": (row.get("notes") or "").strip(),
            })
        except CollectionError as exc:
            raise CollectionError(f"{path}:{row_number}: {exc}") from exc
    if not records:
        raise CollectionError(f"{path}: no URL records supplied")
    return records


def merge_manifest(manifest: dict[str, Any], imported: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge candidates by document URL, keeping all source-list provenance."""
    result = {**manifest, "records": [dict(record) for record in manifest["records"]], "counts": dict(manifest["counts"])}
    by_url = {record.get("document_url"): record for record in result["records"] if record.get("document_url")}
    keys = {record["source_key"]: record for record in result["records"]}
    added = merged = 0
    for record in imported:
        existing = by_url.get(record["document_url"])
        if existing:
            existing.setdefault("import_provenance", []).extend(record["import_provenance"])
            existing.setdefault("discovery_parent_urls", [])
            if record.get("discovery_parent_url") and record["discovery_parent_url"] not in existing["discovery_parent_urls"]:
                existing["discovery_parent_urls"].append(record["discovery_parent_url"])
            existing.setdefault("collection_ids", [])
            if record.get("collection_id") and record["collection_id"] not in existing["collection_ids"]:
                existing["collection_ids"].append(record["collection_id"])
            merged += 1
            continue
        if record["source_key"] in keys:
            raise CollectionError(f"source_key {record['source_key']} already refers to a different URL")
        result["records"].append(record); by_url[record["document_url"]] = record; keys[record["source_key"]] = record; added += 1
    result["counts"].update(total_records=len(result["records"]), imported_url_records=added, merged_url_records=merged)
    result["created_at"] = now()
    return result


def catalogue(authorities_path: Path, direct_path: Path) -> dict[str, Any]:
    authorities = load_csv(authorities_path)
    direct = load_csv(direct_path)
    if len(authorities) != 153:
        raise CollectionError(f"expected 153 authority seed rows, found {len(authorities)}")
    if len({row["ONS code"] for row in authorities}) != 153:
        raise CollectionError("authority seed has non-unique ONS codes")
    records: list[dict[str, Any]] = []
    link_columns = (
        ("ofsted_area_index", "Ofsted area index (constructed URL)"),
        ("ombudsman_council_search", "Ombudsman council search (constructed; all subjects)"),
        ("govuk_send_search", "GOV.UK SEND search (constructed)"),
    )
    for authority in authorities:
        for kind, column in link_columns:
            url = canonical_url(authority[column])
            records.append({
                "source_key": f"authority-{authority['ONS code'].lower()}-{kind}",
                "title": f"{authority['Local authority']} {kind.replace('_', ' ')} discovery entry",
                "record_kind": "discovery", "source_class": kind,
                "discovery_url": url, "document_url": None,
                "publisher": None, "local_authority": authority["Local authority"],
                "ons_code": authority["ONS code"], "source_verification": "constructed_unchecked",
                "retrieval_status": "not_attempted", "seed_provenance": "SEND_all_153_local_authorities.csv",
                "notes": authority["Verification note"],
            })
    for source in direct:
        url = canonical_url(source["url"])
        is_document = source["source_class"] in DIRECT_CLASSES
        repository_archive_ref = "sources/SRC_001_ofsted_essex_area_send_inspection_jan_2026/original/Essex_Area_SEND_Full_inspection_Jan26.pdf" if source["source_key"] == "essex-ofsted-2026" else None
        records.append({
            "source_key": source["source_key"], "title": source["title"],
            "record_kind": "document_candidate" if is_document else "discovery",
            "source_class": source["source_class"],
            "discovery_url": None if is_document else url,
            "document_url": url if is_document else None,
            "publisher": source["publisher"] or None, "local_authority": source["local_authority"] or None,
            "ons_code": source["ons_code"] or None, "source_verification": source["source_verification"],
            "retrieval_status": source["retrieval_status"], "seed_provenance": "direct_sources.csv",
            "repository_archive_ref": repository_archive_ref, "notes": source["notes"],
        })
    return {"schema_version": 1, "created_at": now(), "purpose": "source discovery and acquisition only; not CDI evidence", "records": records,
            "counts": {"authority_rows": len(authorities), "discovery_records": len(authorities) * 3,
                       "direct_seed_records": len(direct), "total_records": len(records)}}


def archive_state(root: Path) -> dict[str, Any]:
    path = root / "state.json"
    if not path.exists():
        return {"schema_version": 1, "sources": {}, "url_aliases": {}, "hashes": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    value.setdefault("sources", {}); value.setdefault("url_aliases", {}); value.setdefault("hashes", {})
    return value


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    json_dump(root / "state.json", state)


def archive_bytes(root: Path, state: dict[str, Any], *, source_key: str, original_url: str,
                  final_url: str, body: bytes, content_type: str, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    digest = hashlib.sha256(body).hexdigest()
    relationship = {"source_key": source_key, "original_url": canonical_url(original_url), "final_url": canonical_url(final_url),
                    "collected_at": now(), "collection_provenance": metadata.get("collection_provenance"),
                    "discovery_parent_url": metadata.get("discovery_parent_url"), "collection_id": metadata.get("collection_id"),
                    "crawler_metadata": metadata.get("crawler_metadata")}
    relationship = {key: value for key, value in relationship.items() if value is not None}
    existing = state["hashes"].get(digest)
    if existing:
        metadata_path = root / "objects" / digest / "metadata.json"
        try:
            object_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            object_metadata = {"sha256": digest, "archive_path": existing["archive_path"]}
        relationships = object_metadata.setdefault("relationships", [])
        if not any(item.get("source_key") == source_key and item.get("original_url") == relationship["original_url"] for item in relationships):
            relationships.append(relationship)
            json_dump(metadata_path, object_metadata)
        entry = {"status": "duplicate", "sha256": digest, "archive_path": existing["archive_path"], "duplicate_of": existing.get("source_key")}
    else:
        object_dir = root / "objects" / digest
        object_dir.mkdir(parents=True, exist_ok=True)
        archive_path = object_dir / f"original{extension_for(content_type, final_url)}"
        if not archive_path.exists():
            archive_path.write_bytes(body)
        relative = archive_path.relative_to(root).as_posix()
        object_metadata = {"sha256": digest, "bytes": len(body), "archive_path": relative, "first_source_key": source_key,
                           "original_url": original_url, "final_url": final_url, "content_type": content_type, "retrieved_at": now(), "relationships": [relationship], **metadata}
        json_dump(object_dir / "metadata.json", object_metadata)
        state["hashes"][digest] = {"archive_path": relative, "source_key": source_key}
        entry = {"status": "downloaded", "sha256": digest, "archive_path": relative}
    state["sources"][source_key] = {"sha256": digest, "archive_path": entry["archive_path"], "stored_at": now(),
                                     "original_url": canonical_url(original_url), "final_url": canonical_url(final_url),
                                     "local_authority": metadata.get("local_authority"), "ons_code": metadata.get("ons_code"),
                                     "source_class": metadata.get("source_class"), "collection_provenance": metadata.get("collection_provenance")}
    state["url_aliases"][canonical_url(original_url)] = canonical_url(final_url)
    return entry["status"], entry


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def read_response(url: str, *, timeout: float, max_bytes: int,
                  permitted_cross_host_redirect: tuple[str, str] | None = None) -> tuple[str, bytes, str]:
    # Deliberately ignore environment proxy settings: untrusted URL lists must not
    # turn this process into a request through an arbitrary proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    current = assert_safe_url(url, TRUSTED_FETCH_HOSTS)
    original = urllib.parse.urlsplit(current)
    for _ in range(6):
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1"})
        try:
            response = opener.open(request, timeout=timeout)
            status = response.getcode()
        except urllib.error.HTTPError as exc:
            response, status = exc, exc.code
        if status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            if not location:
                raise CollectionError("redirect without Location")
            current = assert_safe_url(urllib.parse.urljoin(current, location), TRUSTED_FETCH_HOSTS)
            redirected = urllib.parse.urlsplit(current)
            redirect_pair = (original.hostname or "", redirected.hostname or "")
            if ((redirected.hostname != original.hostname and redirect_pair != permitted_cross_host_redirect) or
                    (original.scheme == "https" and redirected.scheme != "https")):
                raise CollectionError("cross-host or HTTPS-to-HTTP redirect blocked; resolve and verify it as a separate source")
            continue
        if status != 200:
            raise CollectionError(f"HTTP {status}")
        chunks: list[bytes] = []; total = 0
        while True:
            chunk = response.read(min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise CollectionError(f"response exceeds {max_bytes} byte size cap")
            chunks.append(chunk)
        return current, b"".join(chunks), response.headers.get_content_type()
    raise CollectionError("too many redirects")


def robots_permission(url: str, timeout: float) -> tuple[bool | None, str]:
    safe = assert_safe_url(url, TRUSTED_FETCH_HOSTS)
    parsed = urllib.parse.urlsplit(safe)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        # This narrowly scoped exception covers Ofsted's documented robots redirect.
        # It applies only to policy retrieval, never to source document acquisition.
        permitted_redirect = ("files.ofsted.gov.uk", "reports.ofsted.gov.uk") if parsed.hostname == "files.ofsted.gov.uk" else None
        final, body, _ = read_response(robots_url, timeout=timeout, max_bytes=512_000,
                                       permitted_cross_host_redirect=permitted_redirect)
    except CollectionError as exc:
        return None, f"robots unavailable: {exc}"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(final); parser.parse(body.decode("utf-8", errors="replace").splitlines())
    return parser.can_fetch(USER_AGENT, safe), f"checked {final}"


def validate_response(record: dict[str, Any], body: bytes, content_type: str) -> None:
    """Reject an error/block page that merely has a successful HTTP status."""
    kind = record["source_class"]
    actual_type = content_type.split(";", 1)[0].lower()
    if kind == "direct_pdf":
        if actual_type != "application/pdf" or not body.startswith(b"%PDF-"):
            raise CollectionError("expected a PDF response with an application/pdf content type and PDF signature")
    elif kind == "direct_html":
        snippet = body[:8192].decode("utf-8", errors="ignore").lower()
        if actual_type not in {"text/html", "application/xhtml+xml"} or "<html" not in snippet:
            raise CollectionError("expected an HTML document response")
        if any(marker in snippet for marker in ("access denied", "captcha", "robot check", "request blocked", "error 403")):
            raise CollectionError("HTML response appears to be an access/error page")


def run_path(root: Path, command: str) -> Path:
    return root / "runs" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{command}.json"


def write_run(root: Path, command: str, events: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> Path:
    result = {"schema_version": 1, "command": command, "created_at": now(), "events": events, "counts": dict(Counter(event["status"] for event in events))}
    if extra:
        result.update(extra)
    target = run_path(root, command)
    collision = 1
    while target.exists():
        target = target.with_name(target.stem + f"-{collision}" + target.suffix); collision += 1
    json_dump(target, result)
    return target


def select_fetch_records(manifest: dict[str, Any], limit: int | None, keys: set[str], collection_id: str | None = None) -> list[dict[str, Any]]:
    selected = [record for record in manifest["records"] if record["source_class"] in AUTOMATED_DOCUMENT_CLASSES and (not keys or record["source_key"] in keys) and (not collection_id or record.get("collection_id") == collection_id or collection_id in record.get("collection_ids", []))]
    return selected[:limit] if limit is not None else selected


def pdf_candidate_rows(manifest: dict[str, Any], collection_id: str | None = None) -> list[dict[str, Any]]:
    """Produce an operator-review list without fetching or discovering web pages."""
    rows: list[dict[str, Any]] = []
    for record in select_fetch_records(manifest, None, set(), collection_id):
        rows.append({key: record.get(key) or "" for key in (
            "source_key", "title", "document_url", "source_class", "publisher",
            "local_authority", "ons_code", "source_verification", "rights_check",
            "discovery_parent_url", "collection_id", "notes",
        )})
    return rows


def write_pdf_candidates(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise CollectionError("no direct PDF/data candidates match this selection")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def fetch(manifest: dict[str, Any], root: Path, args: argparse.Namespace) -> tuple[list[dict[str, Any]], Path]:
    root.mkdir(parents=True, exist_ok=True)
    state = archive_state(root)
    events: list[dict[str, Any]] = []
    terms_hosts = {value.lower() for value in args.accept_terms}
    for record in select_fetch_records(manifest, args.limit, set(args.source_key), getattr(args, "collection_id", None)):
        url = record["document_url"]
        event: dict[str, Any] = {"source_key": record["source_key"], "source_class": record["source_class"], "original_url": url,
                                 "host": host_for(url), "local_authority": record["local_authority"], "at": now()}
        if record.get("repository_archive_ref") and not args.include_known_source:
            event.update(status="skipped", reason="already held in repository source archive", repository_archive_ref=record["repository_archive_ref"]); events.append(event); continue
        if record["source_key"] in state["sources"]:
            event.update(status="skipped", reason="source_key already archived", **state["sources"][record["source_key"]]); events.append(event); continue
        if not args.execute:
            event.update(status="dry_run", reason="use --execute to permit network retrieval"); events.append(event); continue
        if event["host"] not in terms_hosts:
            event.update(status="blocked", reason="terms not acknowledged; pass --accept-terms HOST after checking terms and reuse conditions"); events.append(event); continue
        try:
            allowed, robots_note = robots_permission(url, args.timeout)
            if allowed is not True:
                event.update(status="blocked", reason=robots_note if allowed is False else f"{robots_note}; use no bypass; try later"); events.append(event); continue
            last_error: Exception | None = None
            for attempt in range(args.retries + 1):
                try:
                    final_url, body, content_type = read_response(url, timeout=args.timeout, max_bytes=args.max_bytes)
                    validate_response(record, body, content_type)
                    status, stored = archive_bytes(root, state, source_key=record["source_key"], original_url=url, final_url=final_url,
                                                   body=body, content_type=content_type, metadata={"collection_provenance": record.get("seed_provenance", "direct seed"), "publisher": record["publisher"], "local_authority": record["local_authority"], "ons_code": record["ons_code"], "source_class": record["source_class"], "source_verification": record["source_verification"], "rights_check": record.get("rights_check"), "discovery_parent_url": record.get("discovery_parent_url"), "collection_id": record.get("collection_id"), "robots": robots_note})
                    stored.pop("status", None)
                    event.update(status=status, final_url=final_url, content_type=content_type, bytes=len(body), **stored); last_error = None; break
                except (CollectionError, urllib.error.URLError, TimeoutError) as exc:
                    last_error = exc
                    if attempt < args.retries:
                        time.sleep(args.backoff * (attempt + 1))
            if last_error is not None:
                event.update(status="failed", reason=str(last_error))
        except (CollectionError, urllib.error.URLError, TimeoutError) as exc:
            event.update(status="blocked" if "non-public" in str(exc) or "not allowed" in str(exc) or "not approved" in str(exc) else "failed", reason=str(exc))
        events.append(event)
        if args.rate_limit > 0:
            time.sleep(args.rate_limit)
    save_state(root, state)
    return events, write_run(root, "fetch", events, {"execute": args.execute, "manifest_records": len(manifest["records"])})


def import_crawl_export(path: Path, root: Path, max_bytes: int = 25 * 1024 * 1024) -> tuple[list[dict[str, Any]], Path]:
    root.mkdir(parents=True, exist_ok=True)
    state = archive_state(root); events: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for number, row in enumerate(csv.DictReader(handle), start=2):
            event: dict[str, Any] = {"row": number, "at": now(), "import_file": str(path)}
            try:
                url = canonical_url(row.get("url", "")); event["original_url"] = url; event["host"] = host_for(url)
                collection_id = (row.get("collection_id") or path.stem).strip()
                event["source_key"] = (row.get("source_key") or "").strip() or f"crawl-{re.sub(r'[^a-z0-9]+', '-', collection_id.lower()).strip('-')}-{hashlib.sha256(url.encode()).hexdigest()[:12]}"
                content: bytes
                content_path = (row.get("content_path") or "").strip()
                if content_path:
                    supplied = (path.parent / content_path).resolve()
                    if path.parent.resolve() not in supplied.parents:
                        raise CollectionError("content_path must stay within the export directory")
                    if not supplied.is_file():
                        raise CollectionError("content_path does not name a file")
                    if supplied.stat().st_size > max_bytes:
                        raise CollectionError(f"crawler capture exceeds {max_bytes} byte size cap")
                    content = supplied.read_bytes(); supplied_kind = "content_path"
                elif row.get("html") is not None and row.get("html", "") != "":
                    content = row["html"].encode("utf-8"); supplied_kind = "html"
                elif row.get("text") is not None and row.get("text", "") != "":
                    content = row["text"].encode("utf-8"); supplied_kind = "text"
                else:
                    raise CollectionError("one of content_path, html, or text is required")
                if not content:
                    raise CollectionError("crawler capture is empty")
                if len(content) > max_bytes:
                    raise CollectionError(f"crawler capture exceeds {max_bytes} byte size cap")
                digest = hashlib.sha256(content).hexdigest()
                existing_source = state["sources"].get(event["source_key"])
                if existing_source:
                    if existing_source.get("sha256") == digest:
                        event.update(status="skipped", reason="crawler source_key already archived", **existing_source); events.append(event); continue
                    event.update(status="blocked", reason="crawler source_key collision has different content; use a reviewed new source_key"); events.append(event); continue
                content_type = "text/html" if supplied_kind == "html" or content_path.endswith((".html", ".htm")) else "text/plain"
                status, stored = archive_bytes(root, state, source_key=event["source_key"], original_url=url, final_url=url, body=content, content_type=content_type,
                                               metadata={"collection_provenance": "external_site_scraper_export", "source_class": "crawler_capture", "collection_id": collection_id, "crawler_metadata": {k: row.get(k) for k in ("title", "captured_at", "collection_id", "content_path")}, "acquisition_note": "content supplied by external crawler; not independently retrieved or verified"})
                stored.pop("status", None)
                event.update(status=status, bytes=len(content), **stored)
            except (CollectionError, OSError) as exc:
                event.update(status="failed", reason=str(exc))
            events.append(event)
    save_state(root, state)
    return events, write_run(root, "import-crawl-export", events, {"crawler_export": str(path)})


def events_from_runs(root: Path) -> Iterable[dict[str, Any]]:
    for path in sorted((root / "runs").glob("*.json")):
        try:
            yield from json.loads(path.read_text(encoding="utf-8")).get("events", [])
        except (OSError, json.JSONDecodeError):
            continue


def status_report(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    events = list(events_from_runs(root))
    # File names can share a UTC-second prefix; use write time rather than the
    # collision suffix to identify the actual latest run.
    run_files = sorted((root / "runs").glob("*.json"), key=lambda path: path.stat().st_mtime_ns)
    latest_events: list[dict[str, Any]] = []
    if run_files:
        try:
            latest_events = json.loads(run_files[-1].read_text(encoding="utf-8")).get("events", [])
        except (OSError, json.JSONDecodeError):
            pass
    state = archive_state(root)
    historical_outcomes = Counter(event.get("status", "unknown") for event in events)
    latest_outcomes = Counter(event.get("status", "unknown") for event in latest_events)
    source_classes = Counter(record["source_class"] for record in manifest["records"])
    authorities = {record["ons_code"] for record in manifest["records"] if record.get("ons_code")}
    candidates = pdf_candidate_rows(manifest)
    candidate_authorities = {row["ons_code"] for row in candidates if row.get("ons_code")}
    held = list(state["sources"].values())
    covered = {entry.get("local_authority") for entry in held if entry.get("local_authority")}
    hosts = Counter(host_for(entry["original_url"]) for entry in held if entry.get("original_url"))
    return {"registered": len(manifest["records"]), "authority_rows": manifest["counts"]["authority_rows"], "discovery_records": manifest["counts"]["discovery_records"],
            "document_candidates": len(candidates),
            "candidate_coverage": {"direct_documents": len(candidates), "authorities": len(candidate_authorities), "known": len(authorities)},
            "archive": {"externally_held_sources": len(held), "unique_content_objects": len(state["hashes"])},
            "latest_run_outcomes": dict(sorted(latest_outcomes.items())), "historical_event_outcomes": dict(sorted(historical_outcomes.items())),
            "outcomes": dict(sorted(latest_outcomes.items())),
            "authority_coverage": {"externally_held": len(covered), "known": len(authorities), "names": sorted(covered)}, "hosts": dict(hosts), "source_classes": dict(source_classes),
            "caveats": ["Discovery links are constructed/unverified entry points, not reports.", "Externally held counts come from archive state; latest-run skips never overwrite durable holdings.", "A source already held in this Git repository is not counted as externally archived.", "Successful acquisition records provenance only; it does not validate, review or interpret a source.", "Crawler-supplied captures remain distinct from independently downloaded originals.", "Terms, robots and reuse conditions must be checked for every collection host."]}


def metadata_export(root: Path) -> dict[str, Any]:
    """Return publishable provenance metadata without original bytes or local paths."""
    entries: list[dict[str, Any]] = []
    permitted = {"sha256", "bytes", "first_source_key", "original_url", "final_url", "content_type", "retrieved_at",
                 "collection_provenance", "publisher", "local_authority", "ons_code", "source_verification", "robots",
                 "acquisition_note", "crawler_metadata", "rights_check", "relationships"}
    for path in sorted((root / "objects").glob("*/metadata.json")):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            entries.append({key: metadata[key] for key in permitted if key in metadata})
        except (OSError, json.JSONDecodeError):
            continue
    return {"schema_version": 1, "exported_at": now(), "purpose": "metadata-only source acquisition export; original bytes and local archive paths omitted", "sources": entries}


def print_summary(label: str, events: list[dict[str, Any]], run: Path) -> None:
    counts = Counter(event["status"] for event in events)
    print(f"{label}: " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)))
    print(f"run manifest: {run}")


def default_paths(repo: Path) -> tuple[Path, Path]:
    return repo / "intake/seeds/SEND_all_153_local_authorities.csv", repo / "intake/seeds/direct_sources.csv"


def load_manifest_or_catalogue(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "manifest", None):
        return json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    authority, direct = default_paths(Path(args.repo_root))
    return catalogue(authority, direct)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], type=Path)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    catalogue_parser = sub.add_parser("catalogue", help="create a normalized source/discovery manifest")
    catalogue_parser.add_argument("--output", required=True, type=Path)
    urls_parser = sub.add_parser("import-urls", help="merge verified individual official URLs into a new manifest")
    urls_parser.add_argument("--input", required=True, type=Path)
    urls_parser.add_argument("--manifest", type=Path, help="existing manifest; defaults to supplied seed catalogue")
    urls_parser.add_argument("--output", required=True, type=Path)
    candidates_parser = sub.add_parser("discover-pdfs", help="write direct official PDF/data candidates for human review; does not fetch pages")
    candidates_parser.add_argument("--manifest", type=Path)
    candidates_parser.add_argument("--collection-id", help="only list a named imported batch")
    candidates_parser.add_argument("--output", required=True, type=Path)
    fetch_parser = sub.add_parser("fetch", help="fetch direct document candidates only; dry-run by default")
    fetch_parser.add_argument("--manifest", type=Path)
    fetch_parser.add_argument("--archive-root", required=True, type=Path)
    fetch_parser.add_argument("--execute", action="store_true", help="explicitly permit network retrieval")
    fetch_parser.add_argument("--source-key", action="append", default=[])
    fetch_parser.add_argument("--collection-id", help="only fetch verified imported candidates from this named batch")
    fetch_parser.add_argument("--include-known-source", action="store_true", help="allow retrieval of a direct seed already archived in this repository")
    fetch_parser.add_argument("--limit", type=int)
    fetch_parser.add_argument("--accept-terms", action="append", default=[], metavar="HOST", help="host whose terms/reuse rules you have checked")
    fetch_parser.add_argument("--timeout", type=float, default=20.0)
    fetch_parser.add_argument("--max-bytes", type=int, default=25 * 1024 * 1024)
    fetch_parser.add_argument("--retries", type=int, default=1)
    fetch_parser.add_argument("--backoff", type=float, default=1.0)
    fetch_parser.add_argument("--rate-limit", type=float, default=1.0)
    import_parser = sub.add_parser("import-crawl-export", help="archive a local external-scraper CSV export")
    import_parser.add_argument("--input", required=True, type=Path)
    import_parser.add_argument("--archive-root", required=True, type=Path)
    import_parser.add_argument("--max-bytes", type=int, default=25 * 1024 * 1024)
    status_parser = sub.add_parser("status", help="summarise manifest and archive run results")
    status_parser.add_argument("--manifest", type=Path)
    status_parser.add_argument("--archive-root", required=True, type=Path)
    status_parser.add_argument("--json", action="store_true")
    export_parser = sub.add_parser("export-metadata", help="write a publishable metadata-only archive export")
    export_parser.add_argument("--archive-root", required=True, type=Path)
    export_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalogue":
            authority, direct = default_paths(args.repo_root)
            value = catalogue(authority, direct); json_dump(args.output, value)
            print(f"catalogued {value['counts']['authority_rows']} authorities, {value['counts']['discovery_records']} discovery records, {value['counts']['direct_seed_records']} direct seed records: {args.output}")
        elif args.command == "import-urls":
            value = merge_manifest(load_manifest_or_catalogue(args), verified_url_records(args.input)); json_dump(args.output, value)
            print(f"imported {value['counts']['imported_url_records']} verified individual URLs; merged {value['counts']['merged_url_records']}: {args.output}")
        elif args.command == "discover-pdfs":
            rows = pdf_candidate_rows(load_manifest_or_catalogue(args), args.collection_id)
            write_pdf_candidates(args.output, rows)
            print(f"wrote {len(rows)} direct PDF/data candidates for review: {args.output}")
        elif args.command == "fetch":
            archive = external_archive_root(args.archive_root, args.repo_root)
            manifest = load_manifest_or_catalogue(args); events, run = fetch(manifest, archive, args); print_summary("fetch", events, run)
        elif args.command == "import-crawl-export":
            archive = external_archive_root(args.archive_root, args.repo_root)
            events, run = import_crawl_export(args.input, archive, args.max_bytes); print_summary("import-crawl-export", events, run)
        elif args.command == "status":
            archive = external_archive_root(args.archive_root, args.repo_root)
            report = status_report(load_manifest_or_catalogue(args), archive)
            if args.json: print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(f"registered={report['registered']} discovery={report['discovery_records']} document_candidates={report['document_candidates']}")
                print(f"candidate_coverage={report['candidate_coverage']['authorities']}/{report['candidate_coverage']['known']} authorities")
                print("outcomes=" + ", ".join(f"{key}={value}" for key, value in report["outcomes"].items()))
                print(f"externally_held={report['archive']['externally_held_sources']} unique_objects={report['archive']['unique_content_objects']}")
                print(f"authority_coverage={report['authority_coverage']['externally_held']}/{report['authority_coverage']['known']}")
                print("hosts=" + ", ".join(f"{key}={value}" for key, value in report["hosts"].items()))
                print("Caveats:"); [print(f"- {caveat}") for caveat in report["caveats"]]
        elif args.command == "export-metadata":
            archive = external_archive_root(args.archive_root, args.repo_root)
            export = metadata_export(archive); json_dump(args.output, export)
            print(f"exported {len(export['sources'])} metadata-only source records: {args.output}")
    except (CollectionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
