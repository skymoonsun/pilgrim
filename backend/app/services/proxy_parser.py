"""Parse proxy lists from various formats (raw text, JSON, XML, CSV)."""

import csv
import io
import json
import logging
import re
from dataclasses import dataclass

from app.models.enums import ProxyFormatType, ProxyProtocol

logger = logging.getLogger(__name__)

# ── Parsed proxy entry ─────────────────────────────────────────


@dataclass
class ParsedProxy:
    """A proxy parsed from a source list."""

    ip: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: str | None = None
    password: str | None = None


# ── Raw text parser ────────────────────────────────────────────

# Patterns:
#   ip:port
#   protocol://ip:port
#   ip:port:user:pass
#   protocol://user:pass@ip:port
#   user:pass@ip:port
_IPV4_RE = r"(?:\d{1,3}\.){3}\d{1,3}"
_IPV6_RE = r"\[[0-9a-fA-F:]+\]"
_HOST_RE = rf"(?:{_IPV4_RE}|{_IPV6_RE})"

_RE_PROTOCOL_HOST_PORT = re.compile(
    rf"^(?P<protocol>https?|socks[45])://"
    rf"(?:(?P<user>[^:]+):(?P<pw>[^@]+)@)?"
    rf"(?P<host>{_HOST_RE})"
    rf":(?P<port>\d+)$",
    re.IGNORECASE,
)

_RE_USERPASS_HOST_PORT = re.compile(
    rf"^(?P<user>[^:]+):(?P<pw>[^@]+)@"
    rf"(?P<host>{_HOST_RE})"
    rf":(?P<port>\d+)$",
)

_RE_HOST_PORT = re.compile(
    rf"^(?P<host>{_HOST_RE}):(?P<port>\d+)$",
)

_RE_HOST_PORT_USERPASS = re.compile(
    rf"^(?P<host>{_HOST_RE}):(?P<port>\d+):(?P<user>[^:]+):(?P<pw>[^:]+)$",
)


def _parse_raw_line(line: str) -> ParsedProxy | None:
    """Parse a single line of raw proxy text."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # protocol://[user:pass@]host:port
    m = _RE_PROTOCOL_HOST_PORT.match(line)
    if m:
        protocol = ProxyProtocol(m.group("protocol").lower())
        return ParsedProxy(
            ip=m.group("host").strip("[]"),
            port=int(m.group("port")),
            protocol=protocol,
            username=m.group("user"),
            password=m.group("pw"),
        )

    # user:pass@host:port
    m = _RE_USERPASS_HOST_PORT.match(line)
    if m:
        return ParsedProxy(
            ip=m.group("host").strip("[]"),
            port=int(m.group("port")),
            username=m.group("user"),
            password=m.group("pw"),
        )

    # host:port:user:pass
    m = _RE_HOST_PORT_USERPASS.match(line)
    if m:
        return ParsedProxy(
            ip=m.group("host").strip("[]"),
            port=int(m.group("port")),
            username=m.group("user"),
            password=m.group("pw"),
        )

    # host:port
    m = _RE_HOST_PORT.match(line)
    if m:
        return ParsedProxy(
            ip=m.group("host").strip("[]"),
            port=int(m.group("port")),
        )

    logger.debug("Skipping unparseable line: %s", line[:80])
    return None


def parse_raw_text(content: str) -> list[ParsedProxy]:
    """Parse a raw-text proxy list (one proxy per line)."""
    proxies: list[ParsedProxy] = []
    for line in content.splitlines():
        proxy = _parse_raw_line(line)
        if proxy is not None:
            proxies.append(proxy)
    return proxies


# ── JSON parser (using extraction_spec) ────────────────────────


def parse_json(content: str, extraction_spec: dict | None = None) -> list[ParsedProxy]:
    """Parse a JSON proxy list, optionally using extraction_spec."""
    data = json.loads(content)

    # If extraction_spec is provided, use it to extract proxy fields
    if extraction_spec and "fields" in extraction_spec:
        return _parse_json_with_spec(data, extraction_spec)

    # Default: expect a list of objects with ip/port keys
    items = data if isinstance(data, list) else data.get("proxies", data.get("data", []))
    if isinstance(items, dict):
        # Try common nested keys
        for key in ("proxies", "data", "results"):
            if key in items and isinstance(items[key], list):
                items = items[key]
                break

    proxies: list[ParsedProxy] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ip = item.get("ip") or item.get("ip_address") or item.get("host")
        port = item.get("port")
        if not ip or not port:
            continue
        protocol_str = (item.get("protocol") or item.get("type") or "http").lower()
        try:
            protocol = ProxyProtocol(protocol_str)
        except ValueError:
            protocol = ProxyProtocol.HTTP
        proxies.append(ParsedProxy(
            ip=str(ip),
            port=int(port),
            protocol=protocol,
            username=item.get("username") or item.get("user"),
            password=item.get("password") or item.get("pass"),
        ))
    return proxies


def _parse_json_with_spec(data: object, spec: dict) -> list[ParsedProxy]:
    """Parse JSON using extraction_spec fields to locate proxy fields."""
    from app.crawlers.extraction import _resolve_json_path

    fields = spec.get("fields", {})
    items = data

    # If a list_path is specified, resolve it
    list_path = spec.get("list_path")
    if list_path:
        items = _resolve_json_path(data, list_path)

    if not isinstance(items, list):
        return []

    ip_key = fields.get("ip", "ip")
    port_key = fields.get("port", "port")
    protocol_key = fields.get("protocol", "protocol")
    username_key = fields.get("username", "username")
    password_key = fields.get("password", "password")

    proxies: list[ParsedProxy] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        ip = item.get(ip_key)
        port = item.get(port_key)
        if not ip or not port:
            continue
        protocol_str = str(item.get(protocol_key, "http")).lower()
        try:
            protocol = ProxyProtocol(protocol_str)
        except ValueError:
            protocol = ProxyProtocol.HTTP
        proxies.append(ParsedProxy(
            ip=str(ip),
            port=int(port),
            protocol=protocol,
            username=item.get(username_key),
            password=item.get(password_key),
        ))
    return proxies


# ── CSV parser ─────────────────────────────────────────────────


def parse_csv(content: str) -> list[ParsedProxy]:
    """Parse a CSV proxy list."""
    proxies: list[ParsedProxy] = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        # Try common column names
        ip = row.get("ip") or row.get("ip_address") or row.get("host")
        port = row.get("port")
        if not ip or not port:
            continue
        protocol_str = (row.get("protocol") or row.get("type") or "http").lower()
        try:
            protocol = ProxyProtocol(protocol_str)
        except ValueError:
            protocol = ProxyProtocol.HTTP
        proxies.append(ParsedProxy(
            ip=ip.strip(),
            port=int(port.strip()),
            protocol=protocol,
            username=(row.get("username") or row.get("user") or "").strip() or None,
            password=(row.get("password") or row.get("pass") or "").strip() or None,
        ))
    return proxies


# ── XML parser ─────────────────────────────────────────────────


def parse_xml(content: str) -> list[ParsedProxy]:
    """Parse an XML proxy list."""
    import xml.etree.ElementTree as ET

    proxies: list[ParsedProxy] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        logger.warning("Failed to parse XML proxy list")
        return []

    for proxy_el in root.iter():
        if proxy_el.tag.lower() in ("proxy", "item", "row"):
            ip = _get_xml_text(proxy_el, "ip") or _get_xml_text(proxy_el, "host")
            port = _get_xml_text(proxy_el, "port")
            if not ip or not port:
                continue
            protocol_str = (
                _get_xml_text(proxy_el, "protocol")
                or _get_xml_text(proxy_el, "type")
                or "http"
            ).lower()
            try:
                protocol = ProxyProtocol(protocol_str)
            except ValueError:
                protocol = ProxyProtocol.HTTP
            proxies.append(ParsedProxy(
                ip=ip,
                port=int(port),
                protocol=protocol,
                username=_get_xml_text(proxy_el, "username"),
                password=_get_xml_text(proxy_el, "password"),
            ))
    return proxies


def _get_xml_text(parent: "ET.Element", tag: str) -> str | None:
    """Get text content of a child element, case-insensitive."""
    for child in parent:
        if child.tag.lower() == tag.lower():
            return child.text.strip() if child.text else None
    attr = parent.get(tag) or parent.get(tag.lower())
    return attr.strip() if attr else None


# ── Public entry point ─────────────────────────────────────────


def parse_proxy_list(
    content: str,
    format_type: ProxyFormatType,
    extraction_spec: dict | None = None,
) -> list[ParsedProxy]:
    """Parse a proxy list from content in the given format.

    Args:
        content: Raw text content from the proxy source URL.
        format_type: Format of the content.
        extraction_spec: Optional extraction spec for JSON format.

    Returns:
        List of ParsedProxy entries.
    """
    if format_type == ProxyFormatType.RAW_TEXT:
        return parse_raw_text(content)
    elif format_type == ProxyFormatType.JSON:
        return parse_json(content, extraction_spec)
    elif format_type == ProxyFormatType.CSV:
        return parse_csv(content)
    elif format_type == ProxyFormatType.XML:
        return parse_xml(content)
    else:
        raise ValueError(f"Unsupported proxy format: {format_type}")