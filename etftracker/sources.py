"""Fetch strategies: turn a Source config into (bytes, content_type, final_url, page_text)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .config import Fund, Settings


@dataclass
class Fetched:
    data: bytes
    content_type: str | None
    url: str
    page_text: str | None = None  # visible text of the landing page, for as-of detection
    rows: list[dict] | None = None  # already-structured rows (JSON sources)
    as_of_hint: str | None = None  # as-of string pulled from a JSON payload
    payload: dict | None = None  # the full JSON payload when relevant


class FetchError(RuntimeError):
    pass


def _client(settings: Settings, extra_headers: dict[str, str] | None = None) -> httpx.Client:
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "text/html,application/xhtml+xml,text/csv,application/json,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    headers.update(extra_headers or {})
    return httpx.Client(headers=headers, follow_redirects=True, timeout=httpx.Timeout(60.0, connect=20.0))


def _get(client: httpx.Client, url: str, referer: str | None = None) -> httpx.Response:
    headers = {"Referer": referer} if referer else {}
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            r = client.get(url, headers=headers)
            if r.status_code >= 500 and attempt < 2:
                continue
            r.raise_for_status()
            return r
        except (httpx.HTTPError, httpx.StreamError) as e:  # retry transient errors
            last_exc = e
    raise FetchError(f"GET {url} failed: {last_exc}")


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def find_link(html: str, base_url: str, pattern: str) -> str | None:
    """First href/src/data-* attribute matching ``pattern`` (regex, case-insensitive)."""
    pat = re.compile(pattern, re.IGNORECASE)
    soup = BeautifulSoup(html, "lxml")
    candidates: list[str] = []
    for tag in soup.find_all(True):
        for attr in ("href", "src", "data-href", "data-url", "data-file", "data-src"):
            v = tag.get(attr)
            if v:
                candidates.append(v)
    # also scan raw text (links embedded in scripts/JSON)
    candidates += re.findall(r"""["']((?:https?:)?//[^"'\s]+|/[^"'\s]+|[\w./-]+\.(?:csv|xlsx?|json)(?:\?[^"'\s]*)?)["']""", html)
    for c in candidates:
        if pat.search(c):
            return urljoin(base_url, c)
    return None


def _dig(obj, path: str | None):
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _from_json_payload(src, body: bytes, content_type: str | None, url: str) -> Fetched:
    text = body.decode("utf-8", "replace").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Raw CSV came back.
        return Fetched(body, content_type or "text/csv", url)
    data = _dig(payload, src.records_path) if src.records_path else payload
    if data is None and isinstance(payload, dict) and "data" in payload:
        data = payload["data"]
    if isinstance(data, str):
        if not data.strip():
            raise FetchError(f"{url}: empty data string in JSON payload ({payload.get('error') if isinstance(payload, dict) else ''})")
        return Fetched(data.encode("utf-8"), "text/csv", url, payload=payload if isinstance(payload, dict) else None)
    if isinstance(data, dict):
        # single record or {key: row} map
        data = list(data.values()) if all(isinstance(v, dict) for v in data.values()) else [data]
    if not isinstance(data, list) or not data:
        err = payload.get("error") if isinstance(payload, dict) else None
        raise FetchError(f"{url}: no rows in JSON payload{': ' + str(err) if err else ''}")
    rows = [r for r in data if isinstance(r, dict)]
    as_of = _dig(payload, src.as_of_path) if src.as_of_path else None
    if as_of is None and rows:
        for k in ("asOfDate", "as_of", "asof", "holdingsDate", "date", "AsOfDate"):
            if k in rows[0]:
                as_of = rows[0][k]
                break
    return Fetched(body, content_type, url, rows=rows, as_of_hint=str(as_of) if as_of else None,
                   payload=payload if isinstance(payload, dict) else None)


def fetch_fund(fund: Fund, settings: Settings):
    """Fetch using the fund's source, trying ``fallback`` sources on failure.

    Returns (Fetched, source_used)."""
    src = fund.source
    errors = []
    while src is not None:
        try:
            return _fetch_source(fund, src, settings), src
        except (FetchError, httpx.HTTPError) as e:
            errors.append(f"{src.type}: {e}")
            src = src.fallback
    raise FetchError(f"{fund.ticker}: all sources failed: " + " | ".join(errors))


def _fetch_source(fund: Fund, src, settings: Settings) -> Fetched:
    with _client(settings, src.headers) as client:
        if src.type == "json":
            if not src.url:
                raise FetchError(f"{fund.ticker}: json source needs url")
            r = _get(client, src.url)
            return _from_json_payload(src, r.content, r.headers.get("content-type"), str(r.url))
        if src.type == "post":
            if not src.url:
                raise FetchError(f"{fund.ticker}: post source needs url")
            r = client.post(src.url, data=src.form)
            r.raise_for_status()
            return _from_json_payload(src, r.content, r.headers.get("content-type"), str(r.url))
        if src.type == "csv":
            if not src.url:
                raise FetchError(f"{fund.ticker}: csv source needs url")
            r = _get(client, src.url)
            return Fetched(r.content, r.headers.get("content-type"), str(r.url))
        if src.type in ("page_link", "html_table"):
            if not src.page:
                raise FetchError(f"{fund.ticker}: {src.type} source needs page")
            page = _get(client, src.page)
            html = page.text
            text = visible_text(html)
            if src.type == "html_table":
                return Fetched(page.content, page.headers.get("content-type"), str(page.url), text)
            if not src.link_pattern:
                raise FetchError(f"{fund.ticker}: page_link source needs link_pattern")
            link = find_link(html, str(page.url), src.link_pattern)
            if not link:
                raise FetchError(f"{fund.ticker}: no link matching {src.link_pattern!r} on {src.page}")
            r = _get(client, link, referer=str(page.url))
            return Fetched(r.content, r.headers.get("content-type"), str(r.url), text)
        raise FetchError(f"{fund.ticker}: unknown source type {src.type!r}")
